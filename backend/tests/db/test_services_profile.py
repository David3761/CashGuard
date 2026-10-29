"""B3 step 1: profile & plan-input services (users, accounts, goals, income, fixed costs, life
events, life profile, plan preferences, products, merchants)."""

from datetime import date
from decimal import Decimal

import pytest

from app.db import models as m
from app.domain.enums import CoachStyle, Language, LifeEventType
from app.errors import DomainError
from app.services import (
    accounts,
    fixed_costs,
    goals,
    income_sources,
    life_events,
    life_profile,
    merchants,
    plan_preferences,
    products,
    users,
)
from tests import factories as f

D = Decimal


async def fails(coro, code: str, status: int | None = None) -> DomainError:
    with pytest.raises(DomainError) as err:
        await coro
    assert err.value.code == code, err.value.message
    if status is not None:
        assert err.value.status == status
    return err.value


@pytest.fixture
async def two(db):
    """Two users: `a` acts, `b` owns rows `a` must never see."""
    return await f.user(db), await f.user(db)


# ── users ────────────────────────────────────────────────────────────────────────────────


async def test_user_create_get_and_by_sub(db):
    u = await users.create(db, keycloak_sub="sub-matei", name="Matei", age=26, city="București")
    assert (u.name, u.language, u.coach_style) == ("Matei", Language.RO, CoachStyle.WARM)
    assert await users.get(db, u.id) == u
    assert await users.get_by_sub(db, "sub-matei") == u
    assert await users.get_by_sub(db, "nobody") is None


async def test_user_duplicate_sub_is_a_conflict(db):
    await users.create(db, keycloak_sub="dup", name="A")
    await fails(users.create(db, keycloak_sub="dup", name="B"), "conflict", 409)


async def test_user_unknown_id_is_not_found(db):
    await fails(users.get(db, 999_999), "not_found", 404)


async def test_user_update_changes_only_given_fields(db):
    u = await users.create(db, keycloak_sub="s", name="Ana", city="Cluj-Napoca")
    u2 = await users.update(db, u.id, language=Language.EN, household_scale=D("2.1"))
    assert (u2.language, u2.household_scale, u2.city, u2.coach_style) == (
        Language.EN,
        D("2.10"),
        "Cluj-Napoca",
        CoachStyle.WARM,
    )


@pytest.mark.parametrize(
    ("kw", "code"),
    [
        ({"language": "fr"}, "invalid_language"),
        ({"coach_style": "strict"}, "invalid_coach_style"),
        ({"household_scale": D("0.9")}, "invalid_household_scale"),
    ],
)
async def test_user_update_rejects_bad_values(db, kw, code):
    u = await f.user(db)
    await fails(users.update(db, u.id, **kw), code, 422)


async def test_set_onboarded_is_idempotent(db, fixed_clock):
    u = await f.user(db)
    first = await users.set_onboarded(db, u.id)
    assert first.onboarded_at == fixed_clock.now()
    assert (await users.set_onboarded(db, u.id)).onboarded_at == first.onboarded_at


# ── accounts ─────────────────────────────────────────────────────────────────────────────


async def test_account_create_get_adjust(db):
    u = await f.user(db)
    await accounts.create(db, u.id, current_balance=D("100"))
    assert (await accounts.adjust_balance(db, u.id, D("-500.30"))).current_balance == D("-400.30")
    acc = await accounts.adjust_balance(db, u.id, D("7000"))
    assert acc.current_balance == D("6599.70") and acc.savings_pot == D("0")
    assert await accounts.get(db, u.id) == acc


async def test_account_isolation_and_missing(two, db):
    a, b = two
    await accounts.create(db, b.id, current_balance=D("1"))
    await fails(accounts.get(db, a.id), "not_found")
    await fails(accounts.adjust_balance(db, a.id, D("5")), "not_found")
    assert (await accounts.get(db, b.id)).current_balance == D("1.00")


async def test_account_created_twice_is_a_conflict(db):
    u = await f.user(db)
    await accounts.create(db, u.id, current_balance=D("1"))
    await fails(accounts.create(db, u.id, current_balance=D("2")), "conflict", 409)


# ── goals ────────────────────────────────────────────────────────────────────────────────


async def test_goal_lifecycle_with_its_pot(db):
    u = await f.user(db)
    assert await goals.get_active(db, u.id) is None
    g = await goals.create(
        db, u.id, amount=D("10000"), deadline=date(2026, 12, 31), motivation="Fond 10.000"
    )
    assert g.status == "active" and g.soft is True
    assert await goals.get_active(db, u.id) == g == await goals.get(db, u.id, g.id)
    pot = await db.scalar(m.Pot.__table__.select().where(m.Pot.goal_id == g.id))
    assert pot is not None
    g2 = await goals.update(db, u.id, g.id, amount=D("12000"), soft=False)
    assert (g2.amount, g2.soft, g2.deadline) == (D("12000.00"), False, date(2026, 12, 31))
    assert (await db.get(m.Pot, pot)).target == D("12000.00")  # the goal pot follows
    done = await goals.complete(db, u.id, g.id)
    assert done.status == "completed" and await goals.get_active(db, u.id) is None
    await fails(goals.complete(db, u.id, g.id), "invalid_transition", 409)
    await fails(goals.update(db, u.id, g.id, amount=D("1")), "invalid_transition", 409)


async def test_second_active_goal_is_refused(db):
    u = await f.user(db)
    await goals.create(db, u.id, amount=D("100"), deadline=date(2026, 12, 31))
    await fails(
        goals.create(db, u.id, amount=D("200"), deadline=date(2027, 1, 31)),
        "goal_already_active",
        409,
    )


@pytest.mark.parametrize(
    ("kw", "code"),
    [
        ({"amount": D("0"), "deadline": date(2026, 12, 31)}, "invalid_amount"),
        ({"amount": D("10"), "deadline": date(2026, 6, 14)}, "deadline_passed"),
    ],
)
async def test_goal_create_rejects_bad_values(db, kw, code):
    u = await f.user(db)
    await fails(goals.create(db, u.id, **kw), code, 422)


async def test_goal_deadline_today_is_allowed(db):
    u = await f.user(db)
    await goals.create(db, u.id, amount=D("10"), deadline=date(2026, 6, 15))


async def test_goal_isolation(two, db):
    a, b = two
    g = await goals.create(db, b.id, amount=D("100"), deadline=date(2026, 12, 31))
    await fails(goals.get(db, a.id, g.id), "not_found", 404)
    await fails(goals.update(db, a.id, g.id, amount=D("5")), "not_found")
    await fails(goals.complete(db, a.id, g.id), "not_found")
    assert await goals.get_active(db, a.id) is None


# ── income sources & fixed costs (same shape) ────────────────────────────────────────────


async def test_income_sources_crud(db):
    u = await f.user(db)
    late = await income_sources.create(db, u.id, source="Bacșiș", amount=D("300"), day_of_month=25)
    salary = await income_sources.create(
        db, u.id, source="Salariu", amount=D("7000"), day_of_month=10
    )
    assert [i.id for i in await income_sources.list_all(db, u.id)] == [salary.id, late.id]
    upd = await income_sources.update(db, u.id, salary.id, amount=D("7200"))
    assert (upd.amount, upd.source, upd.day_of_month) == (D("7200.00"), "Salariu", 10)
    await income_sources.delete(db, u.id, late.id)
    assert [i.id for i in await income_sources.list_all(db, u.id)] == [salary.id]


async def test_fixed_costs_crud(db):
    u = await f.user(db)
    rent = await fixed_costs.create(db, u.id, name="Chirie", amount=D("2000"), day_of_month=1)
    upd = await fixed_costs.update(db, u.id, rent.id, amount=D("2400"))  # "m-am mutat"
    assert upd.amount == D("2400.00")
    assert await fixed_costs.list_all(db, u.id) == [upd]
    await fixed_costs.delete(db, u.id, rent.id)
    assert await fixed_costs.list_all(db, u.id) == []


@pytest.mark.parametrize("service", [income_sources, fixed_costs])
@pytest.mark.parametrize(
    ("amount", "day", "code"),
    [
        (D("0"), 10, "invalid_amount"),
        (D("10"), 0, "invalid_day_of_month"),
        (D("10"), 32, "invalid_day_of_month"),
    ],
)
async def test_income_and_costs_reject_bad_values(db, service, amount, day, code):
    u = await f.user(db)
    label = {"source": "x"} if service is income_sources else {"name": "x"}
    await fails(service.create(db, u.id, amount=amount, day_of_month=day, **label), code, 422)


@pytest.mark.parametrize("service", [income_sources, fixed_costs])
async def test_income_and_costs_isolation(two, db, service):
    a, b = two
    label = {"source": "x"} if service is income_sources else {"name": "x"}
    row = await service.create(db, b.id, amount=D("10"), day_of_month=1, **label)
    await fails(service.update(db, a.id, row.id, amount=D("1")), "not_found", 404)
    await fails(service.delete(db, a.id, row.id), "not_found", 404)
    assert await service.list_all(db, a.id) == []


# ── life events ──────────────────────────────────────────────────────────────────────────


async def test_life_events_lifecycle(db):
    u = await f.user(db)
    trip = await life_events.create(
        db,
        u.id,
        name="Vacanță",
        date=date(2026, 8, 15),
        est_cost=D("3000"),
        type=LifeEventType.TRIP,
        source="chat",
    )
    gift = await life_events.create(
        db, u.id, name="Cadou", date=date(2026, 7, 1), est_cost=D("150"), type=LifeEventType.GIFT
    )
    assert [e.id for e in await life_events.list_planned(db, u.id)] == [gift.id, trip.id]
    moved = await life_events.update(db, u.id, trip.id, date=date(2026, 8, 20))
    assert moved.date == date(2026, 8, 20) and moved.name == "Vacanță"
    cancelled = await life_events.cancel(db, u.id, gift.id)
    assert cancelled.status == "cancelled"
    assert [e.id for e in await life_events.list_planned(db, u.id)] == [trip.id]
    await fails(life_events.cancel(db, u.id, gift.id), "invalid_transition", 409)
    await fails(life_events.update(db, u.id, gift.id, name="x"), "invalid_transition", 409)
    assert (await life_events.mark_done(db, u.id, trip.id)).status == "done"
    await fails(life_events.mark_done(db, u.id, trip.id), "invalid_transition")


async def test_life_event_rejects_negative_cost(db):
    u = await f.user(db)
    await fails(
        life_events.create(
            db, u.id, name="x", date=date(2026, 8, 1), est_cost=D("-1"), type=LifeEventType.OTHER
        ),
        "invalid_amount",
        422,
    )


async def test_life_events_isolation(two, db):
    a, b = two
    ev = await life_events.create(
        db, b.id, name="x", date=date(2026, 8, 1), est_cost=D("1"), type=LifeEventType.OTHER
    )
    for call in (
        life_events.get(db, a.id, ev.id),
        life_events.cancel(db, a.id, ev.id),
        life_events.update(db, a.id, ev.id, name="y"),
        life_events.mark_done(db, a.id, ev.id),
    ):
        await fails(call, "not_found")
    assert await life_events.list_planned(db, a.id) == []


# ── life profile (soft notes) ────────────────────────────────────────────────────────────


async def test_life_profile_keys(two, db):
    a, b = two
    assert await life_profile.get(db, a.id) == {}
    await life_profile.set_key(db, a.id, "what_works", ["gătit acasă"])
    notes = await life_profile.set_key(db, a.id, "what_doesnt", ["ton strict"])
    assert notes == {"what_works": ["gătit acasă"], "what_doesnt": ["ton strict"]}
    assert await life_profile.delete_key(db, a.id, "what_works") == {"what_doesnt": ["ton strict"]}
    await fails(life_profile.delete_key(db, a.id, "nope"), "not_found")
    assert await life_profile.get(db, b.id) == {}


# ── plan preferences ─────────────────────────────────────────────────────────────────────


async def test_plan_preferences_default_then_merge(db):
    u = await f.user(db)
    assert (await plan_preferences.get(db, u.id)).buffer_pct == D("0.10")
    p = await plan_preferences.update(
        db,
        u.id,
        weekday_weights={"Sat": 1.5, "Sun": 1.5},
        category_caps={"food_delivery": D("100")},
        pinned_days={date(2026, 11, 14): D("150")},
    )
    assert p.weekday_weights == {"Sat": 1.5, "Sun": 1.5}
    p = await plan_preferences.update(
        db,
        u.id,
        weekday_weights={"Fri": 2},
        buffer_pct=D("0"),
        category_caps={"food_delivery": None},
    )
    assert p.weekday_weights == {"Sat": 1.5, "Sun": 1.5, "Fri": 2}
    assert p.category_caps == {} and p.buffer_pct == D("0")
    assert p.pinned_days == {date(2026, 11, 14): D("150.00")}
    assert await plan_preferences.get(db, u.id) == p


@pytest.mark.parametrize(
    "kw",
    [
        {"buffer_pct": D("0.31")},
        {"weekday_weights": {"Fri": 4}},
        {"weekday_weights": {"Friday": 1}},
        {"category_caps": {"luxury": D("10")}},
    ],
)
async def test_plan_preferences_reject_bad_values(db, kw):
    u = await f.user(db)
    await fails(plan_preferences.update(db, u.id, **kw), "invalid_preferences", 422)


# ── catalogues ───────────────────────────────────────────────────────────────────────────


async def test_products_and_merchants(db):
    db.add_all(
        [
            m.Product(
                id="b_savings",
                name="Cont de economii",
                kind="savings_account",
                rate=D("0.04"),
                liquidity="notice",
            ),
            m.Product(
                id="a_pot",
                name="Pușculiță flexibilă",
                kind="flexible_pot",
                rate=D("0.03"),
                liquidity="instant",
            ),
            m.Merchant(
                id="mega_image",
                canonical_name="Mega Image",
                category="groceries",
                aliases=["MEGA IMAGE"],
            ),
            m.Merchant(
                id="emag", canonical_name="eMAG", category="electronics", multi_category=True
            ),
        ]
    )
    await db.flush()
    assert [p.id for p in await products.list_all(db)] == ["a_pot", "b_savings"]
    assert [x.id for x in await merchants.list_all(db)] == ["emag", "mega_image"]
    assert (await merchants.get(db, "emag")).multi_category is True
    await fails(merchants.get(db, "nope"), "not_found", 404)
