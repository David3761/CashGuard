"""Planned life events: trips, gifts, concerts (B3 step 1)."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm
from app.domain.enums import LifeEventType


async def get(db: AsyncSession, user_id: int, event_id: int) -> dm.LifeEvent:
    """One event. Another user's → not_found."""
    raise NotImplementedError("B3 step 1")


async def list_planned(db: AsyncSession, user_id: int) -> Sequence[dm.LifeEvent]:
    """Planned events (not done, not cancelled), by date."""
    raise NotImplementedError("B3 step 1")


async def create(
    db: AsyncSession,
    user_id: int,
    *,
    name: str,
    date: date,
    est_cost: Decimal,
    type: LifeEventType,
    source: str | None = None,
) -> dm.LifeEvent:
    """A new planned event."""
    raise NotImplementedError("B3 step 1")


async def update(
    db: AsyncSession,
    user_id: int,
    event_id: int,
    *,
    name: str | None = None,
    date: date | None = None,
    est_cost: Decimal | None = None,
    type: LifeEventType | None = None,
) -> dm.LifeEvent:
    """Change only the fields given. Not planned → invalid_transition."""
    raise NotImplementedError("B3 step 1")


async def cancel(db: AsyncSession, user_id: int, event_id: int) -> dm.LifeEvent:
    """planned → cancelled (kept, not deleted). Otherwise → invalid_transition."""
    raise NotImplementedError("B3 step 1")


async def mark_done(db: AsyncSession, user_id: int, event_id: int) -> dm.LifeEvent:
    """planned → done. Otherwise → invalid_transition."""
    raise NotImplementedError("B3 step 1")
