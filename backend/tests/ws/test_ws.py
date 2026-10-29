"""B7: event builders, ConnectionManager, push_after_commit, the /ws route."""

import asyncio
from decimal import Decimal

import pytest
from starlette.websockets import WebSocketDisconnect

from app import events
from app.domain.results import PlanSummary
from app.ws import ConnectionManager, manager, push_after_commit
from tests import builders as b
from tests import factories as f

ARCH_KEYS = {
    "agent.typing": set(),
    "plan.updated": {"version", "today_budget", "feasible"},
    "transaction.resolved": {"id", "status"},
    "transaction.annotated": {
        "id",
        "amount",
        "effective_amount",
        "purpose",
        "purpose_label",
        "explanation",
        "decision",
        "receivable_id",
        "pot_id",
    },
}


def test_builders_have_the_arch_keys_utc_ts_and_numeric_money():
    tx = b.tx(amount=Decimal("500"), effective_amount=Decimal("100"))
    built = [
        events.agent_typing(),
        events.plan_updated(PlanSummary(version=8, feasible=True, today_budget=Decimal("29.80"))),
        events.transaction_resolved(tx),
        events.transaction_annotated(tx, "Pentru alții"),
    ]
    for e in built:
        assert set(e["data"]) == ARCH_KEYS[e["type"]]
        assert e["ts"].endswith("Z")
    assert built[1]["data"]["today_budget"] == 29.8
    assert built[3]["data"]["effective_amount"] == 100.0


class FakeSocket:
    def __init__(self, dead: bool = False) -> None:
        self.got: list[dict] = []
        self.dead = dead

    async def send_json(self, data):
        if self.dead:
            raise RuntimeError("closed")
        self.got.append(data)


async def test_push_reaches_all_of_a_users_sockets_and_none_of_others():
    mgr = ConnectionManager()
    a1, a2, b1, dead = FakeSocket(), FakeSocket(), FakeSocket(), FakeSocket(dead=True)
    for s in (a1, a2, dead):
        mgr.connect(1, s)
    mgr.connect(2, b1)
    await mgr.push(1, events.agent_typing())
    assert len(a1.got) == len(a2.got) == 1 and b1.got == []
    assert mgr.count(1) == 2  # the dead socket was dropped
    await mgr.push(99, events.agent_typing())  # nobody connected: no-op
    mgr.disconnect(1, a1)
    mgr.disconnect(1, a2)
    assert mgr.count(1) == 0


@pytest.fixture
def listener():
    sock = FakeSocket()
    manager.connect(7, sock)
    yield sock
    manager.disconnect(7, sock)


async def test_push_after_commit_sends_in_order_only_on_commit(db_committed, listener):
    u = await f.user(db_committed)
    push_after_commit(db_committed, 7, events.agent_typing())
    push_after_commit(db_committed, 7, events.transaction_resolved(b.tx(id=1)))
    assert listener.got == []
    await db_committed.commit()
    await asyncio.sleep(0)
    assert [e["type"] for e in listener.got] == ["agent.typing", "transaction.resolved"]
    assert u.id


async def test_push_after_commit_rollback_drops_the_events(db_committed, listener):
    await f.user(db_committed)
    push_after_commit(db_committed, 7, events.agent_typing())
    await db_committed.rollback()
    await db_committed.commit()
    await asyncio.sleep(0)
    assert listener.got == []


def test_ws_with_a_bad_token_is_closed_1008(ws_connect):
    with pytest.raises(WebSocketDisconnect) as closed, ws_connect("x", token="garbage") as ws:
        ws.receive_json()
    assert closed.value.code == 1008
