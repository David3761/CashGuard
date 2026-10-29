"""Transactions: the queue and the annotation (B3 step 2)."""

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.clock import BUCHAREST
from app.db import models as m
from app.domain import models as dm
from app.domain.enums import AnnotationSource, Beneficiary, Category, Purpose, TransactionStatus
from app.domain.results import Evaluation
from app.services._common import invalid, owned, view

MAX_ATTEMPTS = 3  # arch §11: failed after 3


def day_start(day: date) -> datetime:
    """Bucharest midnight at the start of `day`."""
    return datetime.combine(day, time(0), tzinfo=BUCHAREST)


def _within(stmt: Select[Any], since: date | None, until: date | None) -> Select[Any]:
    if since is not None:
        stmt = stmt.where(m.Transaction.occurred_at >= day_start(since))
    if until is not None:
        stmt = stmt.where(m.Transaction.occurred_at < day_start(until + timedelta(days=1)))
    return stmt


def _check_effective(row: m.Transaction, effective_amount: Decimal) -> None:
    if not Decimal("0") <= effective_amount <= row.amount:
        raise invalid(
            "invalid_effective_amount", f"The own share must be between 0 and {row.amount}."
        )


async def _row(db: AsyncSession, user_id: int, tx_id: int) -> m.Transaction:
    return await owned(db, m.Transaction, user_id, tx_id, "Transaction")


async def get(db: AsyncSession, user_id: int, tx_id: int) -> dm.TxView:
    """One transaction. Another user's → not_found."""
    return view(dm.TxView, await _row(db, user_id, tx_id))


async def list_all(
    db: AsyncSession,
    user_id: int,
    *,
    since: date | None = None,
    until: date | None = None,
    status: TransactionStatus | None = None,
) -> Sequence[dm.TxView]:
    """Transactions by `occurred_at` (Bucharest days, both bounds inclusive), newest first."""
    stmt = _within(select(m.Transaction).where(m.Transaction.user_id == user_id), since, until)
    if status is not None:
        stmt = stmt.where(m.Transaction.status == status)
    rows = await db.scalars(
        stmt.order_by(m.Transaction.occurred_at.desc(), m.Transaction.id.desc())
    )
    return [view(dm.TxView, r) for r in rows]


async def list_effective(
    db: AsyncSession, user_id: int, since: date, until: date, category: Category | None = None
) -> Sequence[dm.TxView]:
    """Resolved transactions only (never unresolved / failed), Bucharest days inclusive, oldest
    first. What baselines, anomaly features and the forecast read (D26)."""
    stmt = _within(
        select(m.Transaction).where(
            m.Transaction.user_id == user_id,
            m.Transaction.status == TransactionStatus.RESOLVED,
        ),
        since,
        until,
    )
    if category is not None:
        stmt = stmt.where(m.Transaction.category == category)
    rows = await db.scalars(stmt.order_by(m.Transaction.occurred_at, m.Transaction.id))
    return [view(dm.TxView, r) for r in rows]


async def save_evaluation(
    db: AsyncSession, user_id: int, tx_id: int, evaluation: Evaluation
) -> dm.TxView:
    """Store `context.evaluate_transaction`'s reading on the row (category, purpose, effective
    amount, scores, decision, explanation, matched ids, pot)."""
    row = await _row(db, user_id, tx_id)
    _check_effective(row, evaluation.effective_amount)
    fields = evaluation.model_dump(
        exclude={"goal_impact", "question_hint", "confidence"}, exclude_none=False
    )
    fields["annotation_confidence"] = evaluation.confidence  # our F2 name → the column
    if (
        fields["merchant_id"] is not None
        and await db.get(m.Merchant, fields["merchant_id"]) is None
    ):
        # C2 normalises against data/merchants.json; a slug the DB catalogue doesn't have yet
        # (catalogue not seeded) must not break processing on the FK.
        fields["merchant_id"] = None
    for name, value in fields.items():
        setattr(row, name, value)
    await db.flush()
    return view(dm.TxView, row)


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
    row = await _row(db, user_id, tx_id)
    _check_effective(row, effective_amount)
    row.purpose = purpose
    row.beneficiary = beneficiary
    row.effective_amount = effective_amount
    row.annotation_source = source
    row.annotation_confidence = Decimal(str(confidence)) if confidence is not None else None
    if explanation is not None:
        row.explanation = explanation
    await db.flush()
    return view(dm.TxView, row)


async def set_pot(db: AsyncSession, user_id: int, tx_id: int, pot_id: int | None) -> dm.TxView:
    """Link (or unlink) the pot that funds this transaction."""
    row = await _row(db, user_id, tx_id)
    row.pot_id = pot_id
    await db.flush()
    return view(dm.TxView, row)


async def set_receivable(
    db: AsyncSession, user_id: int, tx_id: int, receivable_id: int | None
) -> dm.TxView:
    """Link (or unlink) the receivable created from this transaction."""
    row = await _row(db, user_id, tx_id)
    row.receivable_id = receivable_id
    await db.flush()
    return view(dm.TxView, row)


async def mark_resolved(db: AsyncSession, user_id: int, tx_id: int) -> dm.TxView:
    """processing → resolved, `processed_at` = clock.now()."""
    row = await _row(db, user_id, tx_id)
    row.status = TransactionStatus.RESOLVED
    row.processed_at = clock.now()
    row.locked_at = None
    row.error = None
    await db.flush()
    return view(dm.TxView, row)


async def mark_failed(db: AsyncSession, user_id: int, tx_id: int, error: str) -> dm.TxView:
    """→ failed with the error text (no more retries)."""
    row = await _row(db, user_id, tx_id)
    row.status = TransactionStatus.FAILED
    row.error = error
    row.locked_at = None
    await db.flush()
    return view(dm.TxView, row)


async def bump_attempts(db: AsyncSession, user_id: int, tx_id: int, error: str) -> dm.TxView:
    """attempts += 1 and back to unresolved; on the 3rd attempt → failed (arch §11)."""
    row = await _row(db, user_id, tx_id)
    row.attempts += 1
    row.error = error
    row.locked_at = None
    row.status = (
        TransactionStatus.FAILED if row.attempts >= MAX_ATTEMPTS else TransactionStatus.UNRESOLVED
    )
    await db.flush()
    return view(dm.TxView, row)
