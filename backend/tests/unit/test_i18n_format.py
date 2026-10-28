"""C1.1: RO / EN money, percent and date formats (work-breakdown C1, B13; D48 defaults).

RO `10.000 lei` · `30,40 lei` · `-30,40 lei` · `100 lei`; EN `10,000 lei` · `30.40 lei`.
Whole amounts drop the decimals; money is Decimal or int, never float.
"""

import re
import unicodedata
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.i18n.format import format_date, format_money, format_pct

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
    "amount",
    [Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"), Decimal("-Infinity"), Decimal("1E+30")],
)
def test_format_money_rejects_amounts_that_are_not_a_finite_sum(amount: Decimal) -> None:
    with pytest.raises(ValueError, match="amount"):
        format_money(amount, "ro")


@given(
    st.decimals(
        min_value=Decimal("-1e12"),
        max_value=Decimal("1e12"),
        places=4,
        allow_nan=False,
        allow_infinity=False,
    ),
    st.sampled_from(["ro", "en"]),
)
def test_format_money_shows_exactly_the_rounded_amount(amount: Decimal, lang: str) -> None:
    thousands, decimal_sep = SEPARATORS[lang]
    text = format_money(amount, lang)

    assert text.endswith(" lei")
    number = text.removesuffix(" lei")
    integer, _, fraction = number.removeprefix("-").partition(decimal_sep)
    groups = integer.split(thousands)
    assert 1 <= len(groups[0]) <= 3
    assert all(len(group) == 3 for group in groups[1:])
    assert fraction == "" or (len(fraction) == 2 and fraction != "00")
    parsed = Decimal(number.replace(thousands, "").replace(decimal_sep, "."))
    assert parsed == amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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


@pytest.mark.parametrize("value", [float("nan"), float("inf"), Decimal("NaN"), 1e300])
def test_format_pct_rejects_values_that_cannot_be_shown(value: float | Decimal) -> None:
    with pytest.raises(ValueError, match="value"):
        format_pct(value, "ro")


@pytest.mark.parametrize("value", [True, "0.5", None])
def test_format_pct_rejects_non_numbers(value: object) -> None:
    with pytest.raises(TypeError):
        format_pct(value, "ro")  # type: ignore[arg-type]


@pytest.mark.parametrize("decimals", [-1, 3, True])
def test_format_pct_accepts_zero_to_two_decimals_only(decimals: int) -> None:
    with pytest.raises(ValueError, match="decimals"):
        format_pct(0.5, "ro", decimals=decimals)


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
