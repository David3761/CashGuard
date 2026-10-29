"""B2 step 3: conversation tables (agent_events, messages, notifications, runs, tool calls)."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import delete, func, select, text

from app.db import models as m
from app.domain.enums import AgentEventType
from tests import factories as f
from tests.db.test_schema_core import accepted, rejected

DAY = date(2026, 6, 15)


def event(user_id, type_, day=DAY, **kw):
    return m.AgentEvent(user_id=user_id, type=type_, event_date=day, **kw)


def test_every_event_type_is_either_day_level_or_transaction_level():
    day, tx = set(m.DAY_LEVEL_EVENT_TYPES), set(m.TRANSACTION_EVENT_TYPES)
    assert day.isdisjoint(tx)
    assert day | tx == set(AgentEventType)
    assert tx == {AgentEventType.TRANSACTION_QUESTION}


async def test_event_defaults(db, fixed_clock):
    u = await f.user(db)
    ev = await accepted(db, event(u.id, "overspend"))
    await db.refresh(ev)
    assert ev.status == "pending"
    assert ev.payload == {}
    assert ev.created_at == fixed_clock.now()


async def test_two_day_level_events_of_one_type_on_one_date_rejected(db):
    u = await f.user(db)
    await accepted(db, event(u.id, "overspend"))
    await rejected(db, event(u.id, "overspend"))


async def test_day_level_events_differ_by_date_type_or_user(db):
    a, b = await f.user(db), await f.user(db)
    await accepted(db, event(a.id, "overspend"))
    await accepted(db, event(a.id, "overspend", day=date(2026, 6, 16)))
    await accepted(db, event(a.id, "warning"))
    await accepted(db, event(b.id, "overspend"))


async def test_transaction_questions_for_different_transactions_same_day_ok(db):
    u = await f.user(db)
    t1, t2 = await f.transaction(db, u.id), await f.transaction(db, u.id)
    await accepted(db, event(u.id, "transaction_question", ref_transaction_id=t1.id))
    await accepted(db, event(u.id, "transaction_question", ref_transaction_id=t2.id))


async def test_same_transaction_question_twice_rejected_even_on_another_day(db):
    u = await f.user(db)
    t = await f.transaction(db, u.id)
    await accepted(db, event(u.id, "transaction_question", ref_transaction_id=t.id))
    await rejected(
        db, event(u.id, "transaction_question", day=date(2026, 6, 16), ref_transaction_id=t.id)
    )


async def test_transaction_question_needs_its_transaction(db):
    u = await f.user(db)
    await rejected(db, event(u.id, "transaction_question"))


@pytest.mark.parametrize(("field", "value"), [("type", "nag"), ("status", "snoozed")])
async def test_event_unknown_enum_value_rejected(db, field, value):
    u = await f.user(db)
    await rejected(
        db, m.AgentEvent(user_id=u.id, event_date=DAY, **({"type": "overspend"} | {field: value}))
    )


async def test_event_payload_keeps_diacritics_and_emoji(db):
    u = await f.user(db)
    payload = {"reason": "~6× coșul obișnuit la Mega ăîșț 🛒"}
    ev_id = (await accepted(db, event(u.id, "overspend", payload=payload))).id
    db.expunge_all()
    assert await db.scalar(select(m.AgentEvent.payload).where(m.AgentEvent.id == ev_id)) == payload


async def test_timestamptz_keeps_the_instant(db):
    u = await f.user(db)
    instant = datetime(2026, 6, 14, 21, 30, tzinfo=UTC)  # 00:30 next day in Bucharest
    ev_id = (await accepted(db, event(u.id, "overspend", asked_at=instant))).id
    db.expunge_all()
    stored = await db.scalar(select(m.AgentEvent.asked_at).where(m.AgentEvent.id == ev_id))
    assert stored == instant and stored.tzinfo is not None


async def test_event_status_index_exists(db):
    defs = " ".join(
        r[0]
        for r in await db.execute(
            text("select indexdef from pg_indexes where tablename = 'agent_events'")
        )
    )
    assert "(user_id, status)" in defs


async def test_message_defaults_and_checks(db, fixed_clock):
    u = await f.user(db)
    msg = await accepted(db, m.Message(user_id=u.id, role="assistant", content="Ce a fost?"))
    await db.refresh(msg)
    assert (msg.speak, msg.quick_replies, msg.action_cards) == (False, [], [])
    assert msg.created_at == fixed_clock.now()
    await rejected(db, m.Message(user_id=u.id, role="system", content="x"))
    await rejected(db, m.Message(user_id=u.id, role="user", content="x", input_mode="telepathy"))


async def test_message_keeps_voice_fields(db):
    u = await f.user(db)
    t = await f.transaction(db, u.id)
    ev = await accepted(db, event(u.id, "transaction_question", ref_transaction_id=t.id))
    cards = [
        {"type": "request_payment", "receivable_id": 9, "label": "Trimite cererea (4 × 100 lei)"}
    ]
    msg = await accepted(
        db,
        m.Message(
            user_id=u.id,
            role="assistant",
            content="Am văzut 500 lei la Mega azi. Ce a fost?",
            quick_replies=["Doar pentru mine", "Și pentru alții"],
            speak=True,
            speak_text="Am văzut 500 de lei la Mega azi.",
            agent_event_id=ev.id,
            ref_transaction_id=t.id,
            action_cards=cards,
            input_mode=None,
        ),
    )
    await db.refresh(msg)
    assert msg.action_cards == cards and msg.speak_text.startswith("Am văzut")


async def test_message_ordering_index_exists(db):
    defs = " ".join(
        r[0]
        for r in await db.execute(
            text("select indexdef from pg_indexes where tablename = 'messages'")
        )
    )
    assert "(user_id, created_at)" in defs


async def test_deleting_a_transaction_keeps_messages_and_drops_its_question(db):
    u = await f.user(db)
    t = await f.transaction(db, u.id)
    ev = await accepted(db, event(u.id, "transaction_question", ref_transaction_id=t.id))
    msg = await accepted(
        db,
        m.Message(
            user_id=u.id,
            role="assistant",
            content="x",
            ref_transaction_id=t.id,
            agent_event_id=ev.id,
        ),
    )
    msg_id = msg.id
    await db.execute(delete(m.Transaction).where(m.Transaction.id == t.id))
    db.expunge_all()
    stored = await db.get(m.Message, msg_id)
    assert (
        stored is not None and stored.ref_transaction_id is None and stored.agent_event_id is None
    )
    assert (
        await db.scalar(
            select(func.count()).select_from(m.AgentEvent).where(m.AgentEvent.user_id == u.id)
        )
        == 0
    )


async def test_notification_defaults_and_links(db):
    u = await f.user(db)
    ev = await accepted(db, event(u.id, "overspend"))
    msg = await accepted(db, m.Message(user_id=u.id, role="assistant", content="x"))
    n = await accepted(
        db,
        m.Notification(
            user_id=u.id,
            type="overspend",
            title="Planul s-a actualizat",
            body="Bugetul nou: 30,40 lei/zi.",
            agent_event_id=ev.id,
            message_id=msg.id,
        ),
    )
    await db.refresh(n)
    assert (n.read, n.opens_chat) == (False, False)


async def test_agent_run_and_tool_calls(db, fixed_clock):
    u = await f.user(db)
    run = await accepted(db, m.AgentRun(user_id=u.id, trigger="chat", model="claude-sonnet-5-5"))
    await db.refresh(run)
    assert run.status == "running" and run.iterations == 0
    assert run.started_at == fixed_clock.now()
    call = await accepted(
        db,
        m.ToolCall(
            run_id=run.id,
            user_id=u.id,
            tool_name="annotate_transaction",
            input={"transaction_id": 918, "people_count": 5},
            output={"ok": True},
            status="ok",
        ),
    )
    await rejected(db, m.AgentRun(user_id=u.id, trigger="cron", model="x"))
    await rejected(db, m.AgentRun(user_id=u.id, trigger="chat", model="x", status="done"))
    await rejected(
        db, m.ToolCall(run_id=run.id, user_id=u.id, tool_name="x", input={}, status="meh")
    )
    # deleting the run deletes its tool calls
    call_id = call.id
    await db.execute(delete(m.AgentRun).where(m.AgentRun.id == run.id))
    db.expunge_all()
    assert await db.get(m.ToolCall, call_id) is None
