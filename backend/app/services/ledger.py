"""The day ledger: budget and spent per Bucharest day (B3 step 2)."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm
from app.domain.enums import LedgerStatus


async def get(db: AsyncSession, user_id: int, day: date) -> dm.LedgerDay | None:
    """That day's row, or None."""
    raise NotImplementedError("B3 step 2")


async def get_or_create(db: AsyncSession, user_id: int, day: date) -> dm.LedgerDay:
    """That day's row, created (budget 0, spent 0, ok) when missing; safe when called twice."""
    raise NotImplementedError("B3 step 2")


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
    raise NotImplementedError("B3 step 2")


async def add_spent(db: AsyncSession, user_id: int, day: date, delta: Decimal) -> dm.LedgerDay:
    """spent += delta atomically (a re-annotation passes a negative delta); never below 0."""
    raise NotImplementedError("B3 step 2")


async def between(
    db: AsyncSession, user_id: int, since: date, until: date
) -> Sequence[dm.LedgerDay]:
    """Rows between the two days (inclusive), oldest first."""
    raise NotImplementedError("B3 step 2")
