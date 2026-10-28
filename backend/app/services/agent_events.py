"""Agent events: what the agent should bring up (B3 step 3).

States: pending → asked → answered | handled | expired; pending → handled | expired.
"""

from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm
from app.domain.enums import AgentEventType


async def get(db: AsyncSession, user_id: int, event_id: int) -> dm.AgentEventView:
    """One event. Another user's → not_found."""
    raise NotImplementedError("B3 step 3")


async def create(
    db: AsyncSession,
    user_id: int,
    *,
    type: AgentEventType,
    event_date: date,
    payload: dict[str, Any] | None = None,
    ref_transaction_id: int | None = None,
) -> dm.AgentEventView:
    """A pending event. Deduplicated: the same day-level type on the same date, or the same
    transaction question twice, returns the existing event instead of failing."""
    raise NotImplementedError("B3 step 3")


async def mark_asked(db: AsyncSession, user_id: int, event_id: int) -> dm.AgentEventView:
    """pending → asked, `asked_at` = clock.now(). Otherwise → invalid_transition."""
    raise NotImplementedError("B3 step 3")


async def mark_answered(db: AsyncSession, user_id: int, event_id: int) -> dm.AgentEventView:
    """asked → answered, `answered_at` = clock.now(). Otherwise → invalid_transition."""
    raise NotImplementedError("B3 step 3")


async def mark_handled(db: AsyncSession, user_id: int, event_id: int) -> dm.AgentEventView:
    """pending | asked → handled. Otherwise → invalid_transition."""
    raise NotImplementedError("B3 step 3")


async def expire(db: AsyncSession, user_id: int, event_id: int) -> dm.AgentEventView:
    """pending | asked → expired. Otherwise → invalid_transition."""
    raise NotImplementedError("B3 step 3")


async def pending_for(db: AsyncSession, user_id: int) -> Sequence[dm.AgentEventView]:
    """Pending events, oldest first (what a proactive run or the next chat should bring up)."""
    raise NotImplementedError("B3 step 3")


async def open_question(db: AsyncSession, user_id: int) -> dm.AgentEventView | None:
    """The asked-but-unanswered question, newest first, or None (the snapshot's open question)."""
    raise NotImplementedError("B3 step 3")


async def question_asked_today(db: AsyncSession, user_id: int, day: date) -> bool:
    """Was a question type asked on that Bucharest day (`asked_at`)? The D25 budget."""
    raise NotImplementedError("B3 step 3")
