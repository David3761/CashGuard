"""Income sources (B3 step 1)."""

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain import models as dm
from app.services._common import invalid, owned, view


def _check(amount: Decimal | None, day_of_month: int | None) -> None:
    if amount is not None and amount <= 0:
        raise invalid("invalid_amount", "The amount must be positive.")
    if day_of_month is not None and not 1 <= day_of_month <= 31:
        raise invalid("invalid_day_of_month", "day_of_month is between 1 and 31.")


async def list_all(db: AsyncSession, user_id: int) -> Sequence[dm.IncomeSource]:
    """Every income source, by day of month."""
    rows = await db.scalars(
        select(m.IncomeSource)
        .where(m.IncomeSource.user_id == user_id)
        .order_by(m.IncomeSource.day_of_month, m.IncomeSource.id)
    )
    return [view(dm.IncomeSource, r) for r in rows]


async def create(
    db: AsyncSession, user_id: int, *, source: str, amount: Decimal, day_of_month: int
) -> dm.IncomeSource:
    """A new income source."""
    _check(amount, day_of_month)
    row = m.IncomeSource(user_id=user_id, source=source, amount=amount, day_of_month=day_of_month)
    db.add(row)
    await db.flush()
    return view(dm.IncomeSource, row)


async def update(
    db: AsyncSession,
    user_id: int,
    income_id: int,
    *,
    source: str | None = None,
    amount: Decimal | None = None,
    day_of_month: int | None = None,
) -> dm.IncomeSource:
    """Change only the fields given. Another user's → not_found."""
    _check(amount, day_of_month)
    row = await owned(db, m.IncomeSource, user_id, income_id, "Income source")
    if source is not None:
        row.source = source
    if amount is not None:
        row.amount = amount
    if day_of_month is not None:
        row.day_of_month = day_of_month
    await db.flush()
    return view(dm.IncomeSource, row)


async def delete(db: AsyncSession, user_id: int, income_id: int) -> None:
    """Remove it. Another user's → not_found."""
    await db.delete(await owned(db, m.IncomeSource, user_id, income_id, "Income source"))
    await db.flush()
