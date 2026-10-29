"""B11: day jobs."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app import clock
from app.clock import BUCHAREST, FixedClock
from app.db import models as m
from app.domain.enums import LedgerStatus
from app.domain.results import Forecast, PlanResult
from app.pipeline import jobs
from app.pipeline.day_jobs import Job, day_sequence
from app.services import agent_events, forecasts, goals, notifications, plans
from tests import factories as f

D = Decimal
DAY = date(2026, 6, 15)


def at(day: date, hh: int, mm: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=BUCHAREST)


@pytest.mark.parametrize(
    ("spent", "status"),
    [
        ("100.01", LedgerStatus.OVERSPENT),
        ("100", LedgerStatus.OK),
        ("50", LedgerStatus.OK),
        ("49.99", LedgerStatus.UNDER),
        ("0", LedgerStatus.UNDER),
    ],
)
def test_ledger_status_boundaries(spent, status):
    assert jobs.ledger_status(D(spent), D("100")) == status


async def user_with_plan(db, budget="100"):
    u = await f.user(db)
    await goals.create(db, u.id, amount=D("1000"), deadline=date(2026, 12, 31))
    await plans.save(db, u.id, PlanResult(today_budget=D(budget), feasible=True), reason="x")
    return u


async def test_close_day_overspend_becomes_the_question_when_free(db):
    u = await user_with_plan(db)
    db.add(m.DayLedger(user_id=u.id, date=DAY, spent=D("185")))
    await db.flush()
    assert await jobs.close_day(db, u.id, DAY) == LedgerStatus.OVERSPENT
    assert await jobs.close_day(db, u.id, DAY) == LedgerStatus.OVERSPENT  # idempotent
    events = await agent_events.pending_for(db, u.id)
    assert [e.type for e in events] == ["overspend"] and events[0].payload["over"] == 85.0
    assert await notifications.list_all(db, u.id) == []


async def test_close_day_overspend_is_a_quiet_notification_when_the_question_is_used(db):
    u = await user_with_plan(db)
    db.add(m.DayLedger(user_id=u.id, date=DAY, spent=D("185")))
    tx = await f.transaction(db, u.id)
    q = await agent_events.create(
        db, u.id, type="transaction_question", event_date=DAY, ref_transaction_id=tx.id
    )
    await agent_events.mark_asked(db, u.id, q.id)
    await jobs.close_day(db, u.id, DAY)
    await jobs.close_day(db, u.id, DAY)
    assert [n.type for n in await notifications.list_all(db, u.id)] == ["overspend"]
    assert [e.type for e in await agent_events.pending_for(db, u.id)] == []


async def test_streak_milestone_notification(db):
    u = await user_with_plan(db)
    for back in (1, 2):
        db.add(
            m.DayLedger(
                user_id=u.id,
                date=DAY - timedelta(days=back),
                status="ok",
                budget=D("100"),
                spent=D("80"),
            )
        )
    db.add(m.DayLedger(user_id=u.id, date=DAY, budget=D("100"), spent=D("80")))
    await db.flush()
    await jobs.close_day(db, u.id, DAY)
    assert [n.type for n in await notifications.list_all(db, u.id)] == ["streak"]


@pytest.mark.parametrize(("minutes", "expired"), [(23 * 60 + 59, False), (24 * 60 + 1, True)])
async def test_unanswered_question_gets_the_default_reading_after_24h(db, minutes, expired):
    u = await f.user(db)
    tx = await f.transaction(db, u.id, status="resolved", purpose="unknown")
    q = await agent_events.create(
        db, u.id, type="transaction_question", event_date=DAY, ref_transaction_id=tx.id
    )
    clock.set_clock(FixedClock(at(DAY, 13, 6)))
    await agent_events.mark_asked(db, u.id, q.id)
    now = at(DAY, 13, 6) + timedelta(minutes=minutes)
    assert await jobs.expire_questions(db, u.id, now) == int(expired)
    row = await db.get(m.Transaction, tx.id, populate_existing=True)
    if expired:
        assert (row.purpose, row.annotation_source, row.annotation_confidence) == (
            "unplanned_discretionary",
            "default",
            D("0.3000"),
        )
        assert (await agent_events.get(db, u.id, q.id)).status == "expired"
    else:
        assert row.annotation_source is None


async def test_answered_question_is_untouched(db):
    u = await f.user(db)
    tx = await f.transaction(db, u.id)
    q = await agent_events.create(
        db, u.id, type="transaction_question", event_date=DAY, ref_transaction_id=tx.id
    )
    await agent_events.mark_asked(db, u.id, q.id)
    await agent_events.mark_answered(db, u.id, q.id)
    assert await jobs.expire_questions(db, u.id, at(DAY, 12) + timedelta(days=3)) == 0


async def test_pending_events_expire_after_48h(db):
    u = await f.user(db)
    clock.set_clock(FixedClock(at(DAY, 9)))
    await agent_events.create(db, u.id, type="warning", event_date=DAY)
    assert await jobs.expire_events(db, u.id, at(DAY, 9) + timedelta(hours=47)) == 0
    assert await jobs.expire_events(db, u.id, at(DAY, 9) + timedelta(hours=49)) == 1


async def test_receivable_reminder_after_14_days_once_a_day(db):
    u = await f.user(db)
    clock.set_clock(FixedClock(at(DAY, 9)))
    db.add(
        m.Receivable(
            user_id=u.id,
            amount=D("400"),
            debtor_label="colegi",
            expected_by=DAY + timedelta(days=14),
        )
    )
    await db.flush()
    assert await jobs.receivable_reminders(db, u.id, DAY + timedelta(days=13)) == 0
    assert await jobs.receivable_reminders(db, u.id, DAY + timedelta(days=14)) == 1
    await jobs.receivable_reminders(db, u.id, DAY + timedelta(days=14))
    n = await db.scalar(select(func.count()).select_from(m.AgentEvent))
    assert n == 1


async def test_forecast_snapshot_once_per_week(db):
    u = await f.user(db)
    g = await goals.create(db, u.id, amount=D("1000"), deadline=date(2026, 12, 31))
    await forecasts.save(
        db,
        u.id,
        Forecast(
            probability=0.78, p10=D("1"), p50=D("2"), p90=D("3"), plan_version=1, sim_date=DAY
        ),
        goal_id=g.id,
    )
    assert await jobs.forecast_snapshot(db, u.id, DAY) is True
    assert await jobs.forecast_snapshot(db, u.id, DAY) is False
    assert (await forecasts.last_weekly_snapshot(db, u.id)).probability == 0.78
    assert await jobs.forecast_snapshot(db, u.id, DAY + timedelta(days=7)) is True


async def test_preemptive_and_weekly_reflection(db):
    u = await f.user(db)
    db.add(
        m.LifeEvent(
            user_id=u.id,
            name="Concert",
            date=DAY + timedelta(days=1),
            est_cost=D("100"),
            type="social",
        )
    )
    await db.flush()
    assert await jobs.preemptive(db, u.id, DAY) == 1
    await jobs.weekly_reflection(db, u.id, DAY)
    types = sorted(e.type for e in await agent_events.pending_for(db, u.id))
    assert types == ["preemptive_checkin", "weekly_reflection"]


def test_sim_day_order():
    monday, sunday, wednesday = date(2026, 6, 15), date(2026, 6, 21), date(2026, 6, 17)
    assert day_sequence(wednesday) == [
        Job.CLOSE_DAY,
        Job.EXPIRE_QUESTIONS,
        Job.EXPIRE_EVENTS,
        Job.RECEIVABLE_REMINDERS,
    ]
    assert day_sequence(monday)[-1] == Job.FORECAST_SNAPSHOT
    assert day_sequence(sunday)[-2:] == [Job.WEEKLY_REFLECTION, Job.INFER_HYPOTHESES]
