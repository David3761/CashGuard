"""F2 step 3: tests/builders.py makes valid objects and the personas of arch 16.1."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain import models as dm
from app.domain.enums import Category, FactType, Purpose, SignatureEffect
from tests import builders as b

PERSONAS = [b.matei_ctx, b.andrei_ctx, b.bianca_ctx, b.ioana_ctx]


def test_small_builders_make_valid_objects():
    assert isinstance(b.tx(), dm.TxView)
    assert isinstance(b.fact(), dm.LifeFact)
    assert isinstance(b.signature(), dm.Signature)
    assert isinstance(b.rule(), dm.PatternRule)
    assert isinstance(b.ctx(), dm.UserContext)


def test_tx_ids_are_unique_and_overrides_apply():
    a, c = b.tx(), b.tx(amount=Decimal("95"), category=Category.RESTAURANTS)
    assert a.id != c.id
    assert c.amount == Decimal("95.00") and c.category == Category.RESTAURANTS


def test_ctx_accepts_overrides():
    ctx = b.ctx(today=date(2026, 7, 1), questions_asked_today=1)
    assert ctx.today == date(2026, 7, 1) and ctx.questions_asked_today == 1


@pytest.mark.parametrize("make", PERSONAS, ids=lambda f: f.__name__)
def test_persona_is_consistent(make):
    ctx = make()
    assert ctx.today == date(2026, 6, 15)  # D35: the demo starts on Monday 2026-06-15
    assert all(f.active_on(ctx.today) for f in ctx.facts)
    assert ctx.goal is not None and ctx.goal_pot is not None
    assert ctx.goal_pot.goal_id == ctx.goal.id and ctx.goal_pot in ctx.pots
    assert all(
        t.status == "resolved" and t.occurred_at.date() < ctx.today for t in ctx.transactions
    )
    # sensitive: health spending is never "explained" or asked about
    assert not any(s.category == Category.HEALTH_PHARMACY for s in ctx.signatures)
    assert dm.UserContext.model_validate_json(ctx.model_dump_json()) == ctx


def test_matei():
    ctx = b.matei_ctx()
    assert (ctx.profile.name, ctx.profile.age, ctx.profile.city) == ("Matei", 26, "București")
    assert ctx.profile.household_scale == Decimal("1.00")
    assert ctx.goal.amount == Decimal("10000.00") and ctx.goal.deadline == date(2026, 12, 31)
    assert ctx.goal.soft is True and ctx.goal_pot.saved == Decimal("5200.00")
    assert [(i.amount, i.day_of_month) for i in ctx.income_sources] == [(Decimal("7000.00"), 10)]
    assert {c.name: c.amount for c in ctx.fixed_costs}["Chirie"] == Decimal("2000.00")
    friday = ctx.rules[0]
    assert friday.match.weekdays == (5,) and friday.confidence == 0.7 and friday.hits == 2
    assert friday.outcome.label == "Prânz cu echipa"
    protected = [
        f for f in ctx.facts if f.type == FactType.PRIORITY and f.value.priority == "protected"
    ]
    assert protected and protected[0].value.category == Category.ENTERTAINMENT
    assert ctx.baselines[Category.GROCERIES].expected_median == Decimal("85.00")


def test_andrei_tv_is_explained_by_his_job():
    ctx = b.andrei_ctx()
    job = next(f for f in ctx.facts if f.type == FactType.OCCUPATION)
    assert "analist sportiv" in job.value.title
    tv = [
        s
        for s in ctx.signatures
        if s.effect == SignatureEffect.EXPLAINS
        and s.category == Category.ELECTRONICS
        and "televizor" in s.item_keywords
    ]
    assert tv and tv[0].purpose == Purpose.WORK_TOOL and tv[0].fact_id == job.id
    assert ctx.profile.household_scale == Decimal("1.50")


def test_bianca_same_tv_is_not_explained():
    ctx = b.bianca_ctx()
    assert ctx.profile.city == "Iași" and ctx.goal.soft is False
    assert not any(s.category == Category.ELECTRONICS for s in ctx.signatures)


def test_ioana_family_of_four():
    ctx = b.ioana_ctx()
    assert ctx.profile.household_scale == Decimal("2.10")
    kids = sorted(
        f.value.age
        for f in ctx.facts
        if f.type == FactType.HOUSEHOLD_MEMBER and f.value.role == "child"
    )
    assert kids == [7, 11]
    assert ctx.baselines[Category.GROCERIES].expected_median == Decimal("140.00")
    assert any(
        s.effect == SignatureEffect.SCALES_BASELINE and s.multiplier == Decimal("2.1")
        for s in ctx.signatures
    )
