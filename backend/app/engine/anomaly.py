"""E7 minimum (danutu's task, written by David G.'s C5-C7 agent under D42): anomaly features.

Arch 5.3.4 step 4, pure:
    z = (amount - expected_median) / (1.4826 · MAD)    (MAD = 0 → 0.25 · expected_median)
    stat = clip(z / 4, 0, 1)
    novelty = 1 if the merchant and the category are unseen in 90 days, 0.5 if only the
              merchant is, else 0 (seen exactly 90 days before counts as seen)
    materiality = clip(amount / (0.10 · monthly_disposable), 0, 1); disposable ≤ 0 → 1
"""

from collections.abc import Iterable
from datetime import timedelta
from decimal import Decimal
from typing import Final

from app.domain.enums import Direction
from app.domain.models import Baseline, TxView
from app.domain.results import AnomalyFeatures
from app.engine.baselines import effective_mad
from app.i18n.text import fold

MAD_TO_SIGMA: Final = Decimal("1.4826")
NOVELTY_DAYS: Final = 90
_MATERIAL_SHARE: Final = Decimal("0.10")


def _clip01(value: float) -> float:
    return min(1.0, max(0.0, value))


def merchant_key(tx: TxView) -> str:
    """The merchant slug, else the folded name: how two transactions are "the same merchant"."""
    return tx.merchant_id or fold(tx.merchant or tx.merchant_raw).strip()


def z_score(amount: Decimal, baseline: Baseline | None) -> float:
    if baseline is None or baseline.expected_median <= 0:
        return 0.0
    spread = MAD_TO_SIGMA * effective_mad(baseline)
    return float((amount - baseline.expected_median) / spread)


def novelty(tx: TxView, history: Iterable[TxView]) -> float:
    since = tx.occurred_at - timedelta(days=NOVELTY_DAYS)
    key = merchant_key(tx)
    merchant_seen = category_seen = False
    for past in history:
        if past.id == tx.id or past.direction is not Direction.DEBIT:
            continue
        if not since.date() <= past.occurred_at.date() <= tx.occurred_at.date():
            continue
        merchant_seen = merchant_seen or merchant_key(past) == key
        category_seen = category_seen or (
            past.category is not None and past.category == tx.category
        )
    if merchant_seen:
        return 0.0
    return 0.5 if category_seen else 1.0


def materiality(amount: Decimal, monthly_disposable: Decimal) -> float:
    if monthly_disposable <= 0:
        return 1.0
    return _clip01(float(amount / (_MATERIAL_SHARE * monthly_disposable)))


def anomaly_features(
    tx: TxView,
    baseline: Baseline | None,
    history: Iterable[TxView],
    monthly_disposable: Decimal,
) -> AnomalyFeatures:
    """z, stat, novelty and materiality of `tx` against the person's own baseline."""
    z = z_score(tx.amount, baseline)
    return AnomalyFeatures(
        z=z,
        stat=_clip01(z / 4),
        novelty=novelty(tx, history),
        materiality=materiality(tx.amount, monthly_disposable),
    )
