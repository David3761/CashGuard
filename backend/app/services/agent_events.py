"""Agent events: what the agent should bring up (B3 step 3).

States: pending → asked → answered | handled | expired; pending → handled | expired.
"""

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db import models as m
from app.domain import models as dm
from app.domain.enums import AgentEventStatus, AgentEventType
from app.errors import DomainError
from app.services._common import as_enum, invalid, invalid_transition, owned, view
from app.services.transactions import day_start

S = AgentEventStatus

# The types that use the day's single question (D25). Informational events (goal completed,
# hypotheses, warnings, caps, reminders) don't. 🟡 C7 (David G.) owns the policy: confirm.
QUESTION_EVENT_TYPES = frozenset(
    {
        AgentEventType.TRANSACTION_QUESTION,
        AgentEventType.OVERSPEND,
        AgentEventType.UNDERSPEND_WEEK,
        AgentEventType.WEEKLY_REFLECTION,
        AgentEventType.PREEMPTIVE_CHECKIN,
    }
)


async def _existing(
    db: AsyncSession,
    user_id: int,
    type_: AgentEventType,
    event_date: date,
    ref_transaction_id: int | None,
) -> m.AgentEvent | None:
    stmt = select(m.AgentEvent).where(m.AgentEvent.user_id == user_id, m.AgentEvent.type == type_)
    if type_ in m.TRANSACTION_EVENT_TYPES:
        stmt = stmt.where(m.AgentEvent.ref_transaction_id == ref_transaction_id)
    else:
        stmt = stmt.where(m.AgentEvent.event_date == event_date)
    return await db.scalar(stmt)


async def _move(
    db: AsyncSession,
    user_id: int,
    event_id: int,
    allowed_from: set[AgentEventStatus],
    to: AgentEventStatus,
) -> dm.AgentEventView:
    row = await owned(db, m.AgentEvent, user_id, event_id, "Agent event")
    if row.status not in allowed_from:
        raise invalid_transition("The event", row.status, to)
    row.status = to
    now = clock.now()
    if to == S.ASKED:
        row.asked_at = now
    elif to == S.ANSWERED:
        row.answered_at = now
    else:
        row.handled_at = now
    await db.flush()
    return view(dm.AgentEventView, row)


async def get(db: AsyncSession, user_id: int, event_id: int) -> dm.AgentEventView:
    """One event. Another user's → not_found."""
    return view(dm.AgentEventView, await owned(db, m.AgentEvent, user_id, event_id, "Agent event"))


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
    type_ = as_enum(AgentEventType, type, "invalid_event_type")
    if type_ in m.TRANSACTION_EVENT_TYPES:
        if ref_transaction_id is None:
            raise invalid("missing_transaction", f"A {type_} needs its transaction.")
        await owned(db, m.Transaction, user_id, ref_transaction_id, "Transaction")
    existing = await _existing(db, user_id, type_, event_date, ref_transaction_id)
    if existing is not None:
        return view(dm.AgentEventView, existing)
    row = m.AgentEvent(
        user_id=user_id,
        type=type_,
        event_date=event_date,
        payload=payload or {},
        ref_transaction_id=ref_transaction_id,
    )
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError as exc:  # a concurrent insert won the race: return that one
        again = await _existing(db, user_id, type_, event_date, ref_transaction_id)
        if again is None:
            raise DomainError("conflict", "The event could not be created.", 409) from exc
        return view(dm.AgentEventView, again)
    return view(dm.AgentEventView, row)


async def mark_asked(db: AsyncSession, user_id: int, event_id: int) -> dm.AgentEventView:
    """pending → asked, `asked_at` = clock.now(). Otherwise → invalid_transition."""
    return await _move(db, user_id, event_id, {S.PENDING}, S.ASKED)


async def mark_answered(db: AsyncSession, user_id: int, event_id: int) -> dm.AgentEventView:
    """asked → answered, `answered_at` = clock.now(). Otherwise → invalid_transition."""
    return await _move(db, user_id, event_id, {S.ASKED}, S.ANSWERED)


async def mark_handled(db: AsyncSession, user_id: int, event_id: int) -> dm.AgentEventView:
    """pending | asked → handled. Otherwise → invalid_transition."""
    return await _move(db, user_id, event_id, {S.PENDING, S.ASKED}, S.HANDLED)


async def expire(db: AsyncSession, user_id: int, event_id: int) -> dm.AgentEventView:
    """pending | asked → expired. Otherwise → invalid_transition."""
    return await _move(db, user_id, event_id, {S.PENDING, S.ASKED}, S.EXPIRED)


async def pending_for(db: AsyncSession, user_id: int) -> Sequence[dm.AgentEventView]:
    """Pending events, oldest first (what a proactive run or the next chat should bring up)."""
    rows = await db.scalars(
        select(m.AgentEvent)
        .where(m.AgentEvent.user_id == user_id, m.AgentEvent.status == S.PENDING)
        .order_by(m.AgentEvent.created_at, m.AgentEvent.id)
    )
    return [view(dm.AgentEventView, r) for r in rows]


async def open_question(db: AsyncSession, user_id: int) -> dm.AgentEventView | None:
    """The asked-but-unanswered question, newest first, or None (the snapshot's open question)."""
    row = await db.scalar(
        select(m.AgentEvent)
        .where(
            m.AgentEvent.user_id == user_id,
            m.AgentEvent.status == S.ASKED,
            m.AgentEvent.type.in_(QUESTION_EVENT_TYPES),
        )
        .order_by(m.AgentEvent.asked_at.desc(), m.AgentEvent.id.desc())
        .limit(1)
    )
    return view(dm.AgentEventView, row) if row is not None else None


async def question_asked_today(db: AsyncSession, user_id: int, day: date) -> bool:
    """Was a question type asked on that Bucharest day (`asked_at`)? The D25 budget."""
    asked = select(m.AgentEvent.id).where(
        m.AgentEvent.user_id == user_id,
        m.AgentEvent.type.in_(QUESTION_EVENT_TYPES),
        m.AgentEvent.asked_at >= day_start(day),
        m.AgentEvent.asked_at < day_start(day + timedelta(days=1)),
    )
    return bool(await db.scalar(select(exists(asked))))
