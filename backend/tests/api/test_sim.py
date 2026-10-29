"""B10: the simulator (committed data: the sim runs the pipeline and jobs in their own sessions)."""

from datetime import date

import httpx
import pytest
from sqlalchemy import select

from app import clock
from app.config import Settings
from app.db import models as m
from app.db.seed import counts, realm_subs, seed_all
from app.db.session import unit_of_work
from app.main import create_app
from app.pipeline import day_jobs
from app.sim.clock_store import SimClock

MATEI = realm_subs()["matei"]


@pytest.fixture
async def seeded(db_committed):
    ids = await seed_all(db_committed, reset_first=True)
    await db_committed.commit()
    clock.set_clock(SimClock(date(2026, 6, 15)))
    return ids


async def test_sim_clock_load_set_advance(db):
    sim = SimClock(date(2026, 1, 1))
    assert await sim.load(db, date(2026, 6, 15)) == date(2026, 6, 15)  # no row → default
    await sim.set(db, date(2026, 6, 15))
    assert await sim.advance(db, 1) == date(2026, 6, 16) == sim.today()
    assert sim.now().date() == date(2026, 6, 16)
    assert await db.scalar(select(m.SimClock.today)) == date(2026, 6, 16)


async def test_sim_routes_are_gone_when_sim_mode_is_off(make_token, test_jwks):
    app = create_app(Settings(_env_file=None, SIM_MODE=False, SIM_CLOCK_FROM_DB=False))
    assert not [p for p in app.openapi()["paths"] if p.startswith("/api/sim")]
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api") as c:
        r = await c.post("/sim/reset", headers={"Authorization": f"Bearer {make_token()}"})
    assert r.status_code == 404


async def test_scenario_transaction_is_resolved_for_the_persona(
    as_committed_user, seeded, db_committed
):
    r = await as_committed_user(MATEI).post(
        "/sim/transaction", json={"scenario_id": "matei_mega_500"}
    )
    assert r.status_code == 200
    tx = await db_committed.get(m.Transaction, r.json()["transaction_id"], populate_existing=True)
    assert (tx.user_id, tx.status, tx.amount) == (seeded["matei"], "resolved", 500)
    assert tx.occurred_at.astimezone(clock.BUCHAREST).isoformat().startswith("2026-06-15T13:05")
    q = await db_committed.scalar(
        select(m.AgentEvent).where(m.AgentEvent.ref_transaction_id == tx.id)
    )
    assert q is not None and q.type == "transaction_question"


async def test_scenario_for_another_persona_and_raw_transactions(
    as_committed_user, seeded, db_committed
):
    r = await as_committed_user(MATEI).post("/sim/transaction", json={"scenario_id": "andrei_tv"})
    tx = await db_committed.get(m.Transaction, r.json()["transaction_id"])
    assert tx.user_id == seeded["andrei"] and tx.items[0]["name"] == 'Televizor 65"'
    raw = await as_committed_user(MATEI).post(
        "/sim/transaction",
        json={"merchant_raw": "LIBRARIA CARTURESTI", "amount": 45, "category": "books"},
    )
    assert (await db_committed.get(m.Transaction, raw.json()["transaction_id"])).user_id == (
        seeded["matei"]
    )


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"scenario_id": "nope"}, 404, "scenario_not_found"),
        ({"scenario_id": "../etc/passwd"}, 404, "scenario_not_found"),
        ({"merchant_raw": "", "amount": 5}, 422, "invalid_transaction"),
        ({"merchant_raw": "X", "amount": 5, "persona": "nobody"}, 404, "persona_not_found"),
    ],
)
async def test_sim_transaction_errors(as_committed_user, seeded, body, status, code):
    r = await as_committed_user(MATEI).post("/sim/transaction", json=body)
    assert r.status_code == status and r.json()["error"]["code"] == code


async def test_personas(as_committed_user, seeded):
    r = await as_committed_user(MATEI).get("/sim/personas")
    assert [p["id"] for p in r.json()["personas"]] == ["matei", "andrei", "bianca", "ioana", "alex"]


async def test_next_day_runs_the_jobs_in_order_and_advances_one_day(
    as_committed_user, seeded, monkeypatch
):
    calls = []
    real = day_jobs.run

    async def spy(job, user_id, day):
        calls.append((job, day))
        await real(job, user_id, day)

    monkeypatch.setattr(day_jobs, "run", spy)
    r = await as_committed_user(MATEI).post("/sim/next-day")
    body = r.json()
    assert r.status_code == 200 and body["date"] == "2026-06-16"
    assert body["ledger"]["date"] == "2026-06-15" and body["plan"] is not None
    jobs_on_15 = list(dict.fromkeys(j for j, d in calls if d == date(2026, 6, 15)))
    assert jobs_on_15 == day_jobs.day_sequence(date(2026, 6, 15))
    assert {j for j, d in calls if d == date(2026, 6, 16)} == {day_jobs.Job.PREEMPTIVE}


async def test_jump_crossing_a_monday_snapshots_once(
    as_committed_user, seeded, monkeypatch, db_committed
):
    async with unit_of_work() as db:
        await clock.get_clock().set(db, date(2026, 6, 18))  # Thursday
    snapshots = []
    real = day_jobs.run_for_all

    async def spy(job, day):
        if job == day_jobs.Job.FORECAST_SNAPSHOT:
            snapshots.append(day)
        return await real(job, day)

    monkeypatch.setattr(day_jobs, "run_for_all", spy)
    r = await as_committed_user(MATEI).post("/sim/jump", json={"days": 5})
    assert r.json()["date"] == "2026-06-23" and snapshots == [date(2026, 6, 22)]


async def test_reset_twice_gives_the_same_state(as_committed_user, seeded, db_committed):
    client = as_committed_user(MATEI)
    await client.post("/sim/transaction", json={"scenario_id": "matei_mega_500"})
    await client.post("/sim/next-day")
    assert (await client.post("/sim/reset")).status_code == 204
    first = await counts(db_committed)
    assert (await client.post("/sim/reset")).status_code == 204
    assert await counts(db_committed) == first
    assert clock.today() == date(2026, 6, 15)
    assert await db_committed.scalar(select(m.SimClock.today)) == date(2026, 6, 15)


async def test_jump_rejects_bad_days(as_committed_user, seeded):
    assert (await as_committed_user(MATEI).post("/sim/jump", json={"days": 0})).status_code == 422
