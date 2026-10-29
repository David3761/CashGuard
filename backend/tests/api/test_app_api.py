"""The app API (API_SPEC.md, David V.'s Flutter app): every route, the SSE chat, the errors.

Committed data (`db_committed`): the chat stores its reply from a task with its own sessions.
The agent is always the fake runner of the `runner` fixture: nothing here can reach an LLM.
"""

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.app_api import chat
from app.app_api.mapping import TRANSFER_ID_OFFSET
from app.config import Settings
from app.db import models as m
from app.domain.enums import InputMode, PotKind
from app.domain.results import AgentResult
from app.main import create_app
from app.pipeline import ports
from app.security import ratelimit
from app.services import accounts, messages, pots
from tests import factories as f

SUB = "app-api-demo-user"


def parse_sse(body: str) -> list[tuple[str, Any]]:
    """A port of the app's EventStreamClient: lines, `event:`/`data:`, blank line dispatches an
    event with data, `:` comments ignored, the default event name is `message`."""
    events: list[tuple[str, Any]] = []
    event, data = "message", list[str]()
    for line in body.splitlines():
        if line == "":
            if data:
                events.append((event, json.loads("\n".join(data))))
            event, data = "message", []
        elif line.startswith("event:"):
            event = line[6:].removeprefix(" ")
        elif line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))
    return events


def names(events: list[tuple[str, Any]]) -> list[str]:
    return [e for e, _ in events]


class Runner:
    """A fake agent: records calls, answers `reply` (or raises / waits)."""

    def __init__(self, reply: str = "Soldul tău e 2.847,35 lei. 🙂") -> None:
        self.reply = reply
        self.calls: list[tuple[int, int, str]] = []
        self.error: Exception | None = None
        self.gate: asyncio.Event | None = None

    async def __call__(self, user_id: int, run_id: int, text: str) -> AgentResult:
        self.calls.append((user_id, run_id, text))
        if self.gate is not None:
            await self.gate.wait()
        if self.error is not None:
            raise self.error
        return AgentResult(text=self.reply, quick_replies=("Da", "Nu"))


@pytest.fixture
def runner() -> Runner:
    return Runner()


@pytest.fixture(autouse=True)
def _fresh_limits() -> Iterator[None]:
    ratelimit.reset()
    yield
    ratelimit.reset()


@pytest.fixture
def make_app(runner: Runner, db_committed: Any) -> Callable[..., FastAPI]:
    """Apps on committed data (`db_committed` points the app's sessions at the test DB)."""

    def make(**overrides: Any) -> FastAPI:
        settings = Settings(_env_file=None, APP_API_ENABLED=True, APP_API_USER=SUB, **overrides)
        application = create_app(settings)
        application.dependency_overrides[chat.get_reply_runner] = lambda: runner
        return application

    return make


@pytest.fixture
async def client(
    make_app: Callable[..., FastAPI], monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setattr(chat, "DELTA_PAUSE_S", 0.0)
    transport = httpx.ASGITransport(app=make_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def user(db_committed: Any) -> m.User:
    u = await f.user(db_committed, keycloak_sub=SUB, name="Matei")
    await accounts.create(db_committed, u.id, current_balance=Decimal("2847.35"))
    await db_committed.commit()
    return u


async def settle() -> None:
    """Let the reply tasks finish (they free the lock in their `finally`)."""
    pending = list(chat._tasks)
    if pending:
        await asyncio.wait(pending, timeout=5)


async def count(db: Any, model: type[Any], **where: Any) -> int:
    stmt = select(func.count()).select_from(model).filter_by(**where)
    return int(await db.scalar(stmt.execution_options(populate_existing=True)) or 0)


# ── mounting, auth, errors ───────────────────────────────────────────────────────────────


async def test_routes_need_no_token_and_are_tagged_app(client, user):
    r = await client.get("/balance")
    assert r.status_code == 200
    assert "authorization" not in r.request.headers
    paths = create_app(Settings(_env_file=None, APP_API_ENABLED=True)).openapi()["paths"]
    for path in (
        "/balance",
        "/transactions",
        "/devices",
        "/devices/{fcm_token}",
        "/assistant/messages",
    ):
        assert all(op["tags"] == ["app"] for op in paths[path].values()), path


async def test_disabled_by_default_in_code():
    application = create_app(Settings(_env_file=None))
    assert "/balance" not in {getattr(route, "path", "") for route in application.routes}


async def test_unknown_demo_user_is_503_message(client):
    r = await client.get("/balance")
    assert r.status_code == 503
    assert r.json() == {
        "message": "The demo account isn't set up yet. Seed the database and try again."
    }


async def test_api_routes_keep_the_envelope(client, user):
    r = await client.get("/api/me")
    assert r.status_code == 401
    assert set(r.json()) == {"error"}


async def test_numeric_user_id_works(make_app, user):
    application = make_app()
    application.state.settings = application.state.settings.model_copy(
        update={"APP_API_USER": str(user.id)}
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        assert (await c.get("/balance")).json() == {"balance": 284735, "currency": "RON"}


# ── balance & transactions ───────────────────────────────────────────────────────────────


async def test_balance_is_integer_bani(client, user):
    r = await client.get("/balance")
    assert r.json() == {"balance": 284735, "currency": "RON"}
    assert type(r.json()["balance"]) is int


async def test_transactions_feed(client, user, db_committed):
    other = await f.user(db_committed)
    await f.transaction(db_committed, other.id, merchant_raw="SECRET SHOP")
    await f.transaction(
        db_committed,
        user.id,
        amount=Decimal("18.50"),
        merchant_raw="MEGA IMAGE 0451 BUCURESTI",
        occurred_at=datetime(2026, 6, 15, 6, 42, tzinfo=UTC),
        category="groceries",
    )
    await f.transaction(
        db_committed,
        user.id,
        amount=Decimal("7000"),
        direction="credit",
        category="income",
        merchant_raw="SALARIU ACME SRL",
        occurred_at=datetime(2026, 6, 10, 9, 0, tzinfo=UTC),
    )
    await f.transaction(
        db_committed,
        user.id,
        amount=Decimal("2000"),
        category="housing_rent",
        merchant_raw="CHIRIE PROPRIETAR",
        occurred_at=datetime(2026, 6, 1, 6, 0, tzinfo=UTC),
    )
    pot = await pots.create(
        db_committed, user.id, name="Laptop", kind=PotKind.CUSTOM, target=Decimal("5000")
    )
    transfer = m.Transfer(
        user_id=user.id,
        amount=Decimal("700"),
        kind="auto_save",
        pot_id=pot.id,
        created_at=datetime(2026, 6, 10, 9, 5, tzinfo=UTC),
    )
    undone = m.Transfer(
        user_id=user.id,
        amount=Decimal("50"),
        kind="manual",
        created_at=datetime(2026, 6, 11, 9, 5, tzinfo=UTC),
        undone_at=datetime(2026, 6, 11, 9, 6, tzinfo=UTC),
    )
    db_committed.add_all([transfer, undone])
    await db_committed.commit()

    r = await client.get("/transactions")
    assert r.status_code == 200
    items = r.json()["transactions"]
    assert [(i["title"], i["amount"], i["type"], i["created_at"]) for i in items] == [
        ("Mega Image", -1850, "payment", "2026-06-15T06:42:00Z"),
        ("Laptop", -70000, "transfer_out", "2026-06-10T09:05:00Z"),
        ("Salariu Acme", 700000, "transfer_in", "2026-06-10T09:00:00Z"),
        ("Chirie Proprietar", -200000, "transfer_out", "2026-06-01T06:00:00Z"),
    ]
    assert items[1]["id"] == TRANSFER_ID_OFFSET + transfer.id
    for item in items:  # the Dart fromJson casts
        assert set(item) == {"id", "title", "amount", "type", "created_at"}
        assert type(item["id"]) is int
        assert item["id"] > 0
        assert type(item["amount"]) is int
        datetime.fromisoformat(item["created_at"])


async def test_empty_feed(client, user):
    assert (await client.get("/transactions")).json() == {"transactions": []}


# ── devices ──────────────────────────────────────────────────────────────────────────────


async def test_register_device_is_idempotent(client, user, db_committed):
    r = await client.post("/devices", json={"fcm_token": " tok:1 ", "platform": "android"})
    assert r.status_code == 200
    assert r.json() == {"fcm_token": "tok:1", "platform": "android"}
    r = await client.post("/devices", json={"fcm_token": "tok:1", "platform": "ios"})
    assert r.json() == {"fcm_token": "tok:1", "platform": "ios"}
    assert await count(db_committed, m.Device) == 1


async def test_device_cap_prunes_the_oldest(make_app, user, db_committed, monkeypatch):
    application = make_app(APP_API_MAX_DEVICES=2)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        for i in range(3):
            assert (
                await c.post("/devices", json={"fcm_token": f"t{i}", "platform": "android"})
            ).status_code == 200
    rows = await db_committed.scalars(
        select(m.Device.fcm_token).execution_options(populate_existing=True)
    )
    assert sorted(rows) == ["t1", "t2"]


@pytest.mark.parametrize(
    "body",
    [
        {"fcm_token": "t", "platform": "web"},
        {"platform": "android"},
        {"fcm_token": "", "platform": "ios"},
        {"fcm_token": 5, "platform": "ios"},
    ],
)
async def test_register_device_rejects_bad_bodies(client, user, body):
    r = await client.post("/devices", json=body)
    assert r.status_code == 422
    assert set(r.json()) == {"message"}


async def test_unregister_device_always_returns_an_empty_object(client, user, db_committed):
    await client.post("/devices", json={"fcm_token": "a:b-c_d", "platform": "android"})
    r = await client.delete("/devices/a%3Ab-c_d")
    assert r.status_code == 200
    assert r.json() == {}
    assert await count(db_committed, m.Device) == 0
    r = await client.delete("/devices/never-registered")
    assert r.status_code == 200
    assert r.json() == {}


async def test_devices_survive_a_user_reseed(client, user, db_committed):
    await client.post("/devices", json={"fcm_token": "keep-me", "platform": "android"})
    await db_committed.delete(user)
    await db_committed.commit()
    assert await count(db_committed, m.Device) == 1


# ── chat history ─────────────────────────────────────────────────────────────────────────


async def test_history_is_the_last_n_oldest_first(make_app, user, db_committed):
    for i in range(4):
        await messages.save_user(db_committed, user.id, f"q{i}", InputMode.TEXT)
        await messages.save_assistant(db_committed, user.id, text=f"a{i}")
    await db_committed.commit()
    application = make_app(APP_API_HISTORY_LIMIT=3)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        body = (await c.get("/assistant/messages")).json()
    assert [(x["text"], x["sender"]) for x in body["messages"]] == [
        ("a2", "assistant"),
        ("q3", "user"),
        ("a3", "assistant"),
    ]
    assert all(
        type(x["id"]) is int and x["id"] > 0 and x["created_at"].endswith("Z")
        for x in body["messages"]
    )


async def test_empty_history(client, user):
    assert (await client.get("/assistant/messages")).json() == {"messages": []}


# ── POST /assistant/messages (SSE) ───────────────────────────────────────────────────────


async def test_chat_streams_message_deltas_done(client, user, runner, db_committed):
    r = await client.post(
        "/assistant/messages",
        json={"text": "  What's my balance?  "},
        headers={"Accept": "text/event-stream"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-cache"
    events = parse_sse(r.text)
    assert names(events)[0] == "message"
    assert names(events)[-1] == "done"
    assert set(names(events)[1:-1]) == {"delta"}
    stored_user, reply = events[0][1], events[-1][1]
    assert stored_user["text"] == "What's my balance?"
    assert stored_user["sender"] == "user"
    assert reply["sender"] == "assistant"
    assert reply["text"] == runner.reply
    assert "".join(d["text"] for e, d in events if e == "delta") == reply["text"]
    assert stored_user["id"] > 0
    assert reply["id"] > stored_user["id"]
    for line in r.text.splitlines():  # every frame names its event; data is one line
        assert line == "" or line.startswith(("event: ", "data: ", ":"))
    await settle()
    assert runner.calls == [(user.id, runner.calls[0][1], "What's my balance?")]
    run = await db_committed.get(m.AgentRun, runner.calls[0][1], populate_existing=True)
    assert run.status == "completed"
    history = (await client.get("/assistant/messages")).json()["messages"]
    assert [x["id"] for x in history] == [stored_user["id"], reply["id"]]


async def test_agent_failure_streams_the_fallback_reply(client, user, runner, db_committed):
    runner.error = RuntimeError("LLM down")
    events = parse_sse((await client.post("/assistant/messages", json={"text": "hei"})).text)
    assert names(events)[-1] == "done"
    assert events[-1][1]["text"] == ports.fallback_reply("ro")
    await settle()
    run = await db_committed.scalar(select(m.AgentRun).execution_options(populate_existing=True))
    assert run.status == "failed"
    assert "LLM down" in run.error
    # the lock is free again
    assert (
        names(parse_sse((await client.post("/assistant/messages", json={"text": "again"})).text))[
            -1
        ]
        == "done"
    )


async def test_a_reply_that_cannot_be_stored_ends_with_error(client, user, monkeypatch):
    async def broken(*_: Any, **__: Any) -> Any:
        raise RuntimeError("db down")

    monkeypatch.setattr(messages, "save_assistant", broken)
    events = parse_sse((await client.post("/assistant/messages", json={"text": "hei"})).text)
    assert names(events) == ["message", "error"]
    assert events[-1][1] == {"message": chat.FAILED_REPLY}
    await settle()


async def test_timeout_sends_error_and_the_run_still_finishes(
    make_app, user, runner, db_committed, monkeypatch
):
    monkeypatch.setattr(chat, "KEEP_ALIVE_S", 0.02)
    monkeypatch.setattr(chat, "DELTA_PAUSE_S", 0.0)
    runner.gate = asyncio.Event()
    application = make_app(APP_API_REPLY_TIMEOUT_S=0.1)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        r = await c.post("/assistant/messages", json={"text": "slow"})
        assert ": keep-alive" in r.text
        events = parse_sse(r.text)
        assert names(events) == ["message", "error"]
        assert events[1][1] == {"message": chat.TIMED_OUT}
        busy = await c.post("/assistant/messages", json={"text": "meanwhile"})
        assert busy.status_code == 409
        assert set(busy.json()) == {"message"}
        runner.gate.set()
        await settle()
        history = (await c.get("/assistant/messages")).json()["messages"]
        assert [x["sender"] for x in history] == ["user", "assistant"]
        assert (
            names(parse_sse((await c.post("/assistant/messages", json={"text": "now"})).text))[-1]
            == "done"
        )


async def test_a_running_agent_run_is_409(client, user, db_committed):
    db_committed.add(m.AgentRun(user_id=user.id, trigger="chat", model="x", status="running"))
    await db_committed.commit()
    r = await client.post("/assistant/messages", json={"text": "hei"})
    assert r.status_code == 409
    assert r.json() == {"message": "The assistant is still answering your previous message."}


async def test_rate_limit_is_429_with_retry_after(make_app, user, monkeypatch):
    monkeypatch.setattr(chat, "DELTA_PAUSE_S", 0.0)
    application = make_app(RATE_LIMIT_CHAT_PER_MINUTE=2)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as c:
        for _ in range(2):
            assert (await c.post("/assistant/messages", json={"text": "hi"})).status_code == 200
            await settle()
        r = await c.post("/assistant/messages", json={"text": "hi"})
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1
    assert r.json() == {
        "message": f"Too many requests. Try again in {r.headers['retry-after']} seconds."
    }


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"text": ""}, "Write a message first."),
        ({"text": "   "}, "Write a message first."),
        ({"text": "x" * 2001}, "Your message is too long (at most 2000 characters)."),
        ({"text": 5}, None),
        ({}, None),
    ],
)
async def test_bad_chat_bodies_are_422_message(client, user, body, message):
    r = await client.post("/assistant/messages", json=body)
    assert r.status_code == 422
    assert set(r.json()) == {"message"}
    if message:
        assert r.json()["message"] == message


async def test_non_json_and_huge_bodies(client, user):
    r = await client.post(
        "/assistant/messages", content=b"not json", headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 422
    assert set(r.json()) == {"message"}
    r = await client.post(
        "/assistant/messages", content=b"x" * 20_000, headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 413
    assert r.json() == {"message": "The request is too large."}


async def test_text_at_the_limit_is_accepted(client, user):
    r = await client.post("/assistant/messages", json={"text": "y" * 2000})
    assert r.status_code == 200
    await settle()


async def test_closing_the_stream_early_still_stores_the_reply(user, runner, db_committed):
    from app.security.ratelimit import ConcurrencyGuard

    runner.gate = asyncio.Event()
    guard = ConcurrencyGuard()
    assert guard.claim(user.id)
    stored = await messages.save_user(db_committed, user.id, "hei", InputMode.TEXT)
    run = m.AgentRun(user_id=user.id, trigger="chat", model="x", status="running")
    db_committed.add(run)
    await db_committed.commit()
    task = chat.start_reply(user.id, run.id, "hei", runner, release=lambda: guard.release(user.id))
    stream = chat.stream_reply(stored, task, timeout_s=5)
    assert isinstance(stream, AsyncGenerator)
    assert (await anext(stream)).startswith(b"event: message\n")
    await stream.aclose()  # the client went away
    runner.gate.set()
    reply = await asyncio.wait_for(task, 5)
    assert reply.content == runner.reply
    assert not guard.held(user.id)


# ── CORS ─────────────────────────────────────────────────────────────────────────────────


async def test_cors_allows_localhost_only(client, user):
    ok = await client.options(
        "/balance",
        headers={"Origin": "http://localhost:5000", "Access-Control-Request-Method": "GET"},
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5000"
    bad = await client.options(
        "/balance",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in bad.headers
