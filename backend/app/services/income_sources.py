"""Income sources (B3 step 1)."""

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm


async def list_all(db: AsyncSession, user_id: int) -> Sequence[dm.IncomeSource]:
    """Every income source, by day of month."""
    raise NotImplementedError("B3 step 1")


async def create(
    db: AsyncSession, user_id: int, *, source: str, amount: Decimal, day_of_month: int
) -> dm.IncomeSource:
    """A new income source."""
    raise NotImplementedError("B3 step 1")


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
    raise NotImplementedError("B3 step 1")


async def delete(db: AsyncSession, user_id: int, income_id: int) -> None:
    """Remove it. Another user's → not_found."""
    raise NotImplementedError("B3 step 1")
