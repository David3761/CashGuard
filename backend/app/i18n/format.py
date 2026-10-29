"""RO / EN number, percent and date formats for user-facing text (C1.1, D48).

    ro: 10.000 lei · 30,40 lei · -30,40 lei · 77% · 12,5% · 15 iunie 2026 · luni, 15 iunie 2026
    en: 10,000 lei · 30.40 lei · -30.40 lei · 77% · 12.5% · 15 June 2026 · Monday, 15 June 2026

Whole amounts drop the decimals; money is Decimal or int, never float. Plain Python, no `locale`
or Babel (process-global and machine-dependent). The spoken forms ("1 leu", "500 de lei") are
A11's `speak_text`, not this module's.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Context, Decimal, InvalidOperation
from types import MappingProxyType
from typing import Final

from app.domain.enums import Language
from app.domain.money import quantize_cents


@dataclass(frozen=True, slots=True)
class _Locale:
    thousands: str
    decimal: str
    months: tuple[str, ...]
    weekdays: tuple[str, ...]  # Monday first, as date.weekday()
    _table: dict[int, int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        # Built once per language: Python's "," / "." → this language's separators.
        object.__setattr__(self, "_table", str.maketrans(",.", self.thousands + self.decimal))

    def number(self, text: str) -> str:
        """Python's `format(x, ",.2f")` text ("1,234.50") with this language's separators."""
        return text.translate(self._table)


_MONTHS_RO: Final = ("ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie",
                     "august", "septembrie", "octombrie", "noiembrie", "decembrie")  # fmt: skip
_MONTHS_EN: Final = ("January", "February", "March", "April", "May", "June", "July", "August",
                     "September", "October", "November", "December")  # fmt: skip
_WEEKDAYS_RO: Final = ("luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică")
_WEEKDAYS_EN: Final = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
                       "Sunday")  # fmt: skip
_LOCALES: Final = MappingProxyType(
    {
        Language.RO: _Locale(thousands=".", decimal=",", months=_MONTHS_RO, weekdays=_WEEKDAYS_RO),
        Language.EN: _Locale(thousands=",", decimal=".", months=_MONTHS_EN, weekdays=_WEEKDAYS_EN),
    }
)
# An explicit context, so the result never depends on the thread's decimal context.
_CONTEXT: Final = Context(prec=28, rounding=ROUND_HALF_UP, traps=[InvalidOperation])


def _locale(lang: str) -> _Locale:
    try:
        return _LOCALES[Language(lang)]
    except ValueError:
        raise ValueError(f"unsupported language {lang!r}: expected 'ro' or 'en'") from None


def _shift(value: Decimal, places: int) -> Decimal:
    """value * 10**places, exactly: no context, so no rounding and no overflow (finite only)."""
    sign, digits, exponent = value.as_tuple()
    return Decimal((sign, digits, int(exponent) + places))


def _round_half_up(value: Decimal, exponent: Decimal, what: str, given: object) -> Decimal:
    """format_pct's one rounding step (finite values only); errors name the caller's `given`."""
    try:
        rounded = value.quantize(exponent, rounding=ROUND_HALF_UP, context=_CONTEXT)
    except InvalidOperation:
        raise ValueError(f"the {what} is too large to format: {given!r}") from None
    return abs(rounded) if rounded == 0 else rounded  # never "-0"


def _cents(amount: Decimal | int, caller: str) -> Decimal:
    """`amount` rounded by `app.domain.money.quantize_cents`, the rule storage uses (`to_money`),
    so the shown and the stored cents can't differ; never -0.00; any amount below 10^26."""
    if isinstance(amount, bool) or not isinstance(amount, Decimal | int):
        raise TypeError(
            f"{caller} takes a Decimal or an int, not {type(amount).__name__}: "
            "round money with to_money() first"
        )
    value = Decimal(amount)
    if not value.is_finite():
        raise ValueError(f"the amount must be a finite number, got {amount!r}")
    try:
        return quantize_cents(value)
    except ValueError:
        raise ValueError(f"the amount is too large to format: {amount!r}") from None


def _amount_text(cents: Decimal, locale: _Locale) -> str:
    return locale.number(format(cents, ",.2f").removesuffix(".00"))  # whole amounts: no decimals


def format_money(amount: Decimal | int, lang: str) -> str:
    """The display form (UI, cards): RO `10.000 lei` / `30,40 lei` / `500 lei`, EN `10,000 lei` /
    `30.40 lei`. Whole amounts without decimals; always "lei"."""
    locale = _locale(lang)
    return f"{_amount_text(_cents(amount, 'format_money'), locale)} lei"


def format_money_in_sentence(amount: Decimal | int, lang: str) -> str:
    """The form inside a Romanian sentence (templates, notifications, speak_text): "de" before
    "lei" from 20 on, when the last two digits are 00 or 20-99 (`80 de lei`, `1.500 de lei`,
    `100 de lei`), but `19 lei`, `101 lei`, `30,40 lei` (decimals); `1 leu` (singular).
    English is the display form (`80 lei`)."""
    locale = _locale(lang)
    cents = _cents(amount, "format_money_in_sentence")
    text = _amount_text(cents, locale)
    if Language(lang) is not Language.RO or cents != cents.to_integral_value():
        return f"{text} lei"
    whole = abs(int(cents))
    if whole == 1:
        return f"{text} leu"
    needs_de = whole >= 20 and (whole % 100 == 0 or whole % 100 >= 20)
    return f"{text} de lei" if needs_de else f"{text} lei"


def format_pct(value: Decimal | float | int, lang: str, *, decimals: int = 0) -> str:
    """A ratio as a percent: 0.77 → `77%`; `decimals=1`: 0.125 → RO `12,5%`, EN `12.5%`."""
    locale = _locale(lang)
    if type(decimals) is not int or decimals not in (0, 1, 2):  # not True, 1.0, Decimal(1)
        raise ValueError(f"decimals must be the int 0, 1 or 2, got {decimals!r}")
    if isinstance(value, bool) or not isinstance(value, Decimal | float | int):
        raise TypeError(f"format_pct takes a Decimal, float or int, not {type(value).__name__}")
    ratio = Decimal(str(value)) if isinstance(value, float) else Decimal(value)  # str: 0.285 → 29%
    if not ratio.is_finite():
        raise ValueError(f"the value must be a finite number, got {value!r}")
    percent = _round_half_up(_shift(ratio, 2), _shift(Decimal(1), -decimals), "value", value)
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
