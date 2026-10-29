"""Chat messages (B3 step 3)."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain import models as dm
from app.domain.enums import InputMode, MessageRole
from app.services._common import as_enum, view


async def _add(db: AsyncSession, row: m.Message) -> dm.MessageView:
    db.add(row)
    await db.flush()
    return view(dm.MessageView, row)


async def save_user(
    db: AsyncSession, user_id: int, text: str, input_mode: InputMode
) -> dm.MessageView:
    """The user's message as received (POST /chat)."""
    mode = as_enum(InputMode, input_mode, "invalid_input_mode")
    return await _add(
        db, m.Message(user_id=user_id, role=MessageRole.USER, content=text, input_mode=mode)
    )


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
    return await _add(
        db,
        m.Message(
            user_id=user_id,
            role=MessageRole.ASSISTANT,
            content=text,
            speak=speak,
            speak_text=speak_text,
            quick_replies=list(quick_replies),
            action_cards=[dict(card) for card in action_cards],
            ref_transaction_id=ref_transaction_id,
            agent_event_id=agent_event_id,
        ),
    )


async def list_all(
    db: AsyncSession, user_id: int, *, since: datetime | None = None, limit: int = 50
) -> Sequence[dm.MessageView]:
    """Messages created strictly after `since`, oldest first, at most `limit`."""
    stmt = select(m.Message).where(m.Message.user_id == user_id)
    if since is not None:
        stmt = stmt.where(m.Message.created_at > since)
    rows = await db.scalars(stmt.order_by(m.Message.created_at, m.Message.id).limit(limit))
    return [view(dm.MessageView, r) for r in rows]


async def recent(db: AsyncSession, user_id: int, limit: int = 20) -> Sequence[dm.MessageView]:
    """The last `limit` messages, oldest first (the agent's history, Q12)."""
    rows = await db.scalars(
        select(m.Message)
        .where(m.Message.user_id == user_id)
        .order_by(m.Message.created_at.desc(), m.Message.id.desc())
        .limit(limit)
    )
    return [view(dm.MessageView, r) for r in reversed(list(rows))]
