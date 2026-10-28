"""Chat messages (B3 step 3)."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm
from app.domain.enums import InputMode


async def save_user(
    db: AsyncSession, user_id: int, text: str, input_mode: InputMode
) -> dm.MessageView:
    """The user's message as received (POST /chat)."""
    raise NotImplementedError("B3 step 3")


async def save_assistant(
    db: AsyncSession,
    user_id: int,
    *,
    text: str,
    speak_text: str | None = None,
    quick_replies: Sequence[str] = (),
    action_cards: Sequence[dict[str, Any]] = (),
    ref_transaction_id: int | None = None,
    agent_event_id: int | None = None,
    speak: bool = False,
) -> dm.MessageView:
    """The agent's reply with everything the app needs (arch 9.3)."""
    raise NotImplementedError("B3 step 3")


async def list_all(
    db: AsyncSession, user_id: int, *, since: datetime | None = None, limit: int = 50
) -> Sequence[dm.MessageView]:
    """Messages created strictly after `since`, oldest first, at most `limit`."""
    raise NotImplementedError("B3 step 3")


async def recent(db: AsyncSession, user_id: int, limit: int = 20) -> Sequence[dm.MessageView]:
    """The last `limit` messages, oldest first (the agent's history, Q12)."""
    raise NotImplementedError("B3 step 3")
