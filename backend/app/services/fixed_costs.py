"""Fixed costs: rent, utilities, subscriptions (B3 step 1)."""

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


async def list_all(db: AsyncSession, user_id: int) -> Sequence[dm.FixedCost]:
    """Every fixed cost, by day of month."""
    rows = await db.scalars(
        select(m.FixedCost)
        .where(m.FixedCost.user_id == user_id)
        .order_by(m.FixedCost.day_of_month, m.FixedCost.id)
    )
    return [view(dm.FixedCost, r) for r in rows]


async def create(
    db: AsyncSession, user_id: int, *, name: str, amount: Decimal, day_of_month: int
) -> dm.FixedCost:
    """A new fixed cost."""
    _check(amount, day_of_month)
    row = m.FixedCost(user_id=user_id, name=name, amount=amount, day_of_month=day_of_month)
    db.add(row)
    await db.flush()
    return view(dm.FixedCost, row)


async def update(
    db: AsyncSession,
    user_id: int,
    cost_id: int,
    *,
    name: str | None = None,
    amount: Decimal | None = None,
    day_of_month: int | None = None,
) -> dm.FixedCost:
    """Change only the fields given ("m-am mutat, chiria e 2.400"). Another user's → not_found."""
    _check(amount, day_of_month)
    row = await owned(db, m.FixedCost, user_id, cost_id, "Fixed cost")
    if name is not None:
        row.name = name
    if amount is not None:
        row.amount = amount
    if day_of_month is not None:
        row.day_of_month = day_of_month
    await db.flush()
    return view(dm.FixedCost, row)


async def delete(db: AsyncSession, user_id: int, cost_id: int) -> None:
    """Remove it. Another user's → not_found."""
    await db.delete(await owned(db, m.FixedCost, user_id, cost_id, "Fixed cost"))
    await db.flush()
