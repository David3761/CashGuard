"""B12: the seed loader on the placeholder data."""

import json
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.db import models as m
from app.db.seed import DATA_DIR, counts, realm_subs, seed_all
from app.services import forecasts, pattern_rules, plans, signatures, users


def profile(pid):
    return json.loads((DATA_DIR / "personas" / pid / "profile.json").read_text())


async def test_every_persona_with_its_realm_login(db):
    seeded = await seed_all(db, reset_first=True)
    assert set(seeded) == {"matei", "andrei", "bianca", "ioana", "alex"}
    subs = realm_subs()
    for pid, uid in seeded.items():
        assert (await db.get(m.User, uid)).keycloak_sub == subs[pid]
    assert await db.scalar(select(m.SimClock.today)) == date(2026, 6, 15)


async def test_persona_contents(db):
    seeded = await seed_all(db, reset_first=True)
    matei, ioana, andrei = seeded["matei"], seeded["ioana"], seeded["andrei"]
    acc = await db.get(m.Account, matei)
    assert acc.current_balance == Decimal(str(profile("matei")["account"]["current_balance"]))
    assert acc.savings_pot == Decimal("5200.00")
    rule = (await pattern_rules.list_active(db, matei))[0]
    assert (rule.confidence, rule.hits, rule.outcome.label) == (0.7, 2, "Prânz cu echipa")
    n_tx = await db.scalar(select(func.count()).where(m.Transaction.user_id == matei))
    assert n_tx == len(json.loads((DATA_DIR / "personas/matei/transactions.json").read_text()))
    assert (await users.get(db, ioana)).household_scale == Decimal("2.10")
    tv = [s for s in await signatures.list_active(db, andrei) if "televizor" in s.item_keywords]
    assert tv and tv[0].purpose == "work_tool"
    for pid in ("matei", "andrei", "bianca", "ioana"):
        assert await plans.latest(db, seeded[pid]) is not None
        assert await forecasts.latest(db, seeded[pid]) is not None
    assert await plans.latest(db, seeded["alex"]) is None
    assert (await users.get(db, seeded["alex"])).onboarded_at is None
    # danutu's E13 calibration (tests/acceptance/test_demo_numbers.py): last week ≈ 71.5 %
    last_week = (await forecasts.latest(db, matei)).last_week_probability
    assert last_week is not None and abs(last_week - 0.715) < 0.02


async def test_seeding_twice_with_reset_gives_the_same_counts(db):
    await seed_all(db, reset_first=True)
    first = await counts(db)
    await seed_all(db, reset_first=True)
    assert await counts(db) == first
    assert first["merchants"] >= 10 and first["products"] == 3
