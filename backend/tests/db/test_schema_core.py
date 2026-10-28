"""B2 step 1: core tables (arch 4.1, 4.2, 6.7 plan_preferences)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.clock import BUCHAREST
from app.db import models as m
from tests import factories as f


async def rejected(db, row) -> None:
    """The row violates a constraint; the test session stays usable afterwards."""
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(row)
            await db.flush()


async def accepted(db, row):
    async with db.begin_nested():
        db.add(row)
        await db.flush()
    return row


async def test_user_defaults(db, fixed_clock):
    u = await f.user(db)
    await db.refresh(u)
    assert u.language == "ro"
    assert u.coach_style == "warm"
    assert u.timezone == "Europe/Bucharest"
    assert u.household_scale == Decimal("1.00")
    assert u.onboarded_at is None
    assert u.created_at == fixed_clock.now()  # times come from app.clock, not the DB


async def test_user_created_at_keeps_the_instant(db):
    u = await f.user(db)
    await db.refresh(u)
    assert u.created_at.astimezone(BUCHAREST).date() == date(2026, 6, 15)


@pytest.mark.parametrize(("field", "value"), [("language", "fr"), ("coach_style", "strict")])
async def test_user_unknown_enum_value_rejected(db, field, value):
    await rejected(db, m.User(name="x", keycloak_sub="sub-x", **{field: value}))


async def test_user_keycloak_sub_is_unique(db):
    await f.user(db, keycloak_sub="same-sub")
    await rejected(db, m.User(name="Other", keycloak_sub="same-sub"))


async def test_account_is_one_row_per_user(db):
    u = await f.user(db)
    await accepted(db, m.Account(user_id=u.id, current_balance=Decimal("100.00")))
    await rejected(db, m.Account(user_id=u.id, current_balance=Decimal("1.00")))


async def test_second_active_goal_rejected(db):
    u = await f.user(db)
    await f.goal(db, u.id)
    await rejected(db, m.Goal(user_id=u.id, amount=Decimal("500"), deadline=date(2027, 1, 1)))


async def test_completed_and_active_goal_coexist(db):
    u = await f.user(db)
    await f.goal(db, u.id, status="completed")
    await f.goal(db, u.id, status="completed")
    active = await f.goal(db, u.id)
    assert active.status == "active"


async def test_active_goals_of_different_users_coexist(db):
    a, b = await f.user(db), await f.user(db)
    await f.goal(db, a.id)
    await f.goal(db, b.id)


@pytest.mark.parametrize("amount", ["0", "-5"])
async def test_goal_amount_must_be_positive(db, amount):
    u = await f.user(db)
    await rejected(db, m.Goal(user_id=u.id, amount=Decimal(amount), deadline=date(2027, 1, 1)))


@pytest.mark.parametrize(("day", "ok"), [(0, False), (1, True), (31, True), (32, False)])
async def test_income_and_fixed_cost_day_of_month_bounds(db, day, ok):
    u = await f.user(db)
    rows = [
        m.IncomeSource(user_id=u.id, source="Salariu", amount=Decimal("7000"), day_of_month=day),
        m.FixedCost(user_id=u.id, name="Chirie", amount=Decimal("2000"), day_of_month=day),
    ]
    for row in rows:
        await (accepted(db, row) if ok else rejected(db, row))


async def test_life_event_defaults_to_planned_and_checks_type_and_status(db):
    u = await f.user(db)
    ev = await accepted(
        db,
        m.LifeEvent(
            user_id=u.id,
            name="Vacanță",
            date=date(2026, 8, 15),
            est_cost=Decimal("3000"),
            type="trip",
        ),
    )
    assert ev.status == "planned"
    await rejected(
        db,
        m.LifeEvent(
            user_id=u.id, name="x", date=date(2026, 8, 1), est_cost=Decimal("1"), type="party"
        ),
    )
    await rejected(
        db,
        m.LifeEvent(
            user_id=u.id,
            name="x",
            date=date(2026, 8, 1),
            est_cost=Decimal("1"),
            type="trip",
            status="maybe",
        ),
    )


async def test_life_profile_stores_jsonb(db):
    u = await f.user(db)
    data = {"what_works": ["gătit acasă"], "motivation_trend": [4, 4, 3, 5]}
    await accepted(db, m.LifeProfile(user_id=u.id, data=data))
    stored = await db.scalar(select(m.LifeProfile.data).where(m.LifeProfile.user_id == u.id))
    assert stored == data


@pytest.mark.parametrize(
    ("pct", "ok"), [("0", True), ("0.30", True), ("0.31", False), ("-0.01", False)]
)
async def test_plan_preferences_buffer_pct_range(db, pct, ok):
    u = await f.user(db)
    row = m.PlanPreferences(user_id=u.id, buffer_pct=Decimal(pct))
    await (accepted(db, row) if ok else rejected(db, row))


async def test_plan_preferences_default_buffer_is_ten_percent(db):
    u = await f.user(db)
    p = await accepted(db, m.PlanPreferences(user_id=u.id))
    await db.refresh(p)
    assert p.buffer_pct == Decimal("0.10")


async def test_product_checks_kind_liquidity_and_months(db):
    ok = m.Product(
        id="pusculita",
        name="Pușculiță flexibilă",
        kind="flexible_pot",
        rate=Decimal("0.0350"),
        liquidity="instant",
        min_months=0,
        max_months=12,
    )
    await accepted(db, ok)
    await rejected(
        db, m.Product(id="p2", name="x", kind="crypto", rate=Decimal("0.01"), liquidity="instant")
    )
    await rejected(
        db,
        m.Product(
            id="p3", name="x", kind="term_deposit", rate=Decimal("0.01"), liquidity="whenever"
        ),
    )
    await rejected(
        db,
        m.Product(
            id="p4",
            name="x",
            kind="term_deposit",
            rate=Decimal("0.01"),
            liquidity="locked",
            min_months=12,
            max_months=6,
        ),
    )


async def test_sim_clock_has_a_single_row(db):
    await accepted(db, m.SimClock(id=1, today=date(2026, 6, 15)))
    await rejected(db, m.SimClock(id=2, today=date(2026, 6, 16)))
