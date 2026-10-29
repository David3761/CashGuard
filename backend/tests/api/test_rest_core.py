"""B6a: REST core endpoints + the route-table guard."""

import re
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app import clock
from app.clock import BUCHAREST, FixedClock
from app.db import models as m
from app.domain.enums import InputMode
from app.domain.results import PlanResult
from app.main import create_app
from app.services import (
    agent_events,
    goals,
    messages,
    notifications,
    plans,
    transfers,
    users,
)
from tests import factories as f

D = Decimal
STATE_KEYS = {
    "date",
    "account",
    "onboarding",
    "goal",
    "plan",
    "upcoming_events",
    "streak_days",
    "unread_notifications",
    "forecast",
    "pots",
    "receivables",
    "pending_question",
    "last_plan_change",
}


async def onboarded_user(db):
    u = await f.user(db)
    db.add(m.Account(user_id=u.id, current_balance=D("2850"), savings_pot=D("5200")))
    await goals.create(
        db, u.id, amount=D("10000"), deadline=date(2026, 12, 31), motivation="Fond 10.000"
    )
    await users.set_onboarded(db, u.id)
    await db.flush()
    return u


# ── /me ──────────────────────────────────────────────────────────────────────────────────


async def test_me_get_and_patch(as_user, db):
    u = await f.user(db, name="Matei")
    r = await as_user(u).get("/me")
    assert r.json() == {
        "user_id": u.id,
        "name": "Matei",
        "language": "ro",
        "coach_style": "warm",
        "onboarded": False,
    }
    r = await as_user(u).patch("/me", json={"language": "en", "coach_style": "direct"})
    assert r.status_code == 200 and r.json()["language"] == "en"
    r = await as_user(u).patch("/me", json={"language": "fr"})
    assert r.status_code == 422


# ── /state ───────────────────────────────────────────────────────────────────────────────


async def test_state_before_onboarding_has_null_goal_plan_forecast(as_user, db):
    u = await f.user(db)
    r = await as_user(u).get("/state")
    body = r.json()
    assert r.status_code == 200 and set(body) == STATE_KEYS
    assert (body["goal"], body["plan"], body["forecast"], body["pending_question"]) == (
        None,
        None,
        None,
        None,
    )
    assert body["date"] == "2026-06-15" and body["onboarding"]["done"] is False


async def test_state_after_onboarding(as_user, db):
    u = await onboarded_user(db)
    await plans.save(
        db,
        u.id,
        PlanResult(today_budget=D("31.20"), feasible=True),
        reason="Mega Image: 100 lei ai tăi",
    )
    pot = await db.scalar(m.Pot.__table__.select().where(m.Pot.user_id == u.id))
    await db.execute(m.Pot.__table__.update().where(m.Pot.id == pot).values(saved=D("5200")))
    tx = await f.transaction(db, u.id, decision="ask", status="resolved")
    ev = await agent_events.create(
        db,
        u.id,
        type="transaction_question",
        event_date=date(2026, 6, 15),
        ref_transaction_id=tx.id,
    )
    await agent_events.mark_asked(db, u.id, ev.id)
    msg = await messages.save_assistant(db, u.id, text="Ce a fost?", agent_event_id=ev.id)
    db.add(
        m.Receivable(
            user_id=u.id, amount=D("400"), debtor_label="colegi", expected_by=date(2026, 6, 29)
        )
    )
    await db.flush()
    body = (await as_user(u).get("/state")).json()
    assert body["goal"]["progress_pct"] == 52.0 and body["goal"]["days_left"] == 199
    assert body["plan"]["today_budget"] == 31.2 and body["plan"]["spent_today"] == 0
    assert body["account"] == {"current_balance": 2850.0, "savings_pot": 5200.0}
    assert body["pending_question"] == {
        "agent_event_id": ev.id,
        "transaction_id": tx.id,
        "message_id": msg.id,
    }
    assert body["receivables"]["open_total"] == 400.0
    assert body["last_plan_change"] == "Mega Image: 100 lei ai tăi"
    assert body["onboarding"]["goal"] is True


async def test_streak_counts_closed_days_on_plan(as_user, db):
    u = await f.user(db)
    for back, status in ((1, "ok"), (2, "under"), (3, "overspent"), (4, "ok")):
        db.add(
            m.DayLedger(user_id=u.id, date=date(2026, 6, 15) - timedelta(days=back), status=status)
        )
    await db.flush()
    assert (await as_user(u).get("/state")).json()["streak_days"] == 2


# ── messages & notifications ─────────────────────────────────────────────────────────────


async def test_messages_since_limit_order_and_utc(as_user, db):
    u = await f.user(db)
    stamps = []
    for i in range(3):
        clock.set_clock(FixedClock(datetime(2026, 6, 15, 10, i, tzinfo=BUCHAREST)))
        stamps.append((await messages.save_user(db, u.id, f"m{i}", InputMode.TEXT)).created_at)
    r = await as_user(u).get("/messages", params={"since": stamps[0].isoformat(), "limit": 1})
    body = r.json()["messages"]
    assert [x["content"] for x in body] == ["m1"]
    assert body[0]["created_at"] == "2026-06-15T07:01:00Z"


async def test_notifications_unread_and_read(as_user, db):
    u, other = await f.user(db), await f.user(db)
    n = await notifications.create(db, u.id, type="x", title="t", body="b")
    await notifications.create(db, u.id, type="y", title="t", body="b")
    foreign = await notifications.create(db, other.id, type="z", title="t", body="b")
    client = as_user(u)
    assert (
        len(
            (await client.get("/notifications", params={"unread_only": True})).json()[
                "notifications"
            ]
        )
        == 2
    )
    assert (await client.post(f"/notifications/{n.id}/read")).status_code == 204
    assert (
        len(
            (await client.get("/notifications", params={"unread_only": True})).json()[
                "notifications"
            ]
        )
        == 1
    )
    assert (await client.get("/state")).json()["unread_notifications"] == 1
    r = await client.post(f"/notifications/{foreign.id}/read")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


# ── plan ─────────────────────────────────────────────────────────────────────────────────


async def test_plan_and_history(as_user, db):
    u = await f.user(db)
    assert (await as_user(u).get("/plan")).status_code == 404
    await plans.save(db, u.id, PlanResult(today_budget=D("31.20"), feasible=True), reason="a")
    await plans.save(db, u.id, PlanResult(today_budget=D("29.80"), feasible=True), reason="b")
    assert (await as_user(u).get("/plan")).json()["version"] == 2
    history = (await as_user(u).get("/plan/history")).json()["versions"]
    assert [v["version"] for v in history] == [2, 1] and history[0]["today_budget"] == 29.8
    assert history[0]["created_at"].endswith("Z")


# ── transactions ─────────────────────────────────────────────────────────────────────────


async def test_transactions_list_and_detail(as_user, db):
    u = await f.user(db)
    tx = await f.transaction(
        db,
        u.id,
        status="resolved",
        category="groceries",
        purpose="unknown",
        decision="ask",
        life_fit=D("0.1"),
        merchant="Mega Image",
    )
    listed = (await as_user(u).get("/transactions", params={"from": "2026-06-15"})).json()
    row = listed["transactions"][0]
    assert (row["merchant"], row["category_label"], row["amount"]) == (
        "Mega Image",
        "Cumpărături",
        500.0,
    )
    detail = (await as_user(u).get(f"/transactions/{tx.id}")).json()
    assert detail["scores"]["life_fit"] == 0.1 and detail["matched_fact"] is None


@pytest.mark.parametrize(
    ("body", "code"),
    [({"own_amount": 500.01}, "invalid_own_amount"), ({"people_count": 0}, "invalid_people_count")],
)
async def test_patch_transaction_rejects_bad_shares(as_user, db, body, code):
    u = await f.user(db)
    tx = await f.transaction(db, u.id, status="resolved")
    r = await as_user(u).patch(f"/transactions/{tx.id}", json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == code


async def test_patch_transaction_500_to_100_replans(as_user, db):
    u = await onboarded_user(db)
    tx = await f.transaction(db, u.id, status="resolved")
    r = await as_user(u).patch(f"/transactions/{tx.id}", json={"people_count": 5})
    body = r.json()
    assert r.status_code == 200
    assert (body["effective_amount"], body["purpose"], body["purpose_label"]) == (
        100.0,
        "on_behalf_of_others",
        "Pentru alții",
    )
    assert (await plans.latest(db, u.id)).reason == "user edit"


async def test_transactions_isolation(as_user, db):
    u, other = await f.user(db), await f.user(db)
    tx = await f.transaction(db, other.id)
    assert (await as_user(u).get(f"/transactions/{tx.id}")).status_code == 404
    assert (await as_user(u).patch(f"/transactions/{tx.id}", json={})).status_code == 404
    assert (await as_user(u).get("/transactions")).json() == {"transactions": []}


# ── transfers ────────────────────────────────────────────────────────────────────────────


async def test_transfer_undo_moves_the_money_back_once(as_user, db):
    u = await onboarded_user(db)
    pot = await db.scalar(m.Pot.__table__.select().where(m.Pot.user_id == u.id))
    await db.execute(m.Pot.__table__.update().where(m.Pot.id == pot).values(saved=D("760")))
    t = await transfers.create(db, u.id, amount=D("760"), kind="auto_save", pot_id=pot)
    r = await as_user(u).post(f"/transfers/{t.id}/undo")
    assert r.status_code == 200 and r.json()["undone_at"].endswith("Z")
    acc = await db.get(m.Account, u.id, populate_existing=True)
    assert acc.current_balance == D("3610.00") and acc.savings_pot == D("0.00")
    r = await as_user(u).post(f"/transfers/{t.id}/undo")
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_undone"


# ── every endpoint needs a token ─────────────────────────────────────────────────────────

PUBLIC = {"/api/health", "/api/openapi.json", "/api/docs", "/api/docs/oauth2-redirect"}


async def test_every_api_route_needs_a_token(client):
    # every HTTP endpoint in the OpenAPI schema (FastAPI nests routers lazily, so walk the schema)
    checked = 0
    for path, operations in create_app().openapi()["paths"].items():
        if path in PUBLIC:
            continue
        url = re.sub(r"\{[^}]+\}", "1", path.removeprefix("/api"))
        for method in operations:
            r = await client.request(method.upper(), url, json={})
            assert r.status_code == 401, f"{method.upper()} {path} → {r.status_code}"
            checked += 1
    assert checked >= 15
