"""B8: ingest + process_user (spies replace the teammates' functions in app.pipeline.ports)."""

import asyncio
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app import clock
from app.clock import BUCHAREST
from app.db import models as m
from app.domain.enums import AgentEventType
from app.pipeline import ports
from app.pipeline.processor import process_user, recover_stale
from app.services import goals
from app.services.ingest import TxIn, ingest
from tests import factories as f
from tests.db.test_services_profile import fails

D = Decimal
NOON = datetime(2026, 6, 15, 12, 0, tzinfo=BUCHAREST)


def tx_in(**kw) -> TxIn:
    base = {
        "amount": D("500"),
        "merchant_raw": "MEGA IMAGE 0451 BUCURESTI",
        "occurred_at": NOON,
        "category": "groceries",
    }
    return TxIn(**(base | kw))


# ── ingest ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "kw",
    [
        {"amount": D("0")},
        {"amount": D("-5")},
        {"direction": "refund"},
        {"merchant_raw": ""},
        {"merchant_raw": "x" * 201},
        {"items": [{"name": "", "qty": 1}]},
        {"occurred_at": NOON + timedelta(days=2)},
        {"category": "luxury"},
    ],
)
async def test_ingest_rejects_invalid_transactions(db, kw):
    u = await f.user(db)
    await fails(ingest(db, u.id, kw), "invalid_transaction", 422)


async def test_ingest_stores_unresolved_and_calls_nothing(db, monkeypatch):
    called = []
    for name in ("evaluate_transaction", "apply_transaction", "recompute_plan"):
        monkeypatch.setattr(ports, name, lambda *a, n=name, **k: called.append(n))
    u = await f.user(db)
    tx_id = await ingest(db, u.id, tx_in(items=[{"name": 'Televizor 65"', "amount": 4500}]))
    row = await db.get(m.Transaction, tx_id)
    assert (row.status, row.effective_amount, row.source) == ("unresolved", D("500.00"), "sim")
    assert row.items[0]["name"] == 'Televizor 65"' and called == []


async def test_ingest_accepts_tomorrow_but_not_later(db):
    u = await f.user(db)
    await ingest(db, u.id, tx_in(occurred_at=NOON + timedelta(days=1)))


# ── process_user ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def spy(monkeypatch):
    """Records the order of calls; the real fallbacks still run behind the spies."""
    calls: list[tuple[str, int | None]] = []

    def wrap(name, tx_arg=True):
        real = getattr(ports, name)

        async def spy_fn(*args, **kw):
            calls.append((name, args[2] if tx_arg and len(args) > 2 else None))
            return await real(*args, **kw)

        monkeypatch.setattr(ports, name, spy_fn)

    for name in ("evaluate_transaction", "apply_transaction", "auto_save"):
        wrap(name)
    for name in ("recompute_plan", "forecast_goal", "pick_question"):
        wrap(name, tx_arg=False)

    async def proactive(user_id, event_id):
        calls.append(("run_proactive", event_id))

    monkeypatch.setattr(ports, "run_proactive", proactive)
    return calls


async def setup_user(db, n=3, with_goal=True):
    u = await f.user(db)
    db.add(m.Account(user_id=u.id, current_balance=D("2850")))
    if with_goal:
        await goals.create(db, u.id, amount=D("10000"), deadline=date(2026, 12, 31))
    ids = [await ingest(db, u.id, tx_in(amount=D("85") + i)) for i in range(n)]
    await db.commit()
    return u.id, ids


async def statuses(db, ids):
    rows = await db.scalars(
        select(m.Transaction).where(m.Transaction.id.in_(ids)).order_by(m.Transaction.id)
    )
    return [(r.status, r.attempts) for r in rows]


async def test_three_transactions_resolved_in_order(db_committed, spy):
    uid, ids = await setup_user(db_committed)
    result = await process_user(uid, "cron")
    assert result.resolved == 3 and result.failed == 0
    assert await statuses(db_committed, ids) == [("resolved", 0)] * 3
    per_tx = [c for c in spy if c[0] in ("evaluate_transaction", "apply_transaction")]
    assert per_tx == [(n, i) for i in ids for n in ("evaluate_transaction", "apply_transaction")]
    names = [c[0] for c in spy]
    assert names.index("recompute_plan") > names.index("apply_transaction")
    assert names.index("forecast_goal") > names.index("recompute_plan")
    acc = await db_committed.get(m.Account, uid, populate_existing=True)
    assert acc.current_balance == D("2850") - D("85") - D("86") - D("87")


async def test_an_error_on_one_transaction_does_not_stop_the_others(db_committed, monkeypatch):
    uid, ids = await setup_user(db_committed)
    real = ports.evaluate_transaction

    async def flaky(db, user_id, tx_id):
        if tx_id == ids[1]:
            raise RuntimeError("context exploded")
        return await real(db, user_id, tx_id)

    monkeypatch.setattr(ports, "evaluate_transaction", flaky)
    await process_user(uid, "cron")
    assert await statuses(db_committed, ids) == [
        ("resolved", 0),
        ("unresolved", 1),
        ("resolved", 0),
    ]
    await process_user(uid, "cron")
    await process_user(uid, "cron")
    rows = await statuses(db_committed, [ids[1]])
    assert rows == [("failed", 3)]
    assert (
        await db_committed.get(m.Transaction, ids[1], populate_existing=True)
    ).error == "context exploded"


async def test_recover_only_touches_rows_stuck_for_5_minutes(db_committed):
    _, ids = await setup_user(db_committed, n=2, with_goal=False)
    old, fresh = ids
    for tx_id, minutes in ((old, 6), (fresh, 4)):
        row = await db_committed.get(m.Transaction, tx_id)
        row.status = "processing"
        row.locked_at = clock.now() - timedelta(minutes=minutes)
    await db_committed.commit()
    assert await recover_stale() == 1
    assert [s for s, _ in await statuses(db_committed, ids)] == ["unresolved", "processing"]


async def test_nothing_to_process_changes_nothing(db_committed, spy):
    uid, _ = await setup_user(db_committed, n=0)
    await process_user(uid, "cron")
    assert spy == []
    assert await db_committed.scalar(select(func.count()).select_from(m.Plan)) == 0


async def test_salary_auto_saved_once(db_committed, spy):
    u = await f.user(db_committed)
    # danutu's apply_transaction moves the balance: every user has an account (arch 4.2)
    db_committed.add(m.Account(user_id=u.id, current_balance=D("0")))
    salary = await ingest(
        db_committed, u.id, tx_in(amount=D("7000"), direction="credit", category="income")
    )
    await db_committed.commit()
    await process_user(u.id, "cron")
    await process_user(u.id, "cron")
    assert [c for c in spy if c[0] == "auto_save"] == [("auto_save", salary)]


@pytest.mark.parametrize(("trigger", "proactive"), [("sim", True), ("cron", True), ("chat", False)])
async def test_question_created_and_proactive_only_outside_chat(
    db_committed, spy, trigger, proactive
):
    uid, _ = await setup_user(db_committed, n=0)
    big = await ingest(db_committed, uid, tx_in(amount=D("500")))
    await db_committed.commit()
    await process_user(uid, trigger)
    events = list(await db_committed.scalars(select(m.AgentEvent)))
    assert [(e.type, e.ref_transaction_id) for e in events] == [
        (AgentEventType.TRANSACTION_QUESTION, big)
    ]
    assert (("run_proactive", events[0].id) in spy) is proactive


async def test_two_concurrent_runs_apply_each_transaction_once(db_committed, spy):
    uid, ids = await setup_user(db_committed)
    await asyncio.gather(process_user(uid, "cron"), process_user(uid, "chat"))
    applied = sorted(i for n, i in spy if n == "apply_transaction")
    assert applied == sorted(ids)
    acc = await db_committed.get(m.Account, uid, populate_existing=True)
    await db_committed.refresh(acc)
    assert acc.current_balance == D("2850") - D("258")


async def test_resolved_and_annotated_events_are_pushed_after_commit(db_committed, spy):
    from app.ws import manager

    class Sock:
        def __init__(self):
            self.got = []

        async def send_json(self, data):
            self.got.append(data["type"])

    uid, _ = await setup_user(db_committed, n=1)
    sock = Sock()
    manager.connect(uid, sock)
    try:
        await process_user(uid, "cron")
        await asyncio.sleep(0)
    finally:
        manager.disconnect(uid, sock)
    assert sock.got[:2] == ["transaction.resolved", "transaction.annotated"]
    assert "plan.updated" in sock.got and "forecast.updated" in sock.got
