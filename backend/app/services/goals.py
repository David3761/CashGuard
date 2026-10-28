"""Goals: one active goal per user (D17) (B3 step 1)."""

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm


async def get(db: AsyncSession, user_id: int, goal_id: int) -> dm.Goal:
    """One goal. Another user's → not_found."""
    raise NotImplementedError("B3 step 1")


async def get_active(db: AsyncSession, user_id: int) -> dm.Goal | None:
    """The active goal, or None (onboarding, after goal_completed)."""
    raise NotImplementedError("B3 step 1")


async def create(
    db: AsyncSession,
    user_id: int,
    *,
    amount: Decimal,
    deadline: date,
    motivation: str | None = None,
    soft: bool = True,
) -> dm.Goal:
    """A new active goal + its goal pot. Already one active → goal_already_active (409)."""
    raise NotImplementedError("B3 step 1")


async def update(
    db: AsyncSession,
    user_id: int,
    goal_id: int,
    *,
    amount: Decimal | None = None,
    deadline: date | None = None,
    motivation: str | None = None,
    soft: bool | None = None,
) -> dm.Goal:
    """Change only the fields given. A completed goal → invalid_transition."""
    raise NotImplementedError("B3 step 1")


async def complete(db: AsyncSession, user_id: int, goal_id: int) -> dm.Goal:
    """active → completed. Already completed → invalid_transition."""
    raise NotImplementedError("B3 step 1")
