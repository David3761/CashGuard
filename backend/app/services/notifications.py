"""Notifications (rows only; B13 adds the RO/EN texts and the push) (B3 step 3)."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain import models as dm
from app.services._common import owned, view


async def create(
    db: AsyncSession,
    user_id: int,
    *,
    type: str,
    title: str,
    body: str,
    opens_chat: bool = False,
    agent_event_id: int | None = None,
    message_id: int | None = None,
) -> dm.NotificationView:
    """A new unread notification."""
    row = m.Notification(
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        opens_chat=opens_chat,
        agent_event_id=agent_event_id,
        message_id=message_id,
    )
    db.add(row)
    await db.flush()
    return view(dm.NotificationView, row)


async def list_all(
    db: AsyncSession, user_id: int, *, since: datetime | None = None, unread_only: bool = False
) -> Sequence[dm.NotificationView]:
    """Notifications created strictly after `since`, oldest first."""
    stmt = select(m.Notification).where(m.Notification.user_id == user_id)
    if since is not None:
        stmt = stmt.where(m.Notification.created_at > since)
    if unread_only:
        stmt = stmt.where(m.Notification.read.is_(False))
    rows = await db.scalars(stmt.order_by(m.Notification.created_at, m.Notification.id))
    return [view(dm.NotificationView, r) for r in rows]


async def mark_read(db: AsyncSession, user_id: int, notification_id: int) -> dm.NotificationView:
    """Mark it read (idempotent). Another user's → not_found."""
    row = await owned(db, m.Notification, user_id, notification_id, "Notification")
    row.read = True
    await db.flush()
    return view(dm.NotificationView, row)


async def unread_count(db: AsyncSession, user_id: int) -> int:
    """How many are unread (`/state.unread_notifications`)."""
    n = await db.scalar(
        select(func.count()).where(
            m.Notification.user_id == user_id, m.Notification.read.is_(False)
        )
    )
    return n or 0
