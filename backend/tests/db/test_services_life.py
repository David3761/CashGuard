"""B3 step 4: life context & savings services (facts, signatures, rules, receivables, pots,
forecasts, baselines)."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain import models as dm
from app.domain.enums import Category, FactStatus, PotKind, ReceivableStatus, SignatureEffect
from app.domain.results import Driver, Forecast
from app.services import (
    accounts,
    baselines,
    forecasts,
    goals,
    life_facts,
    pattern_rules,
    pots,
    receivables,
    signatures,
)
from tests import builders as b
from tests import factories as f
from tests.db.test_services_profile import fails, two  # noqa: F401  (fixture)

D = Decimal
JULY = date(2026, 7, 10)


def occupation(**kw) -> dm.LifeFact:
    return b.fact(
        **(
            {
                "type": "occupation",
                "value": {"title": "analist sportiv"},
                "source": "chat",
                "text": "Sunt analist sportiv",
            }
            | kw
        )
    )


# ── life facts ───────────────────────────────────────────────────────────────────────────


async def test_fact_create_get_and_typed_value(db):
    u = await f.user(db)
    fact = await life_facts.create(db, u.id, occupation())  # ours: a LifeFact has an id; ignored
    assert fact.id is not None and isinstance(fact.value, dm.OccupationValue)
    assert await life_facts.get(db, u.id, fact.id) == fact
    custom = await life_facts.create(
        db, u.id, b.fact(type="custom", value={"description": "cosplay"}, source="voice")
    )
    assert custom.value.model_dump() == {"description": "cosplay"}  # our CustomValue


async def test_fact_lists_by_status_and_date(db):
    u = await f.user(db)
    job = await life_facts.create(db, u.id, occupation())
    mother = await life_facts.create(
        db,
        u.id,
        b.fact(
            type="household_member",
            value={"role": "adult", "relation": "mama"},
            source="chat",
            persistence="temporary",
            valid_from=date(2026, 7, 1),
            valid_to=date(2026, 7, 31),
        ),
    )
    car = await life_facts.create(
        db,
        u.id,
        b.fact(
            type="vehicle",
            value={"kind": "car"},
            source="inferred",
            status="hypothesis",
            confidence=0.5,
        ),
    )
    assert {x.id for x in await life_facts.list_active(db, u.id, JULY)} == {job.id, mother.id}
    assert {x.id for x in await life_facts.list_active(db, u.id, date(2026, 8, 1))} == {job.id}
    assert [x.id for x in await life_facts.list_hypotheses(db, u.id)] == [car.id]
    hyps = await life_facts.list_all(db, u.id, FactStatus.HYPOTHESIS)
    assert [x.id for x in hyps] == [car.id]
    assert len(await life_facts.list_all(db, u.id)) == 3


async def test_hypothesis_confirm_and_reject(db):
    u = await f.user(db)
    h1 = await life_facts.create(
        db,
        u.id,
        b.fact(
            type="pet",
            value={"kind": "câine"},
            source="inferred",
            status="hypothesis",
            confidence=0.5,
        ),
    )
    h2 = await life_facts.create(
        db,
        u.id,
        b.fact(
            type="vehicle",
            value={"kind": "car"},
            source="inferred",
            status="hypothesis",
            confidence=0.5,
        ),
    )
    confirmed = await life_facts.confirm(db, u.id, h1.id)
    assert confirmed.status == FactStatus.CONFIRMED and confirmed.confidence >= 0.9
    rejected = await life_facts.reject(db, u.id, h2.id)
    assert rejected.status == FactStatus.REJECTED
    assert h2.id not in {x.id for x in await life_facts.list_active(db, u.id, JULY)}
    assert await life_facts.list_hypotheses(db, u.id) == []


@pytest.mark.parametrize(
    ("status", "action"),
    [
        ("confirmed", "confirm"),
        ("confirmed", "reject"),
        ("rejected", "confirm"),
        ("rejected", "reject"),
        ("expired", "confirm"),
        ("hypothesis", "expire"),
        ("expired", "expire"),
        ("rejected", "expire"),
    ],
)
async def test_fact_invalid_transitions(db, status, action):
    u = await f.user(db)
    fact = await life_facts.create(db, u.id, occupation(status=status))
    call = (
        life_facts.expire(db, u.id, fact.id, JULY)
        if action == "expire"
        else getattr(life_facts, action)(db, u.id, fact.id)
    )
    await fails(call, "invalid_transition", 409)


async def test_expired_fact_is_gone_after_valid_to(db):
    u = await f.user(db)
    fact = await life_facts.create(db, u.id, occupation(valid_from=date(2026, 1, 1)))
    gone = await life_facts.expire(db, u.id, fact.id, date(2026, 6, 30))
    assert (gone.status, gone.valid_to) == (FactStatus.EXPIRED, date(2026, 6, 30))
    assert await life_facts.list_active(db, u.id, JULY) == []
    await fails(
        life_facts.expire(
            db,
            u.id,
            (await life_facts.create(db, u.id, occupation(valid_from=date(2026, 7, 1)))).id,
            date(2026, 6, 1),
        ),
        "invalid_fact",
        422,
    )


async def test_fact_update_revalidates(db):
    u = await f.user(db)
    fact = await life_facts.create(db, u.id, occupation())
    moved = await life_facts.update(
        db, u.id, fact.id, value={"title": "jurnalist sportiv"}, text="Acum sunt jurnalist"
    )
    assert moved.value.title == "jurnalist sportiv" and moved.text == "Acum sunt jurnalist"
    await fails(life_facts.update(db, u.id, fact.id, value={"title": ""}), "invalid_fact", 422)
    await fails(
        life_facts.update(db, u.id, fact.id, persistence="temporary"), "invalid_fact", 422
    )  # temporary needs valid_to


async def test_fact_delete_removes_its_signatures(db):
    u = await f.user(db)
    fact = await life_facts.create(db, u.id, occupation())
    await signatures.replace_for_fact(db, u.id, fact.id, [b.signature(fact_id=None)])
    await life_facts.delete(db, u.id, fact.id)
    await fails(life_facts.get(db, u.id, fact.id), "not_found")
    assert await signatures.list_active(db, u.id) == []


async def test_facts_isolation(two, db):  # noqa: F811
    a, c = two
    fact = await life_facts.create(db, c.id, occupation(status="hypothesis", confidence=0.5))
    for call in (
        life_facts.get(db, a.id, fact.id),
        life_facts.confirm(db, a.id, fact.id),
        life_facts.reject(db, a.id, fact.id),
        life_facts.delete(db, a.id, fact.id),
        life_facts.update(db, a.id, fact.id, text="x"),
        life_facts.expire(db, a.id, fact.id, JULY),
    ):
        await fails(call, "not_found", 404)
    assert await life_facts.list_all(db, a.id) == []


# ── signatures ───────────────────────────────────────────────────────────────────────────


async def test_replace_for_fact_swaps_the_set(db):
    u = await f.user(db)
    fact = await life_facts.create(db, u.id, occupation())
    first = await signatures.replace_for_fact(
        db,
        u.id,
        fact.id,
        [
            b.signature(
                item_keywords=("televizor",),
                replacement_cycle_days=900,
                time_window={"weekdays": [5], "from": "12:00", "to": "15:00"},
            ),
        ],
    )
    assert first[0].fact_id == fact.id and first[0].time_window.from_ is not None
    second = await signatures.replace_for_fact(
        db,
        u.id,
        fact.id,
        [
            b.signature(category=Category.SUBSCRIPTIONS, merchant_hints=("DAZN",)),
            b.signature(category=Category.ELECTRONICS),
        ],
    )
    stored = await signatures.list_for_fact(db, u.id, fact.id)
    assert sorted(s.category for s in stored) == sorted(s.category for s in second)
    assert len(stored) == 2


async def test_replace_for_fact_is_atomic(db, monkeypatch):
    u = await f.user(db)
    fact = await life_facts.create(db, u.id, occupation())
    await signatures.replace_for_fact(db, u.id, fact.id, [b.signature()])
    real = signatures._to_row
    calls = {"n": 0}

    def flaky(*args, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("halfway")
        return real(*args, **kw)

    monkeypatch.setattr(signatures, "_to_row", flaky)
    with pytest.raises(RuntimeError):
        await signatures.replace_for_fact(
            db, u.id, fact.id, [b.signature(category=Category.BOOKS)] * 3
        )
    old = await signatures.list_for_fact(db, u.id, fact.id)
    assert [s.category for s in old] == [Category.ELECTRONICS]


async def test_list_active_only_confirmed_facts_and_by_effect(db):
    u = await f.user(db)
    job = await life_facts.create(db, u.id, occupation())
    guess = await life_facts.create(
        db,
        u.id,
        b.fact(
            type="pet",
            value={"kind": "pisică"},
            source="inferred",
            status="hypothesis",
            confidence=0.5,
        ),
    )
    family = await life_facts.create(
        db, u.id, b.fact(type="household_member", value={"role": "adult"}, source="seed")
    )
    await signatures.replace_for_fact(db, u.id, job.id, [b.signature()])
    await signatures.replace_for_fact(db, u.id, guess.id, [b.signature(category="pets")])
    await signatures.replace_for_fact(
        db,
        u.id,
        family.id,
        [
            b.signature(
                effect="scales_baseline",
                category="groceries",
                multiplier=D("1.5"),
                purpose="household_care",
            )
        ],
    )
    assert {s.category for s in await signatures.list_active(db, u.id)} == {
        Category.ELECTRONICS,
        Category.GROCERIES,
    }
    scaled = await signatures.list_active(db, u.id, SignatureEffect.SCALES_BASELINE)
    assert [s.category for s in scaled] == [Category.GROCERIES]


async def test_signatures_isolation(two, db):  # noqa: F811
    a, c = two
    fact = await life_facts.create(db, c.id, occupation())
    await fails(signatures.replace_for_fact(db, a.id, fact.id, []), "not_found")
    await fails(signatures.list_for_fact(db, a.id, fact.id), "not_found")
    await signatures.replace_for_fact(db, c.id, fact.id, [b.signature()])
    assert await signatures.list_active(db, a.id) == []


# ── pattern rules ────────────────────────────────────────────────────────────────────────


async def test_rule_learning_cycle(db, fixed_clock):
    u = await f.user(db)
    rule = await pattern_rules.create(db, u.id, b.rule())
    assert rule.id is not None and rule.match.weekdays == (5,)
    hit = await pattern_rules.record_hit(db, u.id, rule.id)
    assert hit.hits == 3 and hit.last_hit_at == fixed_clock.now()
    assert (await pattern_rules.set_confidence(db, u.id, rule.id, 0.9)).confidence == 0.9
    assert (await pattern_rules.record_miss(db, u.id, rule.id)).misses == 1
    await fails(pattern_rules.set_confidence(db, u.id, rule.id, 1.2), "invalid_confidence", 422)
    off = await pattern_rules.deactivate(db, u.id, rule.id)
    assert off.active is False
    assert (await pattern_rules.deactivate(db, u.id, rule.id)).active is False
    assert await pattern_rules.list_active(db, u.id) == []


async def test_rules_listed_by_confidence(db):
    u = await f.user(db)
    low = await pattern_rules.create(db, u.id, b.rule(confidence=0.7))
    high = await pattern_rules.create(
        db,
        u.id,
        b.rule(
            kind="suppress", confidence=0.9, match={"category": "restaurants", "amount_max": 30}
        ),
    )
    assert [r.id for r in await pattern_rules.list_active(db, u.id)] == [high.id, low.id]


async def test_rules_isolation(two, db):  # noqa: F811
    a, c = two
    rule = await pattern_rules.create(db, c.id, b.rule())
    for name in ("get", "record_hit", "record_miss", "deactivate"):
        await fails(getattr(pattern_rules, name)(db, a.id, rule.id), "not_found")
    await fails(pattern_rules.set_confidence(db, a.id, rule.id, 0.5), "not_found")
    assert await pattern_rules.list_active(db, a.id) == []


# ── receivables ──────────────────────────────────────────────────────────────────────────


async def new_receivable(db, user_id, **kw):
    base = {
        "amount": D("400"),
        "debtor_label": "colegi",
        "expected_by": date(2026, 6, 29),
        "people_count": 4,
        "amount_each": D("100"),
    }
    return await receivables.create(db, user_id, **(base | kw))


async def test_receivable_request_then_paid(db, fixed_clock):
    u = await f.user(db)
    r = await new_receivable(db, u.id)
    assert r.status == ReceivableStatus.OPEN and r.amount_each == D("100.00")
    req = await receivables.update_status(db, u.id, r.id, ReceivableStatus.REQUESTED)
    assert req.requested_at == fixed_clock.now()
    paid = await receivables.update_status(db, u.id, r.id, ReceivableStatus.PAID)
    assert paid.paid_at == fixed_clock.now()


async def test_receivable_paid_without_a_request_and_cancel(db):
    u = await f.user(db)
    r1, r2, r3 = [await new_receivable(db, u.id) for _ in range(3)]
    assert (await receivables.update_status(db, u.id, r1.id, "paid")).status == "paid"
    assert (await receivables.cancel(db, u.id, r2.id)).status == "cancelled"
    await receivables.update_status(db, u.id, r3.id, "requested")
    assert (await receivables.cancel(db, u.id, r3.id)).status == "cancelled"


@pytest.mark.parametrize(
    ("path", "then"),
    [
        (["requested"], "requested"),
        (["requested"], "open"),
        (["paid"], "requested"),
        (["paid"], "cancelled"),
        (["cancelled"], "requested"),
        (["cancelled"], "paid"),
        ([], "open"),
    ],
)
async def test_receivable_invalid_transitions(db, path, then):
    u = await f.user(db)
    r = await new_receivable(db, u.id)
    for step in path:
        await receivables.update_status(db, u.id, r.id, step)
    await fails(receivables.update_status(db, u.id, r.id, then), "invalid_transition", 409)


async def test_receivable_lists(db):
    u = await f.user(db)
    late = await new_receivable(db, u.id, expected_by=date(2026, 7, 15))
    soon = await new_receivable(db, u.id, expected_by=date(2026, 6, 20))
    done = await new_receivable(db, u.id)
    await receivables.update_status(db, u.id, done.id, "paid")
    assert [x.id for x in await receivables.list_open(db, u.id)] == [soon.id, late.id]
    assert [x.id for x in await receivables.list_all(db, u.id, ReceivableStatus.PAID)] == [done.id]
    assert len(await receivables.list_all(db, u.id)) == 3


@pytest.mark.parametrize("kw", [{"amount": D("0")}, {"people_count": 0}, {"amount_each": D("-1")}])
async def test_receivable_rejects_bad_values(db, kw):
    u = await f.user(db)
    await fails(new_receivable(db, u.id, **kw), "invalid_amount", 422)


async def test_receivables_isolation(two, db):  # noqa: F811
    a, c = two
    r = await new_receivable(db, c.id)
    await fails(receivables.get(db, a.id, r.id), "not_found")
    await fails(receivables.update_status(db, a.id, r.id, "requested"), "not_found")
    await fails(receivables.cancel(db, a.id, r.id), "not_found")
    assert await receivables.list_open(db, a.id) == []


# ── pots ─────────────────────────────────────────────────────────────────────────────────


async def test_pot_lifecycle_and_saved(db):
    u = await f.user(db)
    pot = await pots.create(
        db,
        u.id,
        name="Vacanță august",
        kind=PotKind.EVENT,
        target=D("3000"),
        deadline=date(2026, 8, 15),
        monthly_contribution=D("1500"),
    )
    assert (pot.saved, pot.status) == (D("0"), "active")
    assert (await pots.add_saved(db, u.id, pot.id, D("1500"))).saved == D("1500.00")
    assert (await pots.add_saved(db, u.id, pot.id, D("-900"))).saved == D("600.00")  # Wizz Air
    await fails(pots.add_saved(db, u.id, pot.id, D("-600.01")), "insufficient_pot_balance", 409)
    assert (await pots.get(db, u.id, pot.id)).saved == D("600.00")
    renamed = await pots.update(db, u.id, pot.id, name="Vacanță", target=D("3200"))
    assert (renamed.name, renamed.target, renamed.deadline) == (
        "Vacanță",
        D("3200.00"),
        date(2026, 8, 15),
    )
    assert (await pots.close(db, u.id, pot.id)).status == "closed"
    await fails(pots.close(db, u.id, pot.id), "invalid_transition", 409)
    await fails(pots.update(db, u.id, pot.id, name="x"), "invalid_transition", 409)
    assert await pots.list_active(db, u.id) == []


async def test_goal_pot_first_and_mirrored_in_the_account(db):
    u = await f.user(db)
    await accounts.create(db, u.id, current_balance=D("2850"))
    event_pot = await pots.create(db, u.id, name="Vacanță", kind=PotKind.EVENT, target=D("3000"))
    goal = await goals.create(
        db, u.id, amount=D("10000"), deadline=date(2026, 12, 31), motivation="Fond 10.000"
    )
    gp = await pots.goal_pot(db, u.id)
    assert gp is not None and gp.goal_id == goal.id
    assert [p.id for p in await pots.list_active(db, u.id)] == [gp.id, event_pot.id]
    await pots.add_saved(db, u.id, gp.id, D("760"))
    assert (await accounts.get(db, u.id)).savings_pot == D("760.00")
    await pots.add_saved(db, u.id, event_pot.id, D("100"))  # not the goal pot: no mirror
    assert (await accounts.get(db, u.id)).savings_pot == D("760.00")


@pytest.mark.parametrize("kw", [{"target": D("0")}, {"monthly_contribution": D("-1")}])
async def test_pot_rejects_bad_values(db, kw):
    u = await f.user(db)
    base = {"name": "x", "kind": PotKind.CUSTOM, "target": D("10")}
    await fails(pots.create(db, u.id, **(base | kw)), "invalid_amount", 422)


async def test_pots_isolation(two, db):  # noqa: F811
    a, c = two
    pot = await pots.create(db, c.id, name="x", kind=PotKind.CUSTOM, target=D("10"))
    for call in (
        pots.get(db, a.id, pot.id),
        pots.close(db, a.id, pot.id),
        pots.update(db, a.id, pot.id, name="y"),
        pots.add_saved(db, a.id, pot.id, D("1")),
    ):
        await fails(call, "not_found")
    assert await pots.list_active(db, a.id) == [] and await pots.goal_pot(db, a.id) is None


# ── forecasts ────────────────────────────────────────────────────────────────────────────


def fc(p: float, day: date, weekly: bool = False, version: int = 1) -> Forecast:
    return Forecast(
        probability=p,
        p10=D("8650"),
        p50=D("10900"),
        p90=D("12400"),
        plan_version=version,
        sim_date=day,
        is_weekly_snapshot=weekly,
        drivers=(Driver(category=Category.FOOD_DELIVERY, pp_per_100_lei=2.1),),
    )


async def test_forecast_latest_previous_and_last_week(db):
    u = await f.user(db)
    g = await goals.create(db, u.id, amount=D("10000"), deadline=date(2026, 12, 31))
    assert await forecasts.latest(db, u.id) is None
    await forecasts.save(db, u.id, fc(0.70, date(2026, 6, 1), weekly=True), goal_id=g.id)
    await forecasts.save(db, u.id, fc(0.72, date(2026, 6, 8), weekly=True), goal_id=g.id)
    await forecasts.save(db, u.id, fc(0.78, date(2026, 6, 15), weekly=True), goal_id=g.id)
    await forecasts.save(
        db, u.id, fc(0.71, date(2026, 6, 15), version=2), goal_id=g.id, reason="new transactions"
    )
    latest = await forecasts.latest(db, u.id)
    assert latest is not None
    # "71%, era 78%, săptămâna trecută 72%": last week = the newest snapshot before this Monday
    assert (latest.probability, latest.previous_probability, latest.last_week_probability) == (
        0.71,
        0.78,
        0.72,
    )
    assert latest.drivers[0].category == Category.FOOD_DELIVERY
    assert (await forecasts.last_weekly_snapshot(db, u.id)).probability == 0.78
    assert [x.probability for x in await forecasts.weekly_history(db, u.id)] == [0.7, 0.72, 0.78]


async def test_forecast_needs_a_plan_version(db):
    u = await f.user(db)
    g = await goals.create(db, u.id, amount=D("100"), deadline=date(2026, 12, 31))
    bad = Forecast(probability=0.5, p10=D("1"), p50=D("2"), p90=D("3"))
    await fails(forecasts.save(db, u.id, bad, goal_id=g.id), "invalid_forecast", 422)


async def test_forecasts_isolation(two, db):  # noqa: F811
    a, c = two
    g = await goals.create(db, c.id, amount=D("100"), deadline=date(2026, 12, 31))
    await forecasts.save(db, c.id, fc(0.5, date(2026, 6, 15), weekly=True), goal_id=g.id)
    assert await forecasts.latest(db, a.id) is None
    assert await forecasts.last_weekly_snapshot(db, a.id) is None
    await fails(forecasts.save(db, a.id, fc(0.5, date(2026, 6, 15)), goal_id=g.id), "not_found")


# ── baselines ────────────────────────────────────────────────────────────────────────────


def _baseline(category: Category, **fields: object) -> dm.Baseline:
    """A complete baseline (our F2 Baseline has no defaults: E6 always fills every column)."""
    row: dict[str, object] = {
        "personal_median": D("0"),
        "personal_mad": D("0"),
        "n": 0,
        "prior_median": D("0"),
        "household_multiplier": D("1"),
        "expected_median": D("0"),
        "monthly_expected": D("0"),
    }
    return dm.Baseline.model_validate({"category": category, **row, **fields})


async def test_baselines_replace_all(two, db):  # noqa: F811
    a, c = two
    first = [
        _baseline(Category.GROCERIES, expected_median=D("85"), n=48),
        _baseline(Category.RESTAURANTS, expected_median=D("90"), n=16),
    ]
    got = await baselines.replace_all(db, a.id, first)
    assert set(got) == {Category.GROCERIES, Category.RESTAURANTS}
    scaled = [
        _baseline(Category.GROCERIES, expected_median=D("178.50"), household_multiplier=D("2.1"))
    ]
    await baselines.replace_all(db, a.id, scaled)
    stored = await baselines.list_all(db, a.id)
    assert list(stored) == [Category.GROCERIES]
    assert stored[Category.GROCERIES].expected_median == D("178.50")
    assert await baselines.list_all(db, c.id) == {}


async def test_baselines_reject_duplicate_categories(db):
    u = await f.user(db)
    dup = [_baseline(Category.GROCERIES)] * 2
    await fails(baselines.replace_all(db, u.id, dup), "invalid_baselines", 422)
