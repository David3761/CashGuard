"""`load_user_context`: the complete, immutable view of one user (B4)."""

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain import models as dm
from app.domain.enums import AgentEventStatus, FactStatus
from app.errors import DomainError
from app.services import (
    accounts,
    baselines,
    fixed_costs,
    forecasts,
    goals,
    income_sources,
    life_events,
    life_facts,
    pattern_rules,
    plan_preferences,
    plans,
    pots,
    receivables,
    signatures,
    transactions,
    users,
)
from app.services._common import view
from app.services.agent_events import QUESTION_EVENT_TYPES
from app.services.transactions import day_start


async def load_user_context(
    db: AsyncSession, user_id: int, today: date, history_days: int = 180
) -> dm.UserContext:
    """Everything about `user_id` on `today`: profile, account, goal + goal pot, income, fixed
    costs, planned events, active pots, open receivables, confirmed facts active on `today`,
    hypotheses, active signatures (of today's facts) and rules, plan preferences, baselines,
    resolved transactions of the last `history_days`, latest plan, latest + last weekly forecast,
    pending/asked events, and how many questions were asked today."""
    profile = await users.get(db, user_id)
    try:
        account = await accounts.get(db, user_id)
    except DomainError:
        account = dm.Account()  # not created yet (fresh user)
    all_facts = await life_facts.list_all(db, user_id)
    facts = tuple(f for f in all_facts if f.active_on(today))
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
    return dm.UserContext(
        today=today,
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
        events=tuple(view(dm.AgentEventView, e) for e in events),
        questions_asked_today=asked_today or 0,
    )
