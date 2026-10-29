"""B6b: receivables, forecast, pots, products, life facts, life profile."""

from datetime import date
from decimal import Decimal

import pytest

from app.db import models as m
from app.domain.enums import Category
from app.domain.results import Driver, Forecast
from app.pipeline import ports
from app.services import forecasts, goals, notifications, plans, receivables, users
from tests import builders as b
from tests import factories as f

D = Decimal


async def receivable(db, user_id):
    return await receivables.create(
        db,
        user_id,
        amount=D("400"),
        debtor_label="colegi",
        expected_by=date(2026, 6, 29),
        people_count=5,
        amount_each=D("100"),
    )


@pytest.mark.parametrize(
    ("lang", "body"), [("ro", "Cerere trimisă: 4 × 100 lei"), ("en", "Request sent: 4 × 100 lei")]
)
async def test_request_payment(as_user, db, lang, body):
    u = await f.user(db, language=lang)
    r = await receivable(db, u.id)
    resp = await as_user(u).post(f"/receivables/{r.id}/request-payment")
    assert resp.status_code == 200 and resp.json()["status"] == "requested"
    assert [n.body for n in await notifications.list_all(db, u.id)] == [body]
    again = await as_user(u).post(f"/receivables/{r.id}/request-payment")
    assert again.status_code == 409 and again.json()["error"]["code"] == "invalid_transition"


async def test_mark_paid_replans_and_cancel(as_user, db):
    u = await f.user(db)
    await goals.create(db, u.id, amount=D("100"), deadline=date(2026, 12, 31))
    r1, r2 = await receivable(db, u.id), await receivable(db, u.id)
    assert (await as_user(u).post(f"/receivables/{r1.id}/mark-paid")).json()["status"] == "paid"
    assert (await plans.latest(db, u.id)).reason == "receivable paid"
    assert (await as_user(u).post(f"/receivables/{r2.id}/cancel")).json()["status"] == "cancelled"
    listed = (await as_user(u).get("/receivables", params={"status": "paid"})).json()
    assert [x["id"] for x in listed["receivables"]] == [r1.id]


async def test_receivables_isolation(as_user, db):
    u, other = await f.user(db), await f.user(db)
    r = await receivable(db, other.id)
    for action in ("request-payment", "mark-paid", "cancel"):
        assert (await as_user(u).post(f"/receivables/{r.id}/{action}")).status_code == 404


async def test_forecast_pots_products(as_user, db):
    u = await f.user(db)
    assert (await as_user(u).get("/forecast")).status_code == 404
    g = await goals.create(db, u.id, amount=D("10000"), deadline=date(2026, 12, 31))
    await forecasts.save(
        db,
        u.id,
        Forecast(
            probability=0.72,
            p10=D("1"),
            p50=D("2"),
            p90=D("3"),
            plan_version=1,
            sim_date=date(2026, 6, 8),
            is_weekly_snapshot=True,
        ),
        goal_id=g.id,
    )
    await forecasts.save(
        db,
        u.id,
        Forecast(
            probability=0.78,
            p10=D("8650"),
            p50=D("10900"),
            p90=D("12400"),
            plan_version=1,
            sim_date=date(2026, 6, 15),
            drivers=(Driver(category=Category.FOOD_DELIVERY, pp_per_100_lei=2.1),),
        ),
        goal_id=g.id,
    )
    body = (await as_user(u).get("/forecast")).json()
    assert (body["probability"], body["last_week_probability"], body["p50"]) == (
        0.78,
        0.72,
        10900.0,
    )
    assert body["drivers"] == [
        {"category": "food_delivery", "category_label": "Livrări mâncare", "pp_per_100_lei": 2.1}
    ]
    assert body["history"] == [{"date": "2026-06-08", "probability": 0.72}]
    pots_body = (await as_user(u).get("/pots")).json()["pots"]
    assert [p["kind"] for p in pots_body] == ["goal"]
    db.add(
        m.Product(
            id="pusculita",
            name="Pușculiță flexibilă",
            kind="flexible_pot",
            rate=D("0.035"),
            liquidity="instant",
        )
    )
    await db.flush()
    assert (await as_user(u).get("/products")).json()["products"][0]["rate"] == 0.035


async def test_life_fact_create_validates_and_propagates(as_user, db, monkeypatch):
    u = await f.user(db)
    calls = []

    async def spy(db_, user_id, fact_id):
        calls.append(fact_id)

    monkeypatch.setattr(ports, "on_fact_changed", spy)
    monkeypatch.setattr(
        ports,
        "signatures_for_fact",
        lambda fact, llm: [b.signature(fact_id=None, item_keywords=("televizor",))],
    )
    bad = await as_user(u).post("/life-facts", json={"type": "occupation", "value": {}})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_fact"
    r = await as_user(u).post(
        "/life-facts",
        json={
            "type": "occupation",
            "value": {"title": "analist sportiv"},
            "text": "Sunt analist sportiv",
        },
    )
    fact = r.json()
    assert r.status_code == 201 and fact["source"] == "user_edit" and calls == [fact["id"]]
    assert fact["explains"] == ["Electronice → Echipament de lucru"]
    assert (await as_user(u).delete(f"/life-facts/{fact['id']}")).status_code == 204
    assert (await as_user(u).get("/life-facts")).json() == {"facts": []}


async def test_hypothesis_confirm_and_reject(as_user, db):
    u = await f.user(db)
    rows = [
        m.LifeFact(
            user_id=u.id,
            type="vehicle",
            value={"kind": "car"},
            source="inferred",
            status="hypothesis",
            confidence=D("0.5"),
        )
        for _ in range(2)
    ]
    db.add_all(rows)
    await db.flush()
    assert (await as_user(u).post(f"/life-facts/{rows[0].id}/confirm")).json()["status"] == (
        "confirmed"
    )
    assert (await as_user(u).post(f"/life-facts/{rows[1].id}/reject")).json()["status"] == (
        "rejected"
    )
    hyps = (await as_user(u).get("/life-facts", params={"status": "hypothesis"})).json()
    assert hyps == {"facts": []}


async def test_life_facts_isolation(as_user, db):
    u, other = await f.user(db), await f.user(db)
    row = m.LifeFact(user_id=other.id, type="pet", value={"kind": "pisică"}, source="seed")
    db.add(row)
    await db.flush()
    assert (await as_user(u).patch(f"/life-facts/{row.id}", json={"text": "x"})).status_code == 404
    assert (await as_user(u).delete(f"/life-facts/{row.id}")).status_code == 404


async def test_life_profile_soft_notes_only(as_user, db):
    u = await f.user(db)
    await users.set_onboarded(db, u.id)
    r = await as_user(u).patch("/life-profile/what_works", json={"value": ["gătit acasă"]})
    assert r.json() == {"what_works": ["gătit acasă"]}
    bad = await as_user(u).patch("/life-profile/job", json={"value": "developer"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "not_a_soft_note"
    body = (await as_user(u).get("/life-profile")).json()
    assert body["life_profile"] == {"what_works": ["gătit acasă"]} and body["goal"] is None
    assert (await as_user(u).delete("/life-profile/what_works")).status_code == 204
