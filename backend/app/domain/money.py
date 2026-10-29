"""Money helpers and the `Money` field type (work-breakdown 0.3 rule 2 and F2; arch 4.3, 9.1).

- Money is a `Decimal` rounded **half-up to the cent** (ties away from zero: 1.005 -> 1.01,
  -2.675 -> -2.68) by `quantize_cents`, the one rounding rule (C1's `format_money` uses it too).
  A rounded zero is always `0.00`, never `-0.00`.
- Inputs are read **exactly**: a Decimal or an int as is, a float through its shortest repr (so
  1.005 is 1.005, not the 1.00499... that `Decimal(1.005)` would give), and a string only in
  **machine format**: written like a JSON number, ASCII only, at most 64 characters (no spaces,
  `_`, `+`, other scripts' digits or thousands separators). "30,40" is rejected, and the Romanian
  "10.000" (ten thousand) reads as 10.00, so user-formatted text must never reach these helpers.
- Every operation runs in this module's own decimal context, so a caller's thread- or task-local
  context (another precision or rounding) can't change a result.
- Amounts must fit `NUMERIC(12,2)` (arch 4.3): |amount| < 10^10, else `ValueError`.
- In JSON (`model_dump(mode="json")`, `model_dump_json()`, FastAPI responses) a `Money` field is a
  JSON **number** (arch 9.1). JSON numbers keep no trailing zeros, so 31.20 is written `31.2`; the
  app formats amounts for display. This is exact: an amount has at most 12 significant digits and
  a float's shortest repr keeps 15, so reading the JSON back gives the same `Decimal`.
- Reading JSON: pydantic's own JSON parser (and `json.loads` by default) turn a JSON number into
  the nearest float before any validator runs, so a number with more than ~15 significant digits
  is rounded twice (0.0049999999999999999 -> 0.005 -> 0.01). `parse_json` reads every number
  exactly; validate its result with `model_validate`.
"""

import json
import re
from decimal import ROUND_HALF_UP, Context, Decimal, DivisionByZero, InvalidOperation, Overflow
from typing import Annotated, Final, NamedTuple, NoReturn

from pydantic import BeforeValidator, PlainSerializer, WithJsonSchema

MoneyLike = Decimal | int | float | str
CENT: Final = Decimal("0.01")
MAX_ABS: Final = Decimal("10000000000")
"""|amount| must stay below this: NUMERIC(12,2) has 10 digits before the decimal point."""
MAX_DIGITS: Final = 28
"""`to_decimal` keeps at most this many significant digits and decimal places (the context's)."""

_CONTEXT: Final = Context(
    prec=28, rounding=ROUND_HALF_UP, traps=[InvalidOperation, DivisionByZero, Overflow]
)
_MACHINE_NUMBER: Final = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
_MAX_TEXT: Final = 64
_MAX_INT_BITS: Final = 128


class Split(NamedTuple):
    """A total split between the user (`own`) and the others; own + others == total, exactly."""

    own: Decimal
    others: Decimal


def _shown(value: object) -> str:
    """A short repr for error messages: never a huge input in a log or in Claude's context."""
    try:
        text = repr(value)
    except ValueError:  # an int too large for str()
        return f"<{type(value).__name__} too large to show>"
    return text if len(text) <= 40 else f"{text[:37]}…"


def _exact(value: object, what: str) -> Decimal:
    """`value` as an exact, finite Decimal (see the module docstring); `ValueError` otherwise."""
    if isinstance(value, Decimal):
        exact = value
    elif isinstance(value, bool):  # an int, but never a number here
        raise ValueError(f"not a {what}: {value!r}")
    elif isinstance(value, int):
        if value.bit_length() > _MAX_INT_BITS:  # far out of range; str() of it may even fail
            raise ValueError(f"{what} out of range: {_shown(value)}")
        exact = Decimal(value)
    elif isinstance(value, float):
        exact = Decimal(repr(value))  # the shortest repr: 1.005, not 1.00499...
    elif isinstance(value, str):
        if len(value) > _MAX_TEXT or not _MACHINE_NUMBER.fullmatch(value):
            raise ValueError(f"not a {what} in machine format (like -1234.56): {_shown(value)}")
        try:
            exact = Decimal(value)
        except InvalidOperation:  # an exponent beyond what Decimal can hold
            raise ValueError(f"{what} out of range: {_shown(value)}") from None
    else:
        raise ValueError(f"not a {what}: {_shown(value)}")
    if not exact.is_finite():  # also the NaN a caller context without traps would produce
        raise ValueError(f"not a finite {what}: {_shown(value)}")
    return exact


def _count(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, got {_shown(value)}")
    if value < 1:
        raise ValueError(f"{name} must be ≥ 1, got {value}")
    return value


def quantize_cents(value: Decimal) -> Decimal:
    """`value` rounded half-up to the cent in this module's context, never `-0.00`.

    The one rounding rule for money and for displaying it. There's no money range here (display
    code formats larger amounts too), only the context's 28 digits: |value| < 10^26.
    """
    if not isinstance(value, Decimal):
        raise TypeError(f"quantize_cents takes a Decimal, not {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"cannot round a non-finite value to the cent: {_shown(value)}")
    try:
        cents = value.quantize(CENT, rounding=ROUND_HALF_UP, context=_CONTEXT)
    except InvalidOperation:
        raise ValueError(f"too large to round to the cent (28 digits): {_shown(value)}") from None
    return cents.copy_abs() if cents.is_zero() else cents


def to_decimal(value: MoneyLike) -> Decimal:
    """`value` as an exact Decimal, not rounded (for multipliers and ratios); never `-0`.

    `ValueError` outside |x| < 10^10 or beyond 28 significant digits / decimal places, so later
    arithmetic can't overflow.
    """
    exact = _exact(value, "number")
    if exact.copy_abs() >= MAX_ABS:
        raise ValueError(f"number out of range (|x| < 10^10): {_shown(value)}")
    _, digits, exponent = exact.as_tuple()
    places = int(exponent)
    if len(digits) > MAX_DIGITS or places < -MAX_DIGITS:
        raise ValueError(f"number too precise (28 digits or places at most): {_shown(value)}")
    return Decimal((0, (0,), min(places, 0))) if exact.is_zero() else exact


def to_money(value: MoneyLike) -> Decimal:
    """`value` rounded half-up to the cent; `ValueError` for non-numbers and |amount| ≥ 10^10."""
    exact = _exact(value, "money amount")
    out_of_range = f"money amount out of range (|amount| < 10^10): {_shown(value)}"
    try:
        cents = quantize_cents(exact)
    except ValueError:  # more digits than the context holds: far beyond the range anyway
        raise ValueError(out_of_range) from None
    if cents.copy_abs() >= MAX_ABS:
        raise ValueError(out_of_range)
    return cents


def split_share(total: MoneyLike, people: int) -> Split:
    """The user's share of `total` paid for `people` (them included) and the others' share.

    The total is rounded to the cent first; own = total / people rounded half-up; others =
    total - own, so the two always add up exactly (500 for 3 -> 166.67 + 333.33).
    """
    count = _count(people, "people")
    amount = to_money(total)
    if amount < 0:
        raise ValueError(f"total must not be negative, got {amount}")
    own = to_money(_CONTEXT.divide(amount, count))
    return Split(own=own, others=_CONTEXT.subtract(amount, own))


def share_each(others: MoneyLike, count: int) -> Decimal:
    """What each of `count` people owes of `others`, rounded half-up. For display only: the
    receivable keeps the exact total (2 x 166.67 = 333.34, while the total stays 333.33)."""
    people = _count(count, "count")
    amount = to_money(others)
    if amount < 0:
        raise ValueError(f"others must not be negative, got {amount}")
    return to_money(_CONTEXT.divide(amount, people))


MAX_JSON_DEPTH: Final = 64
"""parse_json refuses deeper JSON (domain data is a few levels deep; this stops nesting bombs)."""


def _depth(value: object) -> int:
    deepest, stack = 0, [(value, 1)]
    while stack:
        node, level = stack.pop()
        if isinstance(node, dict | list):
            deepest = max(deepest, level)
            stack.extend(
                (child, level + 1) for child in (node.values() if isinstance(node, dict) else node)
            )
    return deepest


def _no_constant(name: str) -> NoReturn:
    raise ValueError(f"JSON {name} is not a number")


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON has a duplicate key {_shown(key)}")
        result[key] = value
    return result


def parse_json(data: str | bytes | bytearray) -> object:
    """JSON with every number read exactly (decimals as `Decimal`); NaN, Infinity and duplicate
    keys rejected (the stdlib would silently keep the last value; C1's loader rule, H-7).

    Use it, then `model_validate`, wherever JSON carrying money is parsed (see the module
    docstring for why pydantic's own JSON parsing isn't exact). `DomainModel.model_validate_json`
    does exactly that.
    """
    try:
        parsed: object = json.loads(
            data,
            parse_float=Decimal,
            parse_constant=_no_constant,
            object_pairs_hook=_no_duplicate_keys,
        )
    except RecursionError:
        raise ValueError(f"JSON nested deeper than {MAX_JSON_DEPTH} levels") from None
    if _depth(parsed) > MAX_JSON_DEPTH:
        raise ValueError(f"JSON nested deeper than {MAX_JSON_DEPTH} levels")
    return parsed


def decimal_to_json(value: Decimal) -> float:
    """The JSON number for a Decimal (exact for every storable amount, see the module docstring)."""
    return float(value)


Money = Annotated[
    Decimal,
    BeforeValidator(to_money),
    PlainSerializer(decimal_to_json, return_type=float, when_used="json"),
    WithJsonSchema({"type": "number"}),
]
"""A money field: validated with `to_money`, a Decimal in Python, a number in JSON."""
