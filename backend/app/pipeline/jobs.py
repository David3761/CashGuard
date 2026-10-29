"""Time-based jobs (arch F5, F6, §10; B11). Each takes `db`, `user_id` and the (sim) date or
time; the internal endpoints and `/sim/next-day` run them for every user.

Stand-in thresholds until danutu's E11 signals land: overspent if spent > budget; under if
spent < 0.5 × budget at close; otherwise ok.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import events
from app.db import models as m
from app.domain import models as dm
from app.domain.enums import (
    AgentEventStatus,
    AgentEventType,
    AnnotationSource,
    Beneficiary,
    FactSource,
    FactStatus,
    LedgerStatus,
    ReceivableStatus,
)
from app.pipeline import ports
from app.services import agent_events, forecasts, ledger, life_events, life_facts, plans
from app.services import transactions as txs
from app.services.notify import notify
from app.services.transactions import day_start
from app.ws import push_after_commit

STREAK_MILESTONES = (3, 7, 14)
UNDER_RATIO = Decimal("0.5")
EVENT_TTL = timedelta(hours=48)
QUESTION_TTL = timedelta(hours=24)
RECEIVABLE_REMINDER_AFTER = timedelta(days=14)


def ledger_status(spent: Decimal, budget: Decimal) -> LedgerStatus:
    if spent > budget:
        return LedgerStatus.OVERSPENT
    if spent < budget * UNDER_RATIO:
        return LedgerStatus.UNDER
    return LedgerStatus.OK


async def _streak(db: AsyncSession, user_id: int, day: date) -> int:
    rows = {d.date: d for d in await ledger.between(db, user_id, day - timedelta(days=30), day)}
    streak = 0
    while day in rows and rows[day].status in (LedgerStatus.OK, LedgerStatus.UNDER):
        streak += 1
        day -= timedelta(days=1)
    return streak


async def _notified(db: AsyncSession, user_id: int, type_: str, day: date) -> bool:
    found = await db.scalar(
        select(m.Notification.id)
        .where(
            m.Notification.user_id == user_id,
            m.Notification.type == type_,
            m.Notification.created_at >= day_start(day),
            m.Notification.created_at < day_start(day + timedelta(days=1)),
        )
        .limit(1)
    )
    return found is not None


async def close_day(db: AsyncSession, user_id: int, day: date) -> LedgerStatus:
    """Finalise the day's ledger; overspend → the day's question if free, else a quiet
    notification; streak milestones; re-plan. Idempotent per (user, day)."""
    plan = await plans.latest(db, user_id)
    row = await ledger.get_or_create(db, user_id, day)
    budget = row.budget if row.budget > 0 or plan is None else plan.today_budget
    status = ledger_status(row.spent, budget)
    await ledger.update(db, user_id, day, budget=budget, status=status)
    push_after_commit(
        db,
        user_id,
        events.ledger_updated(
            dm.LedgerDay(date=day, budget=budget, spent=row.spent, status=status)
        ),
    )
    if status == LedgerStatus.OVERSPENT:
        over = row.spent - budget
        if not await agent_events.question_asked_today(db, user_id, day):
            await agent_events.create(
                db,
                user_id,
                type=AgentEventType.OVERSPEND,
                event_date=day,
                payload={"over": float(over), "budget": float(budget)},
            )
        elif not await _notified(db, user_id, "overspend", day):
            await notify(db, user_id, "overspend", {"over": over, "budget": budget})
    streak = await _streak(db, user_id, day)
    if streak in STREAK_MILESTONES and not await _notified(db, user_id, "streak", day):
        await notify(db, user_id, "streak", {"days": streak})
    if plan is not None:
        new = await ports.recompute_plan(db, user_id, reason="day closed")
        if new is not None:
            push_after_commit(db, user_id, events.plan_updated(new))
    return status


async def expire_events(db: AsyncSession, user_id: int, now: datetime) -> int:
    """Pending events older than 48 h → expired."""
    rows = await db.scalars(
        select(m.AgentEvent.id).where(
            m.AgentEvent.user_id == user_id,
            m.AgentEvent.status == AgentEventStatus.PENDING,
            m.AgentEvent.created_at < now - EVENT_TTL,
        )
    )
    ids = list(rows)
    for event_id in ids:
        await agent_events.expire(db, user_id, event_id)
    return len(ids)


async def expire_questions(db: AsyncSession, user_id: int, now: datetime) -> int:
    """Asked > 24 h without an answer → the default reading (confidence 0.3) → expired."""
    rows = list(
        await db.scalars(
            select(m.AgentEvent).where(
                m.AgentEvent.user_id == user_id,
                m.AgentEvent.status == AgentEventStatus.ASKED,
                m.AgentEvent.asked_at < now - QUESTION_TTL,
            )
        )
    )
    for ev in rows:
        if ev.type == AgentEventType.TRANSACTION_QUESTION and ev.ref_transaction_id:
            tx = await txs.get(db, user_id, ev.ref_transaction_id)
            purpose, confidence = ports.default_reading(tx)
            await txs.annotate(
                db,
                user_id,
                tx.id,
                purpose=purpose,
                beneficiary=Beneficiary.SELF,
                effective_amount=tx.effective_amount,
                source=AnnotationSource.DEFAULT,
                confidence=confidence,
            )
        await agent_events.expire(db, user_id, ev.id)
    return len(rows)


async def receivable_reminders(db: AsyncSession, user_id: int, today: date) -> int:
    """Open for 14 days or more → one `receivable_reminder` event a day."""
    due = list(
        await db.scalars(
            select(m.Receivable.id).where(
                m.Receivable.user_id == user_id,
                m.Receivable.status == ReceivableStatus.OPEN,
                m.Receivable.created_at
                <= day_start(today) - RECEIVABLE_REMINDER_AFTER + timedelta(days=1),
            )
        )
    )
    if due:
        await agent_events.create(
            db,
            user_id,
            type=AgentEventType.RECEIVABLE_REMINDER,
            event_date=today,
            payload={"receivable_ids": due},
        )
    return len(due)


async def forecast_snapshot(db: AsyncSession, user_id: int, today: date) -> bool:
    """Monday: the latest forecast becomes this week's snapshot (once a week)."""
    monday = today - timedelta(days=today.weekday())
    last = await forecasts.last_weekly_snapshot(db, user_id)
    latest = await forecasts.latest(db, user_id)
    goal = await db.scalar(
        select(m.Goal.id).where(m.Goal.user_id == user_id, m.Goal.status == "active")
    )
    if latest is None or goal is None or (last and last.sim_date and last.sim_date >= monday):
        return False
    snapshot = latest.model_copy(update={"is_weekly_snapshot": True, "sim_date": today})
    await forecasts.save(db, user_id, snapshot, goal_id=goal, reason="weekly snapshot")
    return True


async def weekly_reflection(db: AsyncSession, user_id: int, today: date) -> None:
    """Sunday: the motivation check (it uses the day's question, D25)."""
    await agent_events.create(db, user_id, type=AgentEventType.WEEKLY_REFLECTION, event_date=today)


async def preemptive(db: AsyncSession, user_id: int, today: date) -> int:
    """A planned life event tomorrow → a preemptive check-in."""
    tomorrow = [
        e
        for e in await life_events.list_planned(db, user_id)
        if e.date == today + timedelta(days=1)
    ]
    if tomorrow:
        await agent_events.create(
            db,
            user_id,
            type=AgentEventType.PREEMPTIVE_CHECKIN,
            event_date=today,
            payload={"life_event_ids": [e.id for e in tomorrow]},
        )
    return len(tomorrow)


async def infer_hypotheses(db: AsyncSession, user_id: int) -> int:
    """C10's guesses → hypothesis facts + a 1-tap card each (`fact.hypothesis`)."""
    drafts = await ports.infer_hypotheses(db, user_id)
    for draft in drafts:
        fact = await life_facts.create(
            db,
            user_id,
            draft.replace(source=FactSource.INFERRED, status=FactStatus.HYPOTHESIS),
        )
        # Our LifeFactDraft has no separate question: the card shows the fact's own words.
        push_after_commit(db, user_id, events.fact_hypothesis(fact, draft.text))
    return len(drafts)
