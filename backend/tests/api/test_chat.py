"""B9: POST /chat + the background agent run (committed data: the run uses its own sessions)."""

import pytest
from sqlalchemy import select

from app.db import models as m
from app.domain.enums import Language
from app.domain.results import AgentResult
from app.pipeline import ports
from app.ws import manager
from tests import factories as f


class Sock:
    def __init__(self):
        self.got = []

    async def send_json(self, data):
        self.got.append(data["type"])


@pytest.fixture
async def user(db_committed):
    u = await f.user(db_committed)
    await db_committed.commit()
    return u


@pytest.fixture
def sock(user):
    s = Sock()
    manager.connect(user.id, s)
    yield s
    manager.disconnect(user.id, s)


async def messages_of(db, user_id):
    rows = await db.scalars(
        select(m.Message)
        .where(m.Message.user_id == user_id)
        .order_by(m.Message.id)
        .execution_options(populate_existing=True)
    )
    return list(rows)


async def test_chat_returns_202_and_the_reply_arrives(as_committed_user, db_committed, user, sock):
    r = await as_committed_user(user).post(
        "/chat", json={"text": "  Salut!  ", "input_mode": "voice"}
    )
    assert r.status_code == 202
    body = r.json()
    msgs = await messages_of(db_committed, user.id)
    assert [(x.role, x.content) for x in msgs] == [
        ("user", "Salut!"),
        ("assistant", "Am primit: Salut!"),
    ]
    assert msgs[0].id == body["message_id"] and msgs[0].input_mode == "voice"
    assert msgs[1].speak is True
    run = await db_committed.get(m.AgentRun, body["run_id"], populate_existing=True)
    assert run.status == "completed"
    assert sock.got == ["agent.typing", "assistant.message"]


@pytest.mark.parametrize(
    "payload",
    [
        {"text": ""},
        {"text": "   "},
        {"text": "x" * 2001},
        {"text": "hi", "input_mode": "telepathy"},
        {},
    ],
)
async def test_chat_rejects_bad_bodies(as_committed_user, user, payload):
    r = await as_committed_user(user).post("/chat", json=payload)
    assert r.status_code == 422


async def test_chat_while_a_run_is_running_is_409(as_committed_user, db_committed, user):
    db_committed.add(m.AgentRun(user_id=user.id, trigger="chat", model="x", status="running"))
    await db_committed.commit()
    r = await as_committed_user(user).post("/chat", json={"text": "hei"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "agent_busy"


async def test_plan_updated_only_when_the_plan_changed(
    as_committed_user, db_committed, user, sock, monkeypatch
):
    from datetime import date
    from decimal import Decimal

    from app.services import goals

    await goals.create(db_committed, user.id, amount=Decimal("100"), deadline=date(2026, 12, 31))
    await db_committed.commit()
    await as_committed_user(user).post("/chat", json={"text": "fără schimbări"})
    assert "plan.updated" not in sock.got

    async def replanning_agent(user_id, trigger, text, mode):
        from app.db.session import unit_of_work

        async with unit_of_work() as db:
            plan = await ports.recompute_plan(db, user_id, reason="tool")
            await ports.forecast_goal(db, user_id, plan.version)
        return AgentResult(text="Gata", plan_changed=True)

    monkeypatch.setattr(ports, "run_agent", replanning_agent)
    sock.got.clear()
    await as_committed_user(user).post("/chat", json={"text": "adaugă concertul"})
    assert sock.got == ["agent.typing", "assistant.message", "plan.updated", "forecast.updated"]


async def test_agent_failure_gives_the_fallback_and_frees_the_user(
    as_committed_user, db_committed, user, sock, monkeypatch
):
    async def broken(*_a, **_k):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(ports, "run_agent", broken)
    r = await as_committed_user(user).post("/chat", json={"text": "hei"})
    msgs = await messages_of(db_committed, user.id)
    assert msgs[-1].content.startswith("Am o problemă acum")
    run = await db_committed.get(m.AgentRun, r.json()["run_id"], populate_existing=True)
    assert (run.status, run.error) == ("failed", "LLM down")
    assert sock.got == ["agent.typing", "assistant.message"]
    monkeypatch.undo()
    assert (
        await as_committed_user(user).post("/chat", json={"text": "din nou"})
    ).status_code == 202


async def test_english_message_switches_the_language(
    as_committed_user, db_committed, user, monkeypatch
):
    monkeypatch.setattr(ports, "detect_language", lambda text, current: Language.EN)
    await as_committed_user(user).post("/chat", json={"text": "I bought it for my colleagues"})
    row = await db_committed.get(m.User, user.id, populate_existing=True)
    assert row.language == "en"


async def test_chat_needs_a_token(committed_client):
    assert (await committed_client.post("/chat", json={"text": "x"})).status_code == 401
