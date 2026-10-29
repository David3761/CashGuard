"""F2 step 2: money helpers and the `Money` field type (work-breakdown 0.3 rule 2, F2; arch 9.1).

Money is a Decimal rounded half-up to the cent, read exactly (a float through its shortest repr, a
string only in machine format), and splits always add up exactly. In JSON a money value is a
number (arch 9.1); JSON is read exactly with `parse_json` (pydantic's own JSON parser reads numbers
as floats).
"""

import json
from decimal import ROUND_DOWN, Decimal, InvalidOperation, getcontext, localcontext
from time import perf_counter

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel, ValidationError

from app.domain.money import (
    MAX_ABS,
    Money,
    Split,
    parse_json,
    quantize_cents,
    share_each,
    split_share,
    to_decimal,
    to_money,
)


class Priced(BaseModel):
    amount: Money
    maybe: Money | None = None


TOTALS = st.decimals(min_value=Decimal("0.01"), max_value=Decimal("100000"), places=2)
LONG_TOTALS = st.decimals(min_value=Decimal("0"), max_value=Decimal("100000"), places=3)
PEOPLE = st.integers(min_value=1, max_value=50)
LARGEST = MAX_ABS - Decimal("0.01")
STORED = st.decimals(min_value=-LARGEST, max_value=LARGEST, places=2)


def in_cents(*values: Decimal) -> bool:
    # `==` ignores the exponent (Decimal("4E+2") == 400), so the 2 dp are checked on their own.
    return all(value.as_tuple().exponent == -2 for value in values)


# ── happy path: the work-breakdown F2 golden values ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("1.005", Decimal("1.01"), id="string tie rounds up"),
        pytest.param(1.005, Decimal("1.01"), id="float via str, not 1.00499…"),
        pytest.param(Decimal("-2.675"), Decimal("-2.68"), id="negative tie rounds away from zero"),
        pytest.param(7, Decimal("7.00"), id="int"),
        pytest.param(Decimal("1E+2"), Decimal("100.00"), id="exponent notation"),
    ],
)  # fmt: skip
def test_to_money_rounds_half_up_to_the_cent(
    value: Decimal | float | str, expected: Decimal
) -> None:
    result = to_money(value)

    assert result == expected
    assert in_cents(result)


@pytest.mark.parametrize(
    ("total", "people", "own", "others"),
    [
        pytest.param(Decimal("500"), 5, Decimal("100"), Decimal("400"), id="Scene A: 500 for 5"),
        pytest.param(Decimal("500"), 3, Decimal("166.67"), Decimal("333.33"), id="500 for 3"),
        pytest.param(Decimal("100"), 1, Decimal("100"), Decimal("0"), id="alone"),
        pytest.param(Decimal("0.01"), 3, Decimal("0.00"), Decimal("0.01"), id="one cent for 3"),
    ],
)
def test_split_share_gives_the_own_share_and_the_rest(
    total: Decimal, people: int, own: Decimal, others: Decimal
) -> None:
    split = split_share(total, people)

    assert split == (own, others)
    assert (split.own, split.others) == (own, others)
    assert split.own + split.others == total
    assert in_cents(split.own, split.others)


def test_split_share_returns_a_named_tuple() -> None:
    split = split_share(Decimal("500"), 5)

    assert isinstance(split, Split)
    assert isinstance(split, tuple)


def test_share_each_divides_the_others_share_for_display() -> None:
    # Display only: 2 x 166.67 = 333.34, while the receivable stays 333.33 (WB F2).
    assert share_each(Decimal("333.33"), 2) == Decimal("166.67")
    assert share_each(Decimal("400"), 4) == Decimal("100")
    assert in_cents(share_each(Decimal("333.33"), 2), share_each(Decimal("400"), 4))


# ── quantize_cents: the one rounding rule, shared with C1's format_money (review R10) ───────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("1.005"), "1.01"),
        (Decimal("-2.675"), "-2.68"),
        (Decimal("-0.004"), "0.00"),
        (Decimal("123456789012345.675"), "123456789012345.68"),  # no money range: display too
        (Decimal("1E+25"), "10000000000000000000000000.00"),  # 28 digits: the context's limit
    ],
)
def test_quantize_cents_rounds_half_up_with_no_money_range(value: Decimal, expected: str) -> None:
    assert str(quantize_cents(value)) == expected


@pytest.mark.parametrize("value", [Decimal("1E+26"), Decimal("NaN"), Decimal("-Infinity")])
def test_quantize_cents_rejects_what_cannot_be_rounded(value: Decimal) -> None:
    with pytest.raises(ValueError, match="cent"):
        quantize_cents(value)


@pytest.mark.parametrize("value", [1.005, "1.005", 1, True, None])
def test_quantize_cents_takes_only_a_decimal(value: object) -> None:
    with pytest.raises(TypeError, match="Decimal"):
        quantize_cents(value)  # type: ignore[arg-type]


# ── boundaries ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0.005", "0.01"),
        ("0.00499", "0.00"),
        ("-0.005", "-0.01"),
        ("-0.004", "0.00"),
        ("9999999999.99", "9999999999.99"),
        ("-9999999999.99", "-9999999999.99"),
    ],
)
def test_to_money_boundaries(value: str, expected: str) -> None:
    # str() too: a "-0.00" would be written -0.0 in JSON and "-0" in a text.
    assert str(to_money(value)) == expected


@pytest.mark.parametrize(
    "value",
    [
        "10000000000",
        "-10000000000",
        "9999999999.995",
        pytest.param("1E+9999999999999999999", id="exponent beyond what Decimal holds"),
        pytest.param("1E-9999999999999999999", id="negative exponent beyond Decimal"),
        pytest.param(10**10, id="int 10^10"),
        pytest.param(10**5000, id="int 10^5000"),  # repr() of it fails, so explicit ids
        pytest.param(-(10**5000), id="int -10^5000"),
    ],
)
def test_to_money_rejects_amounts_outside_numeric_12_2(value: str | int) -> None:
    # NUMERIC(12,2) (arch 4.3) holds |x| < 10^10. 9 999 999 999.995 rounds up to exactly 10^10.
    # 10**5000: str() of such an int raises Python's own error; ours must come first (R6).
    with pytest.raises(ValueError, match="money amount out of range") as raised:
        to_money(value)

    assert "set_int_max_str_digits" not in str(raised.value)


def test_split_share_boundaries() -> None:
    assert split_share(Decimal("0.01"), 2) == (Decimal("0.01"), Decimal("0.00"))
    assert split_share(Decimal("0"), 3) == (Decimal("0"), Decimal("0"))
    assert split_share(Decimal("500"), 50) == (Decimal("10"), Decimal("490"))
    assert in_cents(*split_share(Decimal("0"), 3), *split_share(Decimal("500"), 50))


@pytest.mark.parametrize(
    ("total", "people", "own", "others"),
    [
        pytest.param("100.005", 1, "100.01", "0.00", id="100.005 alone: rounded first"),
        pytest.param("0.015", 2, "0.01", "0.01", id="0.015 for 2 is 0.02 for 2"),
        pytest.param("0.004", 3, "0.00", "0.00", id="below half a cent is nothing"),
        pytest.param("333.335", 3, "111.11", "222.23", id="333.335 for 3"),
    ],
)
def test_split_share_rounds_the_total_before_splitting(
    total: str, people: int, own: str, others: str
) -> None:
    # Without rounding the total first, (100.005, 1) would give (100.01, -0.005) (review R2).
    split = split_share(total, people)

    assert (str(split.own), str(split.others)) == (own, others)
    assert split.others >= 0


def test_share_each_of_nothing_is_nothing() -> None:
    assert share_each(Decimal("0"), 4) == Decimal("0.00")
    assert in_cents(share_each(Decimal("0"), 4))


# ── invalid input and error messages ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        "abc", "", " ", True, False, None, "Infinity", "-inf", "NaN",
        Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"), float("nan"), float("inf"), [1],
    ],
)  # fmt: skip
def test_to_money_rejects_what_is_not_a_finite_number(value: object) -> None:
    # bool is an int (True would be 1.00), and garbage must never become money.
    with pytest.raises(ValueError, match="money"):
        to_money(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("1_000.5", id="underscore"),
        pytest.param("  5 \n", id="surrounding whitespace"),
        pytest.param(" 5", id="leading space"),
        pytest.param("5 ", id="trailing space"),
        pytest.param("\u0661\u0662\u0663", id="Arabic-Indic digits"),
        pytest.param("\uff11\uff12", id="fullwidth digits"),
        pytest.param("1\u0662\u0663", id="ASCII 1 then Arabic-Indic digits"),
        pytest.param("1.\uff15", id="a fullwidth digit after the point"),
        pytest.param("1e\u0662", id="an Arabic-Indic exponent"),
        pytest.param("+5", id="plus sign"),
        pytest.param("5.", id="no digit after the point"),
        pytest.param(".5", id="no digit before the point"),
        pytest.param("007", id="leading zeros"),
        pytest.param("0x10", id="hex"),
        pytest.param("1e", id="empty exponent"),
        pytest.param("--5", id="double minus"),
        pytest.param("1,000", id="thousands comma"),
        pytest.param("1" * 65, id="longer than 64 chars"),
    ],
)
def test_to_money_takes_strings_in_machine_format_only(value: str) -> None:
    # A string must be written like a JSON number, in ASCII (review R4).
    with pytest.raises(ValueError, match="machine format"):
        to_money(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("-0.004", "0.00"), ("1E+2", "100.00"), ("1e-3", "0.00"), ("12.30", "12.30"), ("0", "0.00")],
)
def test_to_money_accepts_the_machine_format(value: str, expected: str) -> None:
    assert str(to_money(value)) == expected


def test_to_money_error_names_the_value() -> None:
    with pytest.raises(ValueError, match="'abc'"):
        to_money("abc")


@pytest.mark.parametrize("people", [0, -1])
def test_split_share_rejects_fewer_than_one_person(people: int) -> None:
    with pytest.raises(ValueError, match=f"people must be ≥ 1, got {people}"):
        split_share(Decimal("500"), people)


@pytest.mark.parametrize("people", [True, 1.5, "5", None])
def test_split_share_rejects_a_people_count_that_is_not_an_int(people: object) -> None:
    with pytest.raises(TypeError, match="people must be an int"):
        split_share(Decimal("500"), people)  # type: ignore[arg-type]


def test_split_share_rejects_a_negative_total() -> None:
    with pytest.raises(ValueError, match="total must not be negative, got -1"):
        split_share(Decimal("-1"), 2)


def test_share_each_rejects_bad_counts_and_negative_amounts() -> None:
    with pytest.raises(ValueError, match="count must be ≥ 1, got 0"):
        share_each(Decimal("400"), 0)
    with pytest.raises(TypeError, match="count must be an int"):
        share_each(Decimal("400"), True)
    with pytest.raises(ValueError, match="others must not be negative"):
        share_each(Decimal("-400"), 4)


def test_error_messages_never_echo_a_huge_input() -> None:
    # A 1 MB value must not end up in logs or in Claude's context (review R7).
    huge = "x" * 1_000_000
    for call in (
        lambda: split_share(Decimal("1"), huge),  # type: ignore[arg-type]
        lambda: share_each(Decimal("1"), huge),  # type: ignore[arg-type]
        lambda: to_money(huge),
        lambda: to_decimal(huge),
    ):
        with pytest.raises((TypeError, ValueError)) as raised:
            call()
        assert len(str(raised.value)) < 200


# ── security, isolation from the ambient decimal context ────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("1E+999999", id="huge exponent"),
        pytest.param("9" * 10_000, id="10 000 digits"),
        pytest.param("-" + "9" * 10_000, id="-10 000 digits"),
        pytest.param(10**5000, id="int 10^5000"),
    ],
)
def test_to_money_rejects_huge_inputs_quickly(value: str | int) -> None:
    # Tool and JSON input is untrusted: huge exponents and digit runs must not hang anything.
    # The bound is generous on purpose (coverage and CI are slow); a hang would be seconds+ (R8).
    start = perf_counter()
    with pytest.raises(ValueError, match="money"):
        to_money(value)

    assert perf_counter() - start < 1.0


def test_a_million_digit_int_is_rejected_before_any_conversion() -> None:
    # Decimal(10**1_000_000) alone takes ~12 s: the size is checked first (DoS guard).
    huge = 10**1_000_000
    for convert in (to_money, to_decimal):
        start = perf_counter()
        with pytest.raises(ValueError, match="out of range: <int too large to show>"):
            convert(huge)

        assert perf_counter() - start < 1.0


def test_money_helpers_ignore_the_callers_decimal_context() -> None:
    # The decimal context is thread / task local and anyone can change it: with prec 3 the plain
    # 500 / 3 is 166 and 500.00 - 166.67 is 333.
    with localcontext() as ctx:
        ctx.prec = 3
        ctx.rounding = ROUND_DOWN
        ctx.traps[InvalidOperation] = False

        assert to_money("2.675") == Decimal("2.68")
        assert split_share(Decimal("500"), 3) == (Decimal("166.67"), Decimal("333.33"))
        assert share_each(Decimal("333.33"), 2) == Decimal("166.67")
        assert quantize_cents(Decimal("123456.785")) == Decimal("123456.79")
        assert str(to_money("-0.004")) == "0.00"
        with pytest.raises(ValueError, match="money"):
            to_money("abc")
        assert (getcontext().prec, getcontext().rounding) == (3, ROUND_DOWN)


# ── language: machine format only ───────────────────────────────────────────────────────────


def test_to_money_takes_machine_format_only() -> None:
    # "30,40" is the RO way to write 30.40: not machine input. "10.000" (RO for ten thousand)
    # reads as 10.00, so user-formatted text must never reach to_money (documented).
    with pytest.raises(ValueError, match="money"):
        to_money("30,40")
    assert to_money("10.000") == Decimal("10.00")


# ── to_decimal: exact, bounded, no negative zero (review R3) ───────────────────────────────


def test_to_decimal_is_exact_and_not_rounded() -> None:
    # The non-money Decimals (multipliers, ratios) use it: no rounding to the cent.
    assert to_decimal("2.1") == Decimal("2.1")
    assert to_decimal(0.3) == Decimal("0.3")
    assert to_decimal("0.123456789") == Decimal("0.123456789")
    assert to_decimal("9999999999.999") == Decimal("9999999999.999")
    assert to_decimal("1E-28") == Decimal("1E-28")
    with pytest.raises(ValueError, match="number"):
        to_decimal(True)


@pytest.mark.parametrize(("value", "expected"), [("-0", "0"), ("-0.0", "0.0"), (-0.0, "0.0")])
def test_to_decimal_never_returns_negative_zero(value: str | float, expected: str) -> None:
    assert str(to_decimal(value)) == expected


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("1E+999999999999999999", id="huge exponent"),
        pytest.param("1E+9999999999999999999", id="exponent beyond what Decimal holds"),
        pytest.param(Decimal("1E+999999999"), id="huge Decimal"),
        pytest.param(10**10, id="10^10"),
        pytest.param(10**5000, id="a 5000-digit int"),
    ],
)
def test_to_decimal_rejects_numbers_out_of_range(value: object) -> None:
    # Later arithmetic would raise decimal.Overflow, not a ValueError.
    with pytest.raises(ValueError, match="number out of range"):
        to_decimal(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value", ["0." + "1" * 29, "1E-29", Decimal("1." + "0" * 28), Decimal("1E-999999999")]
)
def test_to_decimal_rejects_more_than_28_digits_or_places(value: object) -> None:
    with pytest.raises(ValueError, match="too precise"):
        to_decimal(value)  # type: ignore[arg-type]


# ── the Money field type (arch 9.1: money is a JSON number) ────────────────────────────────


def test_money_field_rounds_on_validation_and_stays_a_decimal_in_python() -> None:
    priced = Priced.model_validate({"amount": "1.005"})

    assert priced.amount == Decimal("1.01")
    assert isinstance(priced.amount, Decimal)
    assert priced.model_dump() == {"amount": Decimal("1.01"), "maybe": None}


def test_money_field_dumps_as_a_json_number() -> None:
    priced = Priced(amount=Decimal("31.20"), maybe=Decimal("400"))

    dumped = priced.model_dump(mode="json")

    assert dumped == {"amount": 31.2, "maybe": 400.0}
    assert all(isinstance(value, float) for value in dumped.values())
    # A JSON number keeps no trailing zeros: 31.20 is written 31.2 (Q7; arch 9.1 clarified).
    assert priced.model_dump_json() == '{"amount":31.2,"maybe":400.0}'
    assert Priced(amount=Decimal("5")).model_dump_json() == '{"amount":5.0,"maybe":null}'


def test_money_field_json_schema_is_a_number() -> None:
    properties = Priced.model_json_schema()["properties"]

    assert properties["amount"]["type"] == "number"
    assert properties["maybe"]["anyOf"] == [{"type": "number"}, {"type": "null"}]


@pytest.mark.parametrize(
    "value", ["abc", True, None, float("nan"), "1E+30", "1_000", "\u0661\u0662\u0663"]
)
def test_money_field_rejects_bad_values_with_a_validation_error(value: object) -> None:
    with pytest.raises(ValidationError, match="amount"):
        Priced.model_validate({"amount": value})


def test_money_field_round_trips_through_json() -> None:
    priced = Priced(amount=Decimal("1234.56"))

    assert Priced.model_validate_json(priced.model_dump_json()) == priced
    assert Priced.model_validate(json.loads(priced.model_dump_json())) == priced


# ── reading JSON exactly (review R1) ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("0.0049999999999999999", "0.00", id="just below half a cent"),
        pytest.param("1.00499999999999999999", "1.00", id="just below 1.005"),
        pytest.param("0.005", "0.01", id="a real tie"),
        pytest.param("12345678.885000000000000001", "12345678.89", id="just above a tie"),
    ],
)
def test_parse_json_reads_long_numbers_exactly(raw: str, expected: str) -> None:
    priced = Priced.model_validate(parse_json(f'{{"amount": {raw}}}'))

    assert str(priced.amount) == expected


def test_pydantic_json_parsing_reads_numbers_as_floats() -> None:
    # Why parse_json exists: pydantic-core (and the stdlib default) read a JSON number as the
    # nearest float, 0.005 here, before any validator runs. If this ever fails, pydantic became
    # exact and parse_json can go.
    assert Priced.model_validate_json('{"amount": 0.0049999999999999999}').amount == Decimal("0.01")


@pytest.mark.parametrize("raw", ['{"a": NaN}', '{"a": Infinity}', '{"a": -Infinity}'])
def test_parse_json_rejects_non_finite_constants(raw: str) -> None:
    # The stdlib accepts them by default; strict JSON (and pydantic) doesn't.
    with pytest.raises(ValueError, match="JSON"):
        parse_json(raw)


def test_parse_json_keeps_strings_ints_and_nesting() -> None:
    parsed = parse_json(b'{"amount": "12.30", "n": 5, "items": [{"amount": 4500.10}]}')

    assert parsed == {"amount": "12.30", "n": 5, "items": [{"amount": Decimal("4500.10")}]}


@pytest.mark.parametrize(
    "raw", ['{"amount": 1, "amount": 500}', '{"items": [{"a": 1, "a": 1}]}', '{"x": {}, "x": {}}']
)
def test_parse_json_rejects_a_duplicate_key(raw: str) -> None:
    # The stdlib silently keeps the last value; which one wins is a trap (C1's H-7 loader rule).
    with pytest.raises(ValueError, match="duplicate key"):
        parse_json(raw)


# ── invariants (property tests) ──────────────────────────────────────────────────────────────


@given(total=TOTALS, people=PEOPLE)
def test_split_share_always_adds_up_exactly(total: Decimal, people: int) -> None:
    own, others = split_share(total, people)

    assert own + others == total
    assert own >= 0
    assert others >= 0
    assert in_cents(own, others)
    assert abs(own - total / people) <= Decimal("0.005")


@given(total=LONG_TOTALS, people=PEOPLE)
def test_split_share_of_a_3_dp_total_adds_up_to_its_rounded_value(
    total: Decimal, people: int
) -> None:
    own, others = split_share(total, people)

    assert own + others == to_money(total)
    assert own >= 0
    assert others >= 0
    assert in_cents(own, others)


@given(value=st.decimals(min_value=-(10**9), max_value=10**9, allow_nan=False))
def test_to_money_is_the_nearest_cent_and_idempotent(value: Decimal) -> None:
    money = to_money(value)

    assert in_cents(money)
    assert abs(money - value) <= Decimal("0.005")
    assert to_money(money) == money
    assert money == quantize_cents(value)


@given(value=st.floats(min_value=-1e9, max_value=1e9, allow_nan=False))
def test_to_money_reads_a_float_through_its_shortest_repr(value: float) -> None:
    assert to_money(value) == to_money(Decimal(repr(value)))


@given(others=TOTALS, count=PEOPLE)
def test_share_each_is_within_a_cent_of_the_exact_share(others: Decimal, count: int) -> None:
    each = share_each(others, count)

    assert each >= 0
    assert in_cents(each)
    assert abs(each * count - others) <= Decimal("0.005") * count


@given(amount=STORED)
def test_money_json_round_trip_never_loses_a_cent(amount: Decimal) -> None:
    # Every storable amount has ≤ 12 significant digits; a float's shortest repr keeps 15.
    priced = Priced(amount=amount)

    assert Priced.model_validate_json(priced.model_dump_json()).amount == amount
    assert Priced.model_validate(parse_json(priced.model_dump_json())).amount == amount
