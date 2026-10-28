"""Money helpers: `Decimal` RON with 2 decimals, rounded half-up (work-breakdown 0.3)."""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def to_money(x: Decimal | int | float | str) -> Decimal:
    """Round to 2 decimals, half-up. Floats go through `str`, so 1.005 → 1.01."""
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def split_share(total: Decimal, people: int) -> tuple[Decimal, Decimal]:
    """(own share, everybody else's share); the two always add up to `total` exactly."""
    if people <= 0:
        raise ValueError("people must be at least 1")
    total = to_money(total)
    if total < 0:
        raise ValueError("total must not be negative")
    own = to_money(total / people)
    return own, total - own


def share_each(others: Decimal, n: int) -> Decimal:
    """What each of the `n` other people owes (for the payment request card)."""
    if n <= 0:
        raise ValueError("n must be at least 1")
    return to_money(to_money(others) / n)
