"""B3 step 3: conversation services (agent events, messages, notifications, runs, tool calls)."""

from datetime import date, datetime, time, timedelta

import pytest

from app import clock
from app.clock import BUCHAREST, FixedClock
from app.db import models as m
from app.domain.enums import (
    AgentEventStatus,
    AgentEventType,
    AgentRunStatus,
    AgentTrigger,
    InputMode,
    ToolCallStatus,
)
from app.services import agent_events, agent_runs, messages, notifications, tool_calls
from tests import factories as f
from tests.db.test_services_profile import fails, two  # noqa: F401  (fixture)

DAY = date(2026, 6, 15)
T = AgentEventType


def set_time(day: date, hh: int, mm: int) -> None:
    clock.set_clock(FixedClock(datetime.combine(day, time(hh, mm), tzinfo=BUCHAREST)))


async def event(db, user_id, type_=T.OVERSPEND, **kw):
    return await agent_events.create(db, user_id, type=type_, event_date=kw.pop("day", DAY), **kw)


# ── agent events: create + dedup ─────────────────────────────────────────────────────────


async def test_create_pending_event(db, fixed_clock):
    u = await f.user(db)
    ev = await event(db, u.id, payload={"over": 85})
    assert (ev.status, ev.payload, ev.event_date) == (AgentEventStatus.PENDING, {"over": 85}, DAY)
    assert ev.created_at == fixed_clock.now()
    assert await agent_events.get(db, u.id, ev.id) == ev


async def test_same_day_level_event_twice_returns_the_existing_one(db):
    u = await f.user(db)
    first = await event(db, u.id)
    again = await event(db, u.id, payload={"different": True})
    assert again.id == first.id
    other_day = await event(db, u.id, day=DAY + timedelta(days=1))
    assert other_day.id != first.id


async def test_transaction_questions_dedup_per_transaction(db):
    u = await f.user(db)
    t1, t2 = await f.transaction(db, u.id), await f.transaction(db, u.id)
    q1 = await event(db, u.id, T.TRANSACTION_QUESTION, ref_transaction_id=t1.id)
    q2 = await event(db, u.id, T.TRANSACTION_QUESTION, ref_transaction_id=t2.id)
    assert q1.id != q2.id
    again = await event(
        db, u.id, T.TRANSACTION_QUESTION, ref_transaction_id=t1.id, day=DAY + timedelta(days=1)
    )
    assert again.id == q1.id


async def test_transaction_question_needs_its_transaction(db):
    u = await f.user(db)
    await fails(event(db, u.id, T.TRANSACTION_QUESTION), "missing_transaction", 422)


async def test_transaction_question_on_another_users_transaction_is_not_found(two, db):  # noqa: F811
    a, b = two
    t = await f.transaction(db, b.id)
    await fails(event(db, a.id, T.TRANSACTION_QUESTION, ref_transaction_id=t.id), "not_found")


# ── agent events: state machine ──────────────────────────────────────────────────────────

VALID = [
    ([], "mark_asked", AgentEventStatus.ASKED),
    ([], "mark_handled", AgentEventStatus.HANDLED),
    ([], "expire", AgentEventStatus.EXPIRED),
    (["mark_asked"], "mark_answered", AgentEventStatus.ANSWERED),
    (["mark_asked"], "mark_handled", AgentEventStatus.HANDLED),
    (["mark_asked"], "expire", AgentEventStatus.EXPIRED),
]
INVALID = [
    ([], "mark_answered"),  # never asked
    (["mark_asked"], "mark_asked"),
    (["mark_asked", "mark_answered"], "mark_asked"),
    (["mark_asked", "mark_answered"], "mark_handled"),
    (["mark_asked", "mark_answered"], "expire"),
    (["mark_handled"], "mark_asked"),
    (["expire"], "mark_handled"),
    (["expire"], "expire"),
]


@pytest.mark.parametrize(("before", "action", "expected"), VALID)
async def test_valid_transitions(db, fixed_clock, before, action, expected):
    u = await f.user(db)
    ev = await event(db, u.id)
    for step in before:
        await getattr(agent_events, step)(db, u.id, ev.id)
    done = await getattr(agent_events, action)(db, u.id, ev.id)
    assert done.status == expected
    if action == "mark_asked":
        assert done.asked_at == fixed_clock.now()
    if action == "mark_answered":
        assert done.answered_at == fixed_clock.now()


@pytest.mark.parametrize(("before", "action"), INVALID)
async def test_invalid_transitions(db, before, action):
    u = await f.user(db)
    ev = await event(db, u.id)
    for step in before:
        await getattr(agent_events, step)(db, u.id, ev.id)
    await fails(getattr(agent_events, action)(db, u.id, ev.id), "invalid_transition", 409)


async def test_events_isolation(two, db):  # noqa: F811
    a, b = two
    ev = await event(db, b.id)
    for name in ("get", "mark_asked", "mark_answered", "mark_handled", "expire"):
        await fails(getattr(agent_events, name)(db, a.id, ev.id), "not_found", 404)
    assert await agent_events.pending_for(db, a.id) == []
    assert await agent_events.open_question(db, a.id) is None


# ── agent events: queries ────────────────────────────────────────────────────────────────


async def test_pending_for_oldest_first_without_handled(db):
    u = await f.user(db)
    set_time(DAY, 9, 0)
    first = await event(db, u.id, T.WARNING)
    set_time(DAY, 10, 0)
    second = await event(db, u.id, T.OVERSPEND)
    handled = await event(db, u.id, T.GOAL_COMPLETED)
    await agent_events.mark_handled(db, u.id, handled.id)
    assert [e.id for e in await agent_events.pending_for(db, u.id)] == [first.id, second.id]


async def test_open_question_is_the_newest_asked_one(db):
    u = await f.user(db)
    t1, t2 = await f.transaction(db, u.id), await f.transaction(db, u.id)
    assert await agent_events.open_question(db, u.id) is None
    set_time(DAY, 13, 6)
    q1 = await event(db, u.id, T.TRANSACTION_QUESTION, ref_transaction_id=t1.id)
    await agent_events.mark_asked(db, u.id, q1.id)
    assert (await agent_events.open_question(db, u.id)).ref_transaction_id == t1.id
    set_time(DAY + timedelta(days=1), 13, 6)
    q2 = await event(
        db, u.id, T.TRANSACTION_QUESTION, ref_transaction_id=t2.id, day=DAY + timedelta(days=1)
    )
    await agent_events.mark_asked(db, u.id, q2.id)
    assert (await agent_events.open_question(db, u.id)).id == q2.id
    await agent_events.mark_answered(db, u.id, q2.id)
    await agent_events.mark_answered(db, u.id, q1.id)
    assert await agent_events.open_question(db, u.id) is None


@pytest.mark.parametrize(
    ("hh", "mm", "day", "expected"),
    [
        (23, 59, DAY, True),
        (0, 1, DAY + timedelta(days=1), False),
        (0, 0, DAY, True),
        (23, 59, DAY - timedelta(days=1), False),
    ],
)
async def test_question_asked_today_uses_bucharest_days(db, hh, mm, day, expected):
    u = await f.user(db)
    t = await f.transaction(db, u.id)
    q = await event(db, u.id, T.TRANSACTION_QUESTION, ref_transaction_id=t.id)
    set_time(day, hh, mm)
    await agent_events.mark_asked(db, u.id, q.id)
    assert await agent_events.question_asked_today(db, u.id, DAY) is expected


async def test_informational_events_do_not_use_the_question_budget(db):
    u = await f.user(db)
    for type_ in (T.GOAL_COMPLETED, T.HYPOTHESIS_CHECK, T.WARNING, T.CATEGORY_CAP):
        ev = await event(db, u.id, type_)
        await agent_events.mark_asked(db, u.id, ev.id)
    assert await agent_events.question_asked_today(db, u.id, DAY) is False
    reflection = await event(db, u.id, T.WEEKLY_REFLECTION)
    await agent_events.mark_asked(db, u.id, reflection.id)
    assert await agent_events.question_asked_today(db, u.id, DAY) is True


# ── messages ─────────────────────────────────────────────────────────────────────────────


async def test_save_user_and_assistant_messages(db):
    u = await f.user(db)
    t = await f.transaction(db, u.id)
    said = await messages.save_user(
        db, u.id, "Am luat și pentru colegi, suntem cinci", InputMode.VOICE
    )
    assert (said.role, said.input_mode) == ("user", InputMode.VOICE)
    reply = await messages.save_assistant(
        db,
        u.id,
        text="Cheltuiala ta reală e 100 lei.",
        speak_text="100 de lei ai tăi.",
        quick_replies=["Mulțumesc"],
        action_cards=[{"type": "request_payment", "receivable_id": 9, "label": "Trimite"}],
        ref_transaction_id=t.id,
        speak=True,
    )
    assert reply.role == "assistant" and reply.speak and reply.quick_replies == ("Mulțumesc",)
    assert reply.action_cards[0]["receivable_id"] == 9


async def test_save_user_rejects_an_unknown_input_mode(db):
    u = await f.user(db)
    await fails(messages.save_user(db, u.id, "x", "telepathy"), "invalid_input_mode", 422)


async def test_messages_since_is_exclusive_oldest_first_and_limited(db):
    u = await f.user(db)
    stamps = []
    for i in range(5):
        set_time(DAY, 10, i)
        msg = await messages.save_user(db, u.id, f"m{i}", InputMode.TEXT)
        stamps.append(msg.created_at)
    every = await messages.list_all(db, u.id)
    assert [x.content for x in every] == ["m0", "m1", "m2", "m3", "m4"]
    after = await messages.list_all(db, u.id, since=stamps[1])
    assert [x.content for x in after] == ["m2", "m3", "m4"]
    assert [x.content for x in await messages.list_all(db, u.id, since=stamps[1], limit=2)] == [
        "m2",
        "m3",
    ]
    assert [x.content for x in await messages.recent(db, u.id, limit=2)] == ["m3", "m4"]


async def test_messages_isolation(two, db):  # noqa: F811
    a, b = two
    await messages.save_user(db, b.id, "secret", InputMode.TEXT)
    assert await messages.list_all(db, a.id) == []
    assert await messages.recent(db, a.id) == []


# ── notifications ────────────────────────────────────────────────────────────────────────


async def test_notifications_unread_read_count_since(db):
    u = await f.user(db)
    set_time(DAY, 21, 14)
    n1 = await notifications.create(
        db,
        u.id,
        type="overspend",
        title="Planul s-a actualizat",
        body="Bugetul nou: 30,40 lei/zi.",
        opens_chat=True,
    )
    set_time(DAY, 21, 15)
    n2 = await notifications.create(
        db, u.id, type="auto_save", title="Economii", body="Am pus 760 lei deoparte."
    )
    assert await notifications.unread_count(db, u.id) == 2
    read = await notifications.mark_read(db, u.id, n1.id)
    assert read.read is True
    assert (await notifications.mark_read(db, u.id, n1.id)).read is True  # idempotent
    assert await notifications.unread_count(db, u.id) == 1
    assert [x.id for x in await notifications.list_all(db, u.id, unread_only=True)] == [n2.id]
    assert [x.id for x in await notifications.list_all(db, u.id, since=n1.created_at)] == [n2.id]
    assert [x.id for x in await notifications.list_all(db, u.id)] == [n1.id, n2.id]


async def test_notifications_isolation(two, db):  # noqa: F811
    a, b = two
    n = await notifications.create(db, b.id, type="x", title="t", body="b")
    await fails(notifications.mark_read(db, a.id, n.id), "not_found", 404)
    assert await notifications.unread_count(db, a.id) == 0


# ── agent runs & tool calls ──────────────────────────────────────────────────────────────


async def test_agent_run_lifecycle_and_busy_flag(db):
    u = await f.user(db)
    assert await agent_runs.is_running(db, u.id) is False
    run_id = await agent_runs.start(db, u.id, trigger=AgentTrigger.CHAT, model="claude-sonnet-5-5")
    assert await agent_runs.is_running(db, u.id) is True
    await tool_calls.log(
        db,
        u.id,
        run_id,
        tool_name="annotate_transaction",
        input={"transaction_id": 918, "people_count": 5},
        output={"ok": True},
        status=ToolCallStatus.OK,
    )
    await agent_runs.finish(db, u.id, run_id, status=AgentRunStatus.COMPLETED, iterations=2)
    assert await agent_runs.is_running(db, u.id) is False
    run = await db.get(m.AgentRun, run_id)
    assert (run.status, run.iterations, run.finished_at is not None) == ("completed", 2, True)
    await fails(
        agent_runs.finish(db, u.id, run_id, status=AgentRunStatus.FAILED, iterations=2),
        "invalid_transition",
        409,
    )


async def test_a_stale_running_run_does_not_block_the_user(db):
    # a crash mid-run leaves status=running; after 2 minutes it no longer counts as busy
    u = await f.user(db)
    set_time(DAY, 12, 0)
    await agent_runs.start(db, u.id, trigger=AgentTrigger.CHAT, model="x")
    set_time(DAY, 12, 1)
    assert await agent_runs.is_running(db, u.id) is True
    set_time(DAY, 12, 3)
    assert await agent_runs.is_running(db, u.id) is False


async def test_failed_run_keeps_its_error(db):
    u = await f.user(db)
    run_id = await agent_runs.start(db, u.id, trigger=AgentTrigger.PROACTIVE, model="x")
    await agent_runs.finish(
        db, u.id, run_id, status=AgentRunStatus.FAILED, iterations=6, error="loop limit"
    )
    assert (await db.get(m.AgentRun, run_id)).error == "loop limit"


async def test_runs_and_tool_calls_isolation(two, db):  # noqa: F811
    a, b = two
    run_id = await agent_runs.start(db, b.id, trigger=AgentTrigger.CHAT, model="x")
    assert await agent_runs.is_running(db, a.id) is False
    await fails(
        agent_runs.finish(db, a.id, run_id, status=AgentRunStatus.COMPLETED, iterations=1),
        "not_found",
    )
    await fails(
        tool_calls.log(
            db, a.id, run_id, tool_name="x", input={}, output=None, status=ToolCallStatus.ERROR
        ),
        "not_found",
    )
