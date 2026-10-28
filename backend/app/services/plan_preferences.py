"""How the user shaped the budget (D19) (B3 step 1)."""

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm
from app.domain.enums import Category


async def get(db: AsyncSession, user_id: int) -> dm.PlanPreferences:
    """The preferences; the defaults when the user never shaped anything."""
    raise NotImplementedError("B3 step 1")


async def update(
    db: AsyncSession,
    user_id: int,
    *,
    weekday_weights: dict[str, float] | None = None,
    pinned_days: dict[date, Decimal | None] | None = None,
    category_caps: dict[Category, Decimal | None] | None = None,
    buffer_pct: Decimal | None = None,
) -> dm.PlanPreferences:
    """Merge into the stored preferences; a `None` value removes that pin / cap (shape_budget)."""
    raise NotImplementedError("B3 step 1")
