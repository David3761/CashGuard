"""Transactions: the queue and the annotation (B3 step 2)."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm
from app.domain.enums import AnnotationSource, Beneficiary, Category, Purpose, TransactionStatus
from app.domain.results import Evaluation


async def get(db: AsyncSession, user_id: int, tx_id: int) -> dm.TxView:
    """One transaction. Another user's → not_found."""
    raise NotImplementedError("B3 step 2")


async def list_all(
    db: AsyncSession,
    user_id: int,
    *,
    since: date | None = None,
    until: date | None = None,
    status: TransactionStatus | None = None,
) -> Sequence[dm.TxView]:
    """Transactions by `occurred_at` (Bucharest days, both bounds inclusive), newest first."""
    raise NotImplementedError("B3 step 2")


async def list_effective(
    db: AsyncSession, user_id: int, since: date, until: date, category: Category | None = None
) -> Sequence[dm.TxView]:
    """Resolved transactions only (never unresolved / failed), Bucharest days inclusive, oldest
    first. What baselines, anomaly features and the forecast read (D26)."""
    raise NotImplementedError("B3 step 2")


async def save_evaluation(
    db: AsyncSession, user_id: int, tx_id: int, evaluation: Evaluation
) -> dm.TxView:
    """Store `context.evaluate_transaction`'s reading on the row (category, purpose, effective
    amount, scores, decision, explanation, matched ids, pot)."""
    raise NotImplementedError("B3 step 2")


async def annotate(
    db: AsyncSession,
    user_id: int,
    tx_id: int,
    *,
    purpose: Purpose,
    beneficiary: Beneficiary,
    effective_amount: Decimal,
    source: AnnotationSource,
    explanation: str | None = None,
    confidence: float | None = None,
) -> dm.TxView:
    """A new reading (answer, user edit, default). `effective_amount` outside [0, amount] →
    invalid_effective_amount (422). The ledger delta is the engine's job (on_annotation_changed)."""
    raise NotImplementedError("B3 step 2")


async def set_pot(db: AsyncSession, user_id: int, tx_id: int, pot_id: int | None) -> dm.TxView:
    """Link (or unlink) the pot that funds this transaction."""
    raise NotImplementedError("B3 step 2")


async def set_receivable(
    db: AsyncSession, user_id: int, tx_id: int, receivable_id: int | None
) -> dm.TxView:
    """Link (or unlink) the receivable created from this transaction."""
    raise NotImplementedError("B3 step 2")


async def mark_resolved(db: AsyncSession, user_id: int, tx_id: int) -> dm.TxView:
    """processing → resolved, `processed_at` = clock.now()."""
    raise NotImplementedError("B3 step 2")


async def mark_failed(db: AsyncSession, user_id: int, tx_id: int, error: str) -> dm.TxView:
    """→ failed with the error text (no more retries)."""
    raise NotImplementedError("B3 step 2")


async def bump_attempts(db: AsyncSession, user_id: int, tx_id: int, error: str) -> dm.TxView:
    """attempts += 1 and back to unresolved; on the 3rd attempt → failed (arch §11)."""
    raise NotImplementedError("B3 step 2")
