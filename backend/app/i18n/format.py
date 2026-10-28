"""RO / EN number, percent and date formats for user-facing text (C1.1, D48).

    ro: 10.000 lei · 30,40 lei · -30,40 lei · 77% · 12,5% · 15 iunie 2026 · luni, 15 iunie 2026
    en: 10,000 lei · 30.40 lei · -30.40 lei · 77% · 12.5% · 15 June 2026 · Monday, 15 June 2026

Whole amounts drop the decimals; money is Decimal or int, never float. Plain Python, no `locale`
or Babel (process-global and machine-dependent). The spoken forms ("1 leu", "500 de lei") are
A11's `speak_text`, not this module's.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Context, Decimal, InvalidOperation
from types import MappingProxyType
from typing import Final


@dataclass(frozen=True, slots=True)
class _Locale:
    thousands: str
    decimal: str
    months: tuple[str, ...]
    weekdays: tuple[str, ...]  # Monday first, as date.weekday()

    def number(self, text: str) -> str:
        """Python's `format(x, ",.2f")` text ("1,234.50") with this language's separators."""
        return text.translate(str.maketrans(",.", self.thousands + self.decimal))


_MONTHS_RO: Final = ("ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie",
                     "august", "septembrie", "octombrie", "noiembrie", "decembrie")  # fmt: skip
_MONTHS_EN: Final = ("January", "February", "March", "April", "May", "June", "July", "August",
                     "September", "October", "November", "December")  # fmt: skip
_WEEKDAYS_RO: Final = ("luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică")
_WEEKDAYS_EN: Final = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
                       "Sunday")  # fmt: skip
_LOCALES: Final = MappingProxyType(
    {
        "ro": _Locale(thousands=".", decimal=",", months=_MONTHS_RO, weekdays=_WEEKDAYS_RO),
        "en": _Locale(thousands=",", decimal=".", months=_MONTHS_EN, weekdays=_WEEKDAYS_EN),
    }
)
_CENT: Final = Decimal("0.01")
# An explicit context, so the result never depends on the thread's decimal context.
_CONTEXT: Final = Context(prec=28, rounding=ROUND_HALF_UP, traps=[InvalidOperation])


def _locale(lang: str) -> _Locale:
    try:
        return _LOCALES[lang]
    except (KeyError, TypeError):
        raise ValueError(f"unsupported language {lang!r}: expected 'ro' or 'en'") from None


def _round_half_up(value: Decimal, exponent: Decimal, what: str) -> Decimal:
    if not value.is_finite():
        raise ValueError(f"the {what} must be a finite number, got {value}")
    try:
        rounded = value.quantize(exponent, rounding=ROUND_HALF_UP, context=_CONTEXT)
    except InvalidOperation:
        raise ValueError(f"the {what} is too large to format: {value}") from None
    return abs(rounded) if rounded == 0 else rounded  # never "-0"


def format_money(amount: Decimal | int, lang: str) -> str:
    """RO `10.000 lei` / `30,40 lei`, EN `10,000 lei` / `30.40 lei`: half-up to the cent (the
    same rule as `to_money`), and whole amounts without decimals."""
    locale = _locale(lang)
    if isinstance(amount, bool) or not isinstance(amount, Decimal | int):
        raise TypeError(
            f"format_money takes a Decimal or an int, not {type(amount).__name__}: "
            "round money with to_money() first"
        )
    cents = _round_half_up(Decimal(amount), _CENT, "amount")
    return f"{locale.number(format(cents, ',.2f').removesuffix('.00'))} lei"


def format_pct(value: Decimal | float | int, lang: str, *, decimals: int = 0) -> str:
    """A ratio as a percent: 0.77 → `77%`; `decimals=1`: 0.125 → RO `12,5%`, EN `12.5%`."""
    locale = _locale(lang)
    if isinstance(decimals, bool) or decimals not in (0, 1, 2):
        raise ValueError(f"decimals must be 0, 1 or 2, got {decimals!r}")
    if isinstance(value, bool) or not isinstance(value, Decimal | float | int):
        raise TypeError(f"format_pct takes a Decimal, float or int, not {type(value).__name__}")
    ratio = Decimal(str(value)) if isinstance(value, float) else Decimal(value)  # str: 0.285 → 29%
    if not ratio.is_finite():
        raise ValueError(f"the value must be a finite number, got {value}")
    percent = _round_half_up(
        ratio.scaleb(2, context=_CONTEXT), Decimal(1).scaleb(-decimals), "value"
    )
    return f"{locale.number(format(percent, f',.{decimals}f'))}%"


def format_date(day: date, lang: str, *, with_year: bool = True, with_weekday: bool = False) -> str:
    """RO `15 iunie 2026` / `luni, 15 iunie 2026`, EN `15 June 2026` / `Monday, 15 June 2026`."""
    locale = _locale(lang)
    if isinstance(day, datetime) or not isinstance(day, date):
        raise TypeError(
            f"format_date takes a date, not {type(day).__name__}: convert a timestamp to its "
            "Bucharest date with app.clock first"
        )
    text = f"{day.day} {locale.months[day.month - 1]}"
    if with_year:
        text = f"{text} {day.year}"
    if with_weekday:
        text = f"{locale.weekdays[day.weekday()]}, {text}"
    return text
