"""`load_user_context`: the complete, immutable view of one user (B4)."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain import models as dm
from app.domain.enums import AgentEventStatus, FactStatus
from app.domain.user_context import UserContext
from app.errors import DomainError
from app.services import (
    accounts,
    baselines,
    fixed_costs,
    forecasts,
    goals,
    income_sources,
    ledger,
    life_events,
    life_facts,
    life_profile,
    pattern_rules,
    plan_preferences,
    plans,
    pots,
    products,
    receivables,
    signatures,
    transactions,
    users,
)
from app.services._common import view
from app.services.agent_events import QUESTION_EVENT_TYPES
from app.services.transactions import day_start

RECENT_DAYS: Final = 14
"""Day-ledger rows loaded: the snapshot's RECENT SPENDING block (`snapshot.RECENT_DAYS`)."""
MAX_HISTORY: Final = 5
"""Slips and reflections loaded, the latest: what the snapshot prints (`snapshot.MAX_HISTORY`)."""


def _text(value: str | None, limit: int) -> str | None:
    """A free-text column as the domain's TextN: None when blank, cut to `limit` characters."""
    return value[:limit] if value is not None and value.strip() else None


async def _slips(db: AsyncSession, user_id: int, today: date) -> tuple[dm.Slip, ...]:
    """The latest `MAX_HISTORY` slips up to `today` with a reason (the domain needs one), oldest
    first."""
    rows = await db.scalars(
        select(m.Slip)
        .where(m.Slip.user_id == user_id, m.Slip.date <= today, m.Slip.reason.is_not(None))
        .order_by(m.Slip.date.desc(), m.Slip.id.desc())
        .limit(MAX_HISTORY)
    )
    slips = [
        dm.Slip(
            date=r.date,
            amount_over=r.amount_over,
            reason=reason,
            detail=_text(r.detail, 500),
            recurring=r.recurring,
        )
        for r in rows
        if (reason := _text(r.reason, 300)) is not None
    ]
    return tuple(reversed(slips))


async def _reflections(db: AsyncSession, user_id: int, today: date) -> tuple[dm.Reflection, ...]:
    """The latest `MAX_HISTORY` weekly reflections up to `today`, oldest first."""
    rows = await db.scalars(
        select(m.Reflection)
        .where(m.Reflection.user_id == user_id, m.Reflection.week_start <= today)
        .order_by(m.Reflection.week_start.desc(), m.Reflection.id.desc())
        .limit(MAX_HISTORY)
    )
    reflections = [
        dm.Reflection(
            week_start=r.week_start,
            motivation=r.motivation,
            answer=_text(r.answer, 500),
            reason=_text(r.reason, 300),
        )
        for r in rows
    ]
    return tuple(reversed(reflections))


async def load_user_context(
    db: AsyncSession, user_id: int, today: date, history_days: int = 180
) -> UserContext:
    """Everything about `user_id` on `today`: profile, account, goal + goal pot, income, fixed
    costs, planned events, active pots, open receivables, confirmed facts active on `today`,
    hypotheses, active signatures (of today's facts) and rules, plan preferences, baselines,
    resolved transactions of the last `history_days`, latest plan, latest + last weekly forecast,
    pending/asked events, how many questions were asked today, and the snapshot's extras: the
    last `RECENT_DAYS` ledger days, the latest `MAX_HISTORY` slips and reflections, the
    life-profile notes and the product catalogue."""
    profile = await users.get(db, user_id)
    try:
        account = await accounts.get(db, user_id)
    except DomainError:
        account = dm.Account(current_balance=Decimal("0"), savings_pot=Decimal("0"))  # fresh user
    all_facts = await life_facts.list_all(db, user_id)
    facts = tuple(f for f in all_facts if f.status == FactStatus.CONFIRMED and f.active_on(today))
    active_ids = {f.id for f in facts}
    events = await db.scalars(
        select(m.AgentEvent)
        .where(
            m.AgentEvent.user_id == user_id,
            m.AgentEvent.status.in_([AgentEventStatus.PENDING, AgentEventStatus.ASKED]),
        )
        .order_by(m.AgentEvent.created_at, m.AgentEvent.id)
    )
    asked_today = await db.scalar(
        select(func.count()).where(
            m.AgentEvent.user_id == user_id,
            m.AgentEvent.type.in_(QUESTION_EVENT_TYPES),
            m.AgentEvent.asked_at >= day_start(today),
            m.AgentEvent.asked_at < day_start(today + timedelta(days=1)),
        )
    )
    # The Q6 extras (HANDOFFS H-12) feed only the agent's snapshot; no engine core reads them.
    # `recent_questions` stays empty on purpose: the snapshot doesn't print it, and C7's weekly
    # cap and back-off (`app.context.questions`) read it, so loading it would change which
    # questions get asked; today the question budget is the daily cap (`questions_asked_today`).
    return UserContext(
        user_id=user_id,
        as_of=today,
        profile=profile,
        account=account,
        goal=await goals.get_active(db, user_id),
        goal_pot=await pots.goal_pot(db, user_id),
        income_sources=tuple(await income_sources.list_all(db, user_id)),
        fixed_costs=tuple(await fixed_costs.list_all(db, user_id)),
        life_events=tuple(await life_events.list_planned(db, user_id)),
        pots=tuple(await pots.list_active(db, user_id)),
        receivables=tuple(await receivables.list_open(db, user_id)),
        facts=facts,
        hypotheses=tuple(f for f in all_facts if f.status == FactStatus.HYPOTHESIS),
        signatures=tuple(
            s for s in await signatures.list_active(db, user_id) if s.fact_id in active_ids
        ),
        rules=tuple(await pattern_rules.list_active(db, user_id)),
        plan_preferences=await plan_preferences.get(db, user_id),
        baselines=await baselines.list_all(db, user_id),
        transactions=tuple(
            await transactions.list_effective(
                db, user_id, today - timedelta(days=history_days), today
            )
        ),
        plan=await plans.latest(db, user_id),
        forecast=await forecasts.latest(db, user_id),
        last_weekly_forecast=await forecasts.last_weekly_snapshot(db, user_id),
        agent_events=tuple(view(dm.AgentEventView, e) for e in events),
        questions_asked_today=asked_today or 0,
        recent_days=tuple(
            await ledger.between(db, user_id, today - timedelta(days=RECENT_DAYS - 1), today)
        ),
        slips=await _slips(db, user_id, today),
        reflections=await _reflections(db, user_id, today),
        life_notes=await life_profile.get(db, user_id),
        products=tuple(await products.list_all(db)),  # the mock catalogue (3 rows, not per user)
    )
