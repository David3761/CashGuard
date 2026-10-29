"""Money other people owe the user (arch 4.4) (B3 step 4).

States: open → requested → paid; open → paid (paid back without a request);
open | requested → cancelled.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db import models as m
from app.domain import models as dm
from app.domain.enums import ReceivableStatus
from app.services._common import as_enum, invalid, invalid_transition, owned, view

R = ReceivableStatus
ALLOWED = {
    R.OPEN: {R.REQUESTED, R.PAID, R.CANCELLED},
    R.REQUESTED: {R.PAID, R.CANCELLED},
    R.PAID: set(),
    R.CANCELLED: set(),
}


async def get(db: AsyncSession, user_id: int, receivable_id: int) -> dm.Receivable:
    """One receivable. Another user's → not_found."""
    return view(dm.Receivable, await owned(db, m.Receivable, user_id, receivable_id, "Receivable"))


async def create(
    db: AsyncSession,
    user_id: int,
    *,
    amount: Decimal,
    debtor_label: str,
    expected_by: date,
    transaction_id: int | None = None,
    people_count: int | None = None,
    amount_each: Decimal | None = None,
) -> dm.Receivable:
    """An open receivable."""
    if amount <= 0 or (amount_each is not None and amount_each < 0):
        raise invalid("invalid_amount", "A receivable needs a positive amount.")
    if people_count is not None and people_count < 1:
        raise invalid("invalid_amount", "people_count is at least 1.")
    if transaction_id is not None:
        await owned(db, m.Transaction, user_id, transaction_id, "Transaction")
    row = m.Receivable(
        user_id=user_id,
        amount=amount,
        debtor_label=debtor_label,
        expected_by=expected_by,
        transaction_id=transaction_id,
        people_count=people_count,
        amount_each=amount_each,
    )
    db.add(row)
    await db.flush()
    return view(dm.Receivable, row)


async def list_all(
    db: AsyncSession, user_id: int, status: ReceivableStatus | None = None
) -> Sequence[dm.Receivable]:
    """Every receivable, or only one status (GET /receivables?status=), newest first."""
    stmt = select(m.Receivable).where(m.Receivable.user_id == user_id)
    if status is not None:
        stmt = stmt.where(m.Receivable.status == status)
    rows = await db.scalars(stmt.order_by(m.Receivable.created_at.desc(), m.Receivable.id.desc()))
    return [view(dm.Receivable, r) for r in rows]


async def list_open(db: AsyncSession, user_id: int) -> Sequence[dm.Receivable]:
    """Open and requested (still expected), by `expected_by`."""
    rows = await db.scalars(
        select(m.Receivable)
        .where(m.Receivable.user_id == user_id, m.Receivable.status.in_([R.OPEN, R.REQUESTED]))
        .order_by(m.Receivable.expected_by, m.Receivable.id)
    )
    return [view(dm.Receivable, r) for r in rows]


async def update_status(
    db: AsyncSession, user_id: int, receivable_id: int, status: ReceivableStatus
) -> dm.Receivable:
    """Follow the state machine (sets `requested_at` / `paid_at`); anything else →
    invalid_transition (409)."""
    row = await owned(db, m.Receivable, user_id, receivable_id, "Receivable")
    to = as_enum(ReceivableStatus, status, "invalid_status")
    if to not in ALLOWED[ReceivableStatus(row.status)]:
        raise invalid_transition("The receivable", row.status, to)
    row.status = to
    if to == R.REQUESTED:
        row.requested_at = clock.now()
    elif to == R.PAID:
        row.paid_at = clock.now()
    await db.flush()
    return view(dm.Receivable, row)


async def cancel(db: AsyncSession, user_id: int, receivable_id: int) -> dm.Receivable:
    """open | requested → cancelled ("nu, a fost doar pentru mine")."""
    return await update_status(db, user_id, receivable_id, R.CANCELLED)
