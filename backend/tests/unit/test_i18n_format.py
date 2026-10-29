"""C1.1: RO / EN money, percent and date formats (work-breakdown C1, B13; D48 defaults).

RO `10.000 lei` · `30,40 lei` · `-30,40 lei` · `100 lei`; EN `10,000 lei` · `30.40 lei`.
Whole amounts drop the decimals; money is Decimal or int, never float.
"""

import re
import unicodedata
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

import app.i18n.format as format_module
from app.domain.enums import Language
from app.domain.money import quantize_cents
from app.i18n.format import format_date, format_money, format_money_in_sentence, format_pct

MONTHS_RO = ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie", "august",
             "septembrie", "octombrie", "noiembrie", "decembrie"]  # fmt: skip
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December"]  # fmt: skip
WEEKDAYS_RO = ["luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică"]
WEEKDAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
CEDILLAS = set("\u015f\u0163\u015e\u0162")
SEPARATORS = {"ro": (".", ","), "en": (",", ".")}  # thousands, decimal


# ── format_money ────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("amount", "lang", "expected"),
    [
        (10000, "ro", "10.000 lei"),
        (Decimal("30.4"), "ro", "30,40 lei"),
        (Decimal("1234.5"), "en", "1,234.50 lei"),
        (10000, "en", "10,000 lei"),
        (Decimal("30.4"), "en", "30.40 lei"),
        (500, "ro", "500 lei"),
        (Decimal("500.00"), "ro", "500 lei"),
    ],
)
def test_format_money_matches_the_spec_examples(
    amount: Decimal | int, lang: str, expected: str
) -> None:
    assert format_money(amount, lang) == expected


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (999, "999 lei"),
        (1000, "1.000 lei"),
        (Decimal("999999.99"), "999.999,99 lei"),
        (1000000, "1.000.000 lei"),
        (0, "0 lei"),
        (Decimal("0.01"), "0,01 lei"),
        (Decimal("0.005"), "0,01 lei"),
        (Decimal("0.004"), "0 lei"),
        (Decimal("99.995"), "100 lei"),
        (Decimal("1.10"), "1,10 lei"),
    ],
)
def test_format_money_boundaries_in_romanian(amount: Decimal | int, expected: str) -> None:
    assert format_money(amount, "ro") == expected


@pytest.mark.parametrize(
    ("amount", "lang", "expected"),
    [
        (Decimal("0.1") + Decimal("0.2"), "ro", "0,30 lei"),
        (Decimal("2.675"), "ro", "2,68 lei"),
        (Decimal("-2.675"), "ro", "-2,68 lei"),
        (Decimal("12345678.90"), "ro", "12.345.678,90 lei"),
        (Decimal("-30.4"), "ro", "-30,40 lei"),
        (-10000, "ro", "-10.000 lei"),
        (Decimal("-1234.5"), "en", "-1,234.50 lei"),
        (Decimal("-0.004"), "ro", "0 lei"),
        (Decimal("-0"), "ro", "0 lei"),
    ],
)
def test_format_money_is_exact_half_up_and_never_shows_minus_zero(
    amount: Decimal | int, lang: str, expected: str
) -> None:
    assert format_money(amount, lang) == expected


@pytest.mark.parametrize("amount", [30.4, True, "30.4", None])
def test_format_money_rejects_anything_but_decimal_or_int(amount: object) -> None:
    with pytest.raises(TypeError, match="to_money"):
        format_money(amount, "ro")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("amount", "message"),
    [
        (Decimal("NaN"), "the amount must be a finite number"),
        (Decimal("sNaN"), "the amount must be a finite number"),
        (Decimal("Infinity"), "the amount must be a finite number"),
        (Decimal("-Infinity"), "the amount must be a finite number"),
        (Decimal("1E+30"), "the amount is too large to format"),
    ],
)
def test_format_money_rejects_amounts_that_are_not_a_finite_sum(
    amount: Decimal, message: str
) -> None:
    # Each failure says what is wrong (a NaN is not "too large").
    with pytest.raises(ValueError, match=message):
        format_money(amount, "ro")


def _half_up(n: int, k: int, places: int) -> tuple[str, int, int]:
    """n * 10^-k rounded half-up (away from zero) to `places` decimals, in integers only:
    (sign, whole part, fraction digits). An oracle independent of `decimal` (review R7)."""
    shift = k - places
    if shift >= 0:
        quotient, remainder = divmod(abs(n), 10**shift)
        if 2 * remainder >= 10**shift and shift > 0:
            quotient += 1
    else:
        quotient = abs(n) * 10**-shift
    sign = "-" if n < 0 and quotient else ""  # never "-0"
    whole, fraction = divmod(quotient, 10**places)
    return sign, whole, fraction


def _grouped(whole: int, separator: str) -> str:
    digits = str(whole)
    groups: list[str] = []
    while digits:
        groups.insert(0, digits[-3:])
        digits = digits[:-3]
    return separator.join(groups)


def _money_oracle(n: int, k: int, lang: str) -> str:
    thousands, decimal_sep = SEPARATORS[lang]
    sign, whole, cents = _half_up(n, k, 2)
    fraction = f"{decimal_sep}{cents:02d}" if cents else ""
    return f"{sign}{_grouped(whole, thousands)}{fraction} lei"


def _pct_oracle(n: int, k: int, lang: str, decimals: int) -> str:
    thousands, decimal_sep = SEPARATORS[lang]
    sign, whole, fraction = _half_up(n, k - 2, decimals)  # percent = n * 10^-(k-2)
    tail = f"{decimal_sep}{fraction:0{decimals}d}" if decimals else ""
    return f"{sign}{_grouped(whole, thousands)}{tail}%"


@given(st.integers(-(10**35), 10**35), st.integers(10, 45), st.sampled_from(["ro", "en"]))
def test_format_money_equals_an_integer_arithmetic_oracle(n: int, k: int, lang: str) -> None:
    # Up to 36 significant digits: past the 28-digit decimal context, where double rounding
    # would show (review R1/R7). The exact string is compared, so "-0 lei" can't hide.
    assert format_money(Decimal(f"{n}E-{k}"), lang) == _money_oracle(n, k, lang)


@given(
    st.integers(-(10**35), 10**35),
    st.integers(15, 45),
    st.sampled_from(["ro", "en"]),
    st.sampled_from([0, 1, 2]),
)
def test_format_pct_equals_an_integer_arithmetic_oracle(
    n: int, k: int, lang: str, decimals: int
) -> None:
    assert format_pct(Decimal(f"{n}E-{k}"), lang, decimals=decimals) == _pct_oracle(
        n, k, lang, decimals
    )


# Uniform integers almost never land on a rounding half, so these put the digits right at one:
# n = q·10^s + 5·10^(s-1) + delta, with s digits below the rounding position (up to 33).
NEAR_HALF = st.tuples(
    st.integers(0, 10**6), st.integers(1, 33), st.sampled_from([-1, 0, 1]), st.booleans()
)


def _near_half(q: int, s: int, delta: int, negative: bool) -> int:
    n = q * 10**s + 5 * 10 ** (s - 1) + delta
    return -n if negative else n


@given(NEAR_HALF, st.sampled_from(["ro", "en"]))
def test_format_money_rounds_half_boundaries_like_the_oracle(
    case: tuple[int, int, int, bool], lang: str
) -> None:
    n, k = _near_half(*case), case[1] + 2
    assert format_money(Decimal(f"{n}E-{k}"), lang) == _money_oracle(n, k, lang)


@given(NEAR_HALF, st.sampled_from(["ro", "en"]), st.sampled_from([0, 1, 2]))
def test_format_pct_rounds_half_boundaries_like_the_oracle(
    case: tuple[int, int, int, bool], lang: str, decimals: int
) -> None:
    n, k = _near_half(*case), case[1] + 2 + decimals
    assert format_pct(Decimal(f"{n}E-{k}"), lang, decimals=decimals) == _pct_oracle(
        n, k, lang, decimals
    )


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (Decimal("0.004999999999999999999999999999999"), "0 lei"),
        (Decimal("2.674999999999999999999999999999999"), "2,67 lei"),
        (Decimal("2.675000000000000000000000000000001"), "2,68 lei"),
        (Decimal("-0.004999999999999999999999999999999"), "0 lei"),
        (10**25, "10.000.000.000.000.000.000.000.000 lei"),
    ],
)
def test_format_money_rounds_once_even_beyond_28_digits(
    amount: Decimal | int, expected: str
) -> None:
    assert format_money(amount, "ro") == expected


def test_format_money_reports_the_callers_amount_beyond_the_format_limit() -> None:
    # 10^26 lei needs 29 digits with the cents: past the 28-digit context (the limit).
    # format_money's own message (quantize_cents' error is mapped, as agreed with F2).
    with pytest.raises(ValueError, match="the amount is too large to format") as info:
        format_money(10**26, "ro")

    assert str(10**26) in str(info.value)


@given(st.decimals(min_value=Decimal("-1e12"), max_value=Decimal("1e12"), places=2))
def test_format_money_ro_and_en_differ_only_in_the_separators(amount: Decimal) -> None:
    swapped = format_money(amount, "ro").translate(str.maketrans(".,", ",."))

    assert swapped == format_money(amount, "en")


# ── format_pct ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "lang", "decimals", "expected"),
    [
        (0.77, "ro", 0, "77%"),
        (0.77, "en", 0, "77%"),
        (Decimal("0.77"), "ro", 0, "77%"),
        (0, "ro", 0, "0%"),
        (1, "ro", 0, "100%"),
        (0.005, "ro", 0, "1%"),
        (0.0049, "ro", 0, "0%"),
        (0.995, "ro", 0, "100%"),
        (0.125, "ro", 1, "12,5%"),
        (0.125, "en", 1, "12.5%"),
        (0.285, "ro", 0, "29%"),  # via str(): float maths would give 28.4999… → 28
        (0.035, "ro", 1, "3,5%"),
        (0.12345, "en", 2, "12.35%"),
        (-0.05, "ro", 0, "-5%"),
        (-0.001, "ro", 0, "0%"),
        (12.5, "ro", 0, "1.250%"),
        (12.5, "en", 0, "1,250%"),
    ],
)
def test_format_pct_examples_and_boundaries(
    value: Decimal | float | int, lang: str, decimals: int, expected: str
) -> None:
    assert format_pct(value, lang, decimals=decimals) == expected


@pytest.mark.parametrize(
    ("value", "decimals", "expected"),
    [
        (Decimal("0.1249999999999999999999999999999"), 0, "12%"),  # double rounding: 13%
        (Decimal("0.12449999999999999999999999999999"), 1, "12,4%"),  # double rounding: 12,5%
        (Decimal("0.1249999999999999999999999999999"), 1, "12,5%"),  # correct: 12.4999… → 12.5
        (Decimal("0.004999999999999999999999999999999"), 0, "0%"),
        (Decimal("0.005000000000000000000000000000000"), 0, "1%"),
        (Decimal("-0.004999999999999999999999999999999"), 0, "0%"),
    ],
)
def test_format_pct_rounds_once_even_beyond_28_digits(
    value: Decimal, decimals: int, expected: str
) -> None:
    # Review R1: scaling to percent must be exact; only the final quantize may round.
    assert format_pct(value, "ro", decimals=decimals) == expected


@pytest.mark.parametrize("value", [Decimal("1E+999999999"), Decimal("1E+30"), 1e300])
def test_format_pct_reports_the_callers_value_when_too_large(value: Decimal | float) -> None:
    # Review R6: an overflow is "too large", not "not finite", and names what the caller passed.
    with pytest.raises(ValueError, match="too large") as info:
        format_pct(value, "ro")

    assert repr(value) in str(info.value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), Decimal("NaN")])
def test_format_pct_rejects_values_that_cannot_be_shown(value: float | Decimal) -> None:
    with pytest.raises(ValueError, match="value"):
        format_pct(value, "ro")


@pytest.mark.parametrize("value", [True, "0.5", None])
def test_format_pct_rejects_non_numbers(value: object) -> None:
    with pytest.raises(TypeError):
        format_pct(value, "ro")  # type: ignore[arg-type]


@pytest.mark.parametrize("decimals", [-1, 3, True, 1.0, Decimal(1), 2.0])
def test_format_pct_accepts_zero_to_two_decimals_only(decimals: object) -> None:
    with pytest.raises(ValueError, match="decimals"):
        format_pct(0.5, "ro", decimals=decimals)  # type: ignore[arg-type]


@given(st.floats(min_value=0, max_value=1), st.sampled_from(["ro", "en"]))
def test_format_pct_of_a_probability_is_a_whole_percent_from_0_to_100(p: float, lang: str) -> None:
    text = format_pct(p, lang)

    assert re.fullmatch(r"\d{1,3}%", text)
    assert 0 <= int(text.removesuffix("%")) <= 100


# ── format_date ─────────────────────────────────────────────────────────────────────────


def test_format_date_long_form_in_both_languages() -> None:
    sim_day = date(2026, 6, 15)  # the demo's sim date, a Monday (D35)

    assert format_date(sim_day, "ro") == "15 iunie 2026"
    assert format_date(sim_day, "en") == "15 June 2026"
    assert format_date(sim_day, "ro", with_weekday=True) == "luni, 15 iunie 2026"
    assert format_date(sim_day, "en", with_weekday=True) == "Monday, 15 June 2026"
    assert format_date(date(2026, 12, 31), "ro", with_year=False) == "31 decembrie"
    assert format_date(date(2026, 12, 31), "en", with_year=False) == "31 December"


@pytest.mark.parametrize("month", range(1, 13))
def test_format_date_names_every_month(month: int) -> None:
    day = date(2026, month, 1)

    assert format_date(day, "ro") == f"1 {MONTHS_RO[month - 1]} 2026"
    assert format_date(day, "en") == f"1 {MONTHS_EN[month - 1]} 2026"


@pytest.mark.parametrize("offset", range(7))
def test_format_date_names_every_weekday(offset: int) -> None:
    day = date(2026, 6, 15 + offset)  # Monday 15 … Sunday 21 June 2026

    assert format_date(day, "ro", with_weekday=True).startswith(f"{WEEKDAYS_RO[offset]}, ")
    assert format_date(day, "en", with_weekday=True).startswith(f"{WEEKDAYS_EN[offset]}, ")


@pytest.mark.parametrize(
    ("day", "ro", "en"),
    [
        (date(2026, 10, 25), "duminică, 25 octombrie 2026", "Sunday, 25 October 2026"),  # DST day
        (date(2028, 2, 29), "marți, 29 februarie 2028", "Tuesday, 29 February 2028"),  # leap day
        (date(2026, 12, 31), "joi, 31 decembrie 2026", "Thursday, 31 December 2026"),
        (date(2027, 1, 1), "vineri, 1 ianuarie 2027", "Friday, 1 January 2027"),
    ],
)
def test_format_date_edges_of_the_calendar(day: date, ro: str, en: str) -> None:
    assert format_date(day, "ro", with_weekday=True) == ro
    assert format_date(day, "en", with_weekday=True) == en


@pytest.mark.parametrize(
    "value",
    [
        datetime(2026, 6, 14, 21, 30, tzinfo=UTC),  # already 15 June in Bucharest
        datetime(2026, 6, 15, 12, 0),  # noqa: DTZ001 (a naive datetime is rejected too)
        "2026-06-15",
    ],
)
def test_format_date_rejects_datetimes_and_strings(value: object) -> None:
    with pytest.raises(TypeError, match="date"):
        format_date(value, "ro")  # type: ignore[arg-type]


def test_romanian_names_use_comma_below_diacritics_and_nfc() -> None:
    texts = [format_date(date(2026, month, 1), "ro") for month in range(1, 13)]
    texts += [format_date(date(2026, 6, 15 + d), "ro", with_weekday=True) for d in range(7)]

    for text in texts:
        assert not CEDILLAS & set(text), text
        assert unicodedata.normalize("NFC", text) == text
    assert "marți" in texts[13]
    assert "sâmbătă" in texts[17]


# ── language (all three formatters) ─────────────────────────────────────────────────────

FORMATTERS: list[Callable[[str], str]] = [
    lambda lang: format_money(1, lang),
    lambda lang: format_pct(0.5, lang),
    lambda lang: format_date(date(2026, 6, 15), lang),
]


@pytest.mark.parametrize("formatter", FORMATTERS, ids=["money", "pct", "date"])
@pytest.mark.parametrize("lang", ["fr", "", "RO", "ro ", "en-GB"])
def test_every_formatter_rejects_an_unknown_language(
    formatter: Callable[[str], str], lang: str
) -> None:
    with pytest.raises(ValueError, match="language"):
        formatter(lang)


# ── C1.4: one rounding rule with storage, F2's languages ────────────────────────────────


def test_format_money_rounds_with_the_domain_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    # Display and storage can never round differently: format_money delegates the rounding to
    # app.domain.money.quantize_cents (the rule to_money uses), it doesn't reimplement it.
    calls: list[Decimal] = []

    def spy(value: Decimal) -> Decimal:
        calls.append(value)
        return Decimal("1.23")

    monkeypatch.setattr(format_module, "quantize_cents", spy)

    assert format_money(Decimal("5.005"), "ro") == "1,23 lei"
    assert calls == [Decimal("5.005")]


@given(st.integers(-(10**35), 10**35), st.integers(10, 45))
def test_format_money_shows_exactly_quantize_cents(n: int, k: int) -> None:
    amount = Decimal(f"{n}E-{k}")
    shown = format_money(amount, "en").removesuffix(" lei").replace(",", "")

    assert Decimal(shown) == quantize_cents(amount)


@pytest.mark.parametrize("formatter", FORMATTERS, ids=["money", "pct", "date"])
@pytest.mark.parametrize("lang", list(Language), ids=lambda lang: lang.value)
def test_every_formatter_accepts_every_language_of_f2(
    formatter: Callable[[str], str], lang: Language
) -> None:
    assert formatter(lang) == formatter(lang.value)


# ── C1.4 addition: the Romanian sentence form ("80 de lei", boss decision) ──────────────


def _needs_de(whole: int) -> bool:
    """Romanian grammar, stated the other way round: no "de" for 0-19 or when the last two
    digits are 01-19 (an independent oracle for the implementation's rule)."""
    return not (whole < 20 or 1 <= whole % 100 <= 19)


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (1, "1 leu"),  # singular
        (19, "19 lei"),
        (20, "20 de lei"),
        (99, "99 de lei"),
        (100, "100 de lei"),
        (101, "101 lei"),
        (119, "119 lei"),
        (120, "120 de lei"),
        (1000, "1.000 de lei"),
        (1019, "1.019 lei"),
        (1020, "1.020 de lei"),
        (Decimal("30.40"), "30,40 lei"),  # decimals: no "de"
        (0, "0 lei"),
        (2, "2 lei"),
        (80, "80 de lei"),
        (240, "240 de lei"),
        (1500, "1.500 de lei"),
        (10**6, "1.000.000 de lei"),
        (Decimal("1.00"), "1 leu"),
        (Decimal("1.50"), "1,50 lei"),
        (Decimal("20.50"), "20,50 lei"),
        (Decimal("19.995"), "20 de lei"),  # rounded to the cent first: a whole 20
        (-1, "-1 leu"),
        (-19, "-19 lei"),
        (-20, "-20 de lei"),
        (-1020, "-1.020 de lei"),
        (Decimal("-30.4"), "-30,40 lei"),
        (Decimal("-0.004"), "0 lei"),
    ],
)
def test_format_money_in_sentence_puts_de_before_lei_by_the_romanian_rule(
    amount: Decimal | int, expected: str
) -> None:
    assert format_money_in_sentence(amount, "ro") == expected


def test_the_sentence_rule_matches_romanian_grammar_for_every_whole_amount_to_2500() -> None:
    for whole in range(2501):
        text = format_money_in_sentence(whole, "ro")
        if whole == 1:
            assert text == "1 leu"
        else:
            assert text.endswith(" de lei") is _needs_de(whole), text


@given(st.decimals(min_value=Decimal("-1e9"), max_value=Decimal("1e9"), places=2))
def test_the_sentence_form_shows_the_same_number_as_the_display_form(amount: Decimal) -> None:
    display = format_money(amount, "ro").removesuffix(" lei")
    sentence = format_money_in_sentence(amount, "ro")

    assert sentence in {f"{display} lei", f"{display} de lei", f"{display} leu"}
    assert format_money_in_sentence(amount, "en") == format_money(amount, "en")


def test_the_display_form_is_unchanged() -> None:
    # The UI form the spec pins stays "500 lei" (no "de").
    assert format_money(500, "ro") == "500 lei"
    assert format_money(1, "ro") == "1 lei"


@pytest.mark.parametrize("amount", [30.4, True, "30.4"])
def test_format_money_in_sentence_rejects_non_money(amount: object) -> None:
    with pytest.raises(TypeError, match="to_money"):
        format_money_in_sentence(amount, "ro")  # type: ignore[arg-type]


@pytest.mark.parametrize("lang", ["fr", "", "RO"])
def test_format_money_in_sentence_rejects_an_unknown_language(lang: str) -> None:
    with pytest.raises(ValueError, match="language"):
        format_money_in_sentence(80, lang)


@pytest.mark.parametrize("lang", list(Language), ids=lambda lang: lang.value)
def test_format_money_in_sentence_accepts_every_language_of_f2(lang: Language) -> None:
    assert format_money_in_sentence(80, lang) == format_money_in_sentence(80, lang.value)
