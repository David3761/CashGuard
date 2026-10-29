"""The day ledger: budget and spent per Bucharest day (B3 step 2)."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain import models as dm
from app.domain.enums import LedgerStatus
from app.services._common import view


async def _ensure(db: AsyncSession, user_id: int, day: date) -> None:
    await db.execute(
        insert(m.DayLedger)
        .values(user_id=user_id, date=day, budget=0, spent=0, status=LedgerStatus.OK)
        .on_conflict_do_nothing(index_elements=["user_id", "date"])
    )


async def _fresh(db: AsyncSession, user_id: int, day: date) -> m.DayLedger:
    row = await db.scalar(
        select(m.DayLedger)
        .where(m.DayLedger.user_id == user_id, m.DayLedger.date == day)
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise RuntimeError("day_ledger row missing right after its upsert")
    return row


async def get(db: AsyncSession, user_id: int, day: date) -> dm.LedgerDay | None:
    """That day's row, or None."""
    row = await db.get(m.DayLedger, (user_id, day))
    return view(dm.LedgerDay, row) if row is not None else None


async def get_or_create(db: AsyncSession, user_id: int, day: date) -> dm.LedgerDay:
    """That day's row, created (budget 0, spent 0, ok) when missing; safe when called twice."""
    await _ensure(db, user_id, day)
    return view(dm.LedgerDay, await _fresh(db, user_id, day))


async def update(
    db: AsyncSession,
    user_id: int,
    day: date,
    *,
    budget: Decimal | None = None,
    spent: Decimal | None = None,
    status: LedgerStatus | None = None,
) -> dm.LedgerDay:
    """Set the fields given (creates the row if needed)."""
    await _ensure(db, user_id, day)
    row = await _fresh(db, user_id, day)
    if budget is not None:
        row.budget = budget
    if spent is not None:
        row.spent = max(spent, Decimal("0"))
    if status is not None:
        row.status = status
    await db.flush()
    return view(dm.LedgerDay, row)


async def add_spent(db: AsyncSession, user_id: int, day: date, delta: Decimal) -> dm.LedgerDay:
    """spent += delta atomically (a re-annotation passes a negative delta); never below 0."""
    await db.execute(
        insert(m.DayLedger)
        .values(
            user_id=user_id,
            date=day,
            budget=0,
            spent=max(delta, Decimal("0")),
            status=LedgerStatus.OK,
        )
        .on_conflict_do_update(
            index_elements=["user_id", "date"],
            set_={"spent": func.greatest(m.DayLedger.spent + delta, 0)},
        )
    )
    return view(dm.LedgerDay, await _fresh(db, user_id, day))


async def between(
    db: AsyncSession, user_id: int, since: date, until: date
) -> Sequence[dm.LedgerDay]:
    """Rows between the two days (inclusive), oldest first."""
    rows = await db.scalars(
        select(m.DayLedger)
        .where(m.DayLedger.user_id == user_id, m.DayLedger.date.between(since, until))
        .order_by(m.DayLedger.date)
    )
    return [view(dm.LedgerDay, r) for r in rows]
