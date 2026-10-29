"""Planned life events: trips, gifts, concerts (B3 step 1)."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain import models as dm
from app.domain.enums import LifeEventStatus, LifeEventType
from app.services._common import as_enum, invalid, invalid_transition, owned, view


def _check_cost(est_cost: Decimal | None) -> None:
    if est_cost is not None and est_cost < 0:
        raise invalid("invalid_amount", "The estimated cost can't be negative.")


async def _planned(db: AsyncSession, user_id: int, event_id: int, wanted: str) -> m.LifeEvent:
    row = await owned(db, m.LifeEvent, user_id, event_id, "Life event")
    if row.status != LifeEventStatus.PLANNED:
        raise invalid_transition("The event", row.status, wanted)
    return row


async def get(db: AsyncSession, user_id: int, event_id: int) -> dm.LifeEvent:
    """One event. Another user's → not_found."""
    return view(dm.LifeEvent, await owned(db, m.LifeEvent, user_id, event_id, "Life event"))


async def list_planned(db: AsyncSession, user_id: int) -> Sequence[dm.LifeEvent]:
    """Planned events (not done, not cancelled), by date."""
    rows = await db.scalars(
        select(m.LifeEvent)
        .where(m.LifeEvent.user_id == user_id, m.LifeEvent.status == LifeEventStatus.PLANNED)
        .order_by(m.LifeEvent.date, m.LifeEvent.id)
    )
    return [view(dm.LifeEvent, r) for r in rows]


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
    _check_cost(est_cost)
    row = m.LifeEvent(
        user_id=user_id,
        name=name,
        date=date,
        est_cost=est_cost,
        type=as_enum(LifeEventType, type, "invalid_event_type"),
        source=source,
    )
    db.add(row)
    await db.flush()
    return view(dm.LifeEvent, row)


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
    _check_cost(est_cost)
    row = await _planned(db, user_id, event_id, "changed")
    if name is not None:
        row.name = name
    if date is not None:
        row.date = date
    if est_cost is not None:
        row.est_cost = est_cost
    if type is not None:
        row.type = as_enum(LifeEventType, type, "invalid_event_type")
    await db.flush()
    return view(dm.LifeEvent, row)


async def cancel(db: AsyncSession, user_id: int, event_id: int) -> dm.LifeEvent:
    """planned → cancelled (kept, not deleted). Otherwise → invalid_transition."""
    row = await _planned(db, user_id, event_id, LifeEventStatus.CANCELLED)
    row.status = LifeEventStatus.CANCELLED
    await db.flush()
    return view(dm.LifeEvent, row)


async def mark_done(db: AsyncSession, user_id: int, event_id: int) -> dm.LifeEvent:
    """planned → done. Otherwise → invalid_transition."""
    row = await _planned(db, user_id, event_id, LifeEventStatus.DONE)
    row.status = LifeEventStatus.DONE
    await db.flush()
    return view(dm.LifeEvent, row)
