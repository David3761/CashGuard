"""Anomaly features for one transaction (arch 5.3.4 step 4). Pure, no DB, no clock.

Money comes in as `Decimal`; the features are scores in [0, 1] and go out as `float`.
`context.evaluate` combines them: raw = 0.5·stat + 0.2·novelty + 0.3·materiality.
"""

import math
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.domain.models import Baseline, FixedCost, IncomeSource, TxView
from app.domain.results import AnomalyFeatures

BUCHAREST = ZoneInfo("Europe/Bucharest")
MAD_TO_SIGMA = Decimal("1.4826")
MAD_FALLBACK_SHARE = Decimal("0.25")
Z_FOR_FULL_STAT = 4.0
NOVELTY_WINDOW = timedelta(days=90)
MATERIAL_SHARE = Decimal("0.10")


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, x))


def robust_z(amount: Decimal, expected_median: Decimal, mad: Decimal) -> float:
    """(amount − median) / (1.4826 · MAD), with MAD = 0 → 0.25 · median.

    With no scale at all (median and MAD both 0) any spending is maximally unusual: `inf`, or 0 for 0 lei.
    """
    if amount < 0 or expected_median < 0 or mad < 0:
        raise ValueError("amount, expected_median and mad must be ≥ 0")
    spread = mad if mad > 0 else MAD_FALLBACK_SHARE * expected_median
    deviation = amount - expected_median
    if spread == 0:
        return math.inf if deviation > 0 else 0.0
    return float(deviation / (MAD_TO_SIGMA * spread))


def stat_score(z: float) -> float:
    """clip(z / 4, 0, 1): below the median is never an anomaly, 4 robust sigmas or more is the maximum."""
    if math.isnan(z):
        raise ValueError("z must not be NaN")
    return _clip01(z / Z_FOR_FULL_STAT)


def novelty(merchant_last_seen: date | None, category_last_seen: date | None, on_date: date) -> float:
    """1 if neither the merchant nor the category was seen, 0.5 if only the merchant is new, else 0.

    "Seen" means a previous transaction in the 90 days up to `on_date`, both bounds inclusive
    (90 days ago is seen, 91 is not). Pass history from *before* this transaction, without it.
    """
    for seen in (merchant_last_seen, category_last_seen):
        if seen is not None and seen > on_date:
            raise ValueError("last seen dates must not be after the transaction date")

    def recent(seen: date | None) -> bool:
        return seen is not None and on_date - seen <= NOVELTY_WINDOW

    if recent(merchant_last_seen):
        return 0.0
    return 0.5 if recent(category_last_seen) else 1.0


def materiality(amount: Decimal, monthly_disposable: Decimal) -> float:
    """clip(amount / (10% of monthly disposable), 0, 1); disposable ≤ 0 → 1 (any spending matters)."""
    if amount < 0:
        raise ValueError("amount must be ≥ 0")
    if monthly_disposable <= 0:
        return 1.0
    return _clip01(float(amount / (MATERIAL_SHARE * monthly_disposable)))


def monthly_disposable(income_sources: Iterable[IncomeSource], fixed_costs: Iterable[FixedCost]) -> Decimal:
    """Monthly income − monthly fixed costs (arch 5.3.4: disposable = income − fixed costs)."""
    return sum((s.amount for s in income_sources), Decimal(0)) - sum(
        (c.amount for c in fixed_costs), Decimal(0)
    )


def anomaly_features(
    tx: TxView, baseline: Baseline | None, history: Iterable[TxView], monthly_disposable: Decimal
) -> AnomalyFeatures:
    """The three features for `tx` against the person's baseline and history (before `tx`, without it).

    No baseline for the category → median and MAD 0, so any spending scores stat 1.
    """
    on = tx.occurred_at.astimezone(BUCHAREST).date()
    earlier = [h for h in history if h.id != tx.id and h.occurred_at < tx.occurred_at]

    def last_seen(match: Iterable[TxView]) -> date | None:
        return max((h.occurred_at.astimezone(BUCHAREST).date() for h in match), default=None)

    merchant_seen = last_seen(
        h for h in earlier if tx.merchant_id is not None and h.merchant_id == tx.merchant_id
    )
    category_seen = last_seen(h for h in earlier if h.category == tx.category)
    median = baseline.expected_median if baseline is not None else Decimal(0)
    mad = baseline.personal_mad if baseline is not None else Decimal(0)
    z = robust_z(tx.amount, median, mad)
    return AnomalyFeatures(
        z=z,
        stat=stat_score(z),
        novelty=novelty(merchant_seen, category_seen, on),
        materiality=materiality(tx.amount, monthly_disposable),
    )
