"""Security review P0-3 / P1-1: one chat run at a time (no race), and the chat / sim rate limits."""

import asyncio

import pytest

from app.config import Settings
from app.domain.results import AgentResult
from app.pipeline import ports
from app.security import ratelimit
from app.services import agent_runs
from tests import factories as f

SIM = ("sim",)


@pytest.fixture
async def user(db_committed):
    u = await f.user(db_committed)
    await db_committed.commit()
    return u


@pytest.fixture(autouse=True)
def echo_agent(monkeypatch):
    async def _echo(user_id, trigger, text, input_mode="text", **_):
        return AgentResult(text=f"Am primit: {text}")

    monkeypatch.setattr(ports, "run_agent", _echo)


def limits(**kw) -> None:
    ratelimit.configure(Settings(_env_file=None, **kw))


async def test_two_concurrent_chats_one_is_409(as_committed_user, user, monkeypatch):
    real = agent_runs.is_running

    async def slow_is_running(db, user_id):
        await asyncio.sleep(0.05)  # the await the old check-then-add raced through
        return await real(db, user_id)

    monkeypatch.setattr(agent_runs, "is_running", slow_is_running)
    client = as_committed_user(user)
    first, second = await asyncio.gather(
        client.post("/chat", json={"text": "unu"}), client.post("/chat", json={"text": "doi"})
    )
    assert sorted([first.status_code, second.status_code]) == [202, 409]
    loser = first if first.status_code == 409 else second
    assert loser.json()["error"]["code"] == "agent_busy"


async def test_after_a_run_the_next_chat_is_accepted(as_committed_user, user):
    client = as_committed_user(user)
    assert (await client.post("/chat", json={"text": "unu"})).status_code == 202
    assert (await client.post("/chat", json={"text": "doi"})).status_code == 202


async def test_chat_over_the_rate_limit_is_429_with_retry_after(as_committed_user, user):
    limits(RATE_LIMIT_CHAT_PER_MINUTE=1)
    client = as_committed_user(user)
    assert (await client.post("/chat", json={"text": "unu"})).status_code == 202
    r = await client.post("/chat", json={"text": "doi"})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1


async def test_sim_over_the_rate_limit_is_429(as_user, db):
    limits(RATE_LIMIT_SIM_PER_MINUTE=1)
    u = await f.user(db)
    client = as_user(u, roles=SIM)
    assert (await client.get("/sim/personas")).status_code == 200
    r = await client.get("/sim/personas")
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"


async def test_a_refused_sim_call_costs_no_token(as_user, db):
    limits(RATE_LIMIT_SIM_PER_MINUTE=1)
    u = await f.user(db)
    assert (await as_user(u).get("/sim/personas")).status_code == 403  # no role
    assert (await as_user(u, roles=SIM).get("/sim/personas")).status_code == 200
