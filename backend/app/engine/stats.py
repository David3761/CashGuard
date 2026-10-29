"""Small robust statistics on money (pure, `Decimal`)."""

from collections.abc import Sequence
from decimal import Decimal
from hashlib import blake2b
from statistics import median

DAYS_PER_MONTH = Decimal("30.4375")  # 365.25 / 12


def median_and_mad(values: Sequence[Decimal]) -> tuple[Decimal, Decimal]:
    """Median and median absolute deviation (MAD); `(0, 0)` when there are no values."""
    if not values:
        return Decimal(0), Decimal(0)
    mid = median(values)
    return mid, median([abs(v - mid) for v in values])


def blend(n: int, personal: Decimal, prior: Decimal, k: int = 5) -> Decimal:
    """(n·personal + k·prior) / (n + k): the prior dominates while there's little personal
    history."""
    if n < 0 or k < 0 or n + k == 0:
        raise ValueError("n and k must be ≥ 0 and not both 0")
    return (n * personal + k * prior) / (n + k)


def monthly_rate(total: Decimal, span_days: int) -> Decimal:
    """`total` spent over `span_days`, scaled to an average month; 0 when there's no span."""
    if span_days < 0:
        raise ValueError("span_days must be ≥ 0")
    return total * DAYS_PER_MONTH / span_days if span_days else Decimal(0)


def stable_seed(*parts: object) -> int:
    """64-bit seed from `parts`, identical in every process (never Python's `hash()`, which is
    salted)."""
    key = "|".join(str(p) for p in parts).encode()
    return int.from_bytes(blake2b(key, digest_size=8).digest(), "big")
