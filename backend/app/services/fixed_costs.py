"""Fixed costs: rent, utilities, subscriptions (B3 step 1)."""

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm


async def list_all(db: AsyncSession, user_id: int) -> Sequence[dm.FixedCost]:
    """Every fixed cost, by day of month."""
    raise NotImplementedError("B3 step 1")


async def create(
    db: AsyncSession, user_id: int, *, name: str, amount: Decimal, day_of_month: int
) -> dm.FixedCost:
    """A new fixed cost."""
    raise NotImplementedError("B3 step 1")


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
    raise NotImplementedError("B3 step 1")


async def delete(db: AsyncSession, user_id: int, cost_id: int) -> None:
    """Remove it. Another user's → not_found."""
    raise NotImplementedError("B3 step 1")
