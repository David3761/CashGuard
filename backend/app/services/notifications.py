"""Notifications (rows only; B13 adds the RO/EN texts and the push) (B3 step 3)."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm


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
    raise NotImplementedError("B3 step 3")


async def list_all(
    db: AsyncSession, user_id: int, *, since: datetime | None = None, unread_only: bool = False
) -> Sequence[dm.NotificationView]:
    """Notifications created strictly after `since`, oldest first."""
    raise NotImplementedError("B3 step 3")


async def mark_read(db: AsyncSession, user_id: int, notification_id: int) -> dm.NotificationView:
    """Mark it read (idempotent). Another user's → not_found."""
    raise NotImplementedError("B3 step 3")


async def unread_count(db: AsyncSession, user_id: int) -> int:
    """How many are unread (`/state.unread_notifications`)."""
    raise NotImplementedError("B3 step 3")
