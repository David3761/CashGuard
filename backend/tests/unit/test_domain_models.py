"""F2 step 2: domain models (validation rules from work-breakdown F2)."""

import json
from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain import models as dm
from app.domain.enums import Category, Persistence, SignatureEffect

AT = datetime(2026, 6, 15, 10, 5, tzinfo=UTC)


def tx(**kw):
    base = {"id": 918, "amount": Decimal("500"), "occurred_at": AT, "merchant_raw": "MEGA IMAGE"}
    return dm.TxView(**(base | kw))


def fact(**kw):
    base = {"id": 12, "type": "occupation", "value": {"title": "analist sportiv"}, "source": "seed"}
    return dm.LifeFact(**(base | kw))


def signature(**kw):
    base = {
        "effect": "explains",
        "category": "electronics",
        "purpose": "work_tool",
        "strength": 0.9,
    }
    return dm.Signature(**(base | kw))


# ── TxView ───────────────────────────────────────────────────────────────────────────────


def test_tx_defaults_effective_amount_to_amount():
    t = tx()
    assert t.effective_amount == Decimal("500.00")
    assert t.status == "unresolved" and t.direction == "debit"


@pytest.mark.parametrize("kw", [{"effective_amount": Decimal("100")}, {"effective_amount": 0}])
def test_tx_effective_amount_within_range_ok(kw):
    tx(**kw)


@pytest.mark.parametrize(
    "kw",
    [
        {"effective_amount": Decimal("500.01")},
        {"effective_amount": Decimal("-1")},
        {"amount": Decimal("0")},
        {"amount": Decimal("-5")},
        {"occurred_at": datetime(2026, 6, 15, 13, 5)},  # naive
        {"category": "luxury"},
    ],
)
def test_tx_invalid(kw):
    with pytest.raises(ValidationError):
        tx(**kw)


def test_tx_items_are_typed():
    t = tx(items=[{"name": 'Televizor 65"', "qty": 1, "amount": 4500}])
    assert t.items is not None and t.items[0].amount == Decimal("4500.00")
    with pytest.raises(ValidationError):
        tx(items=[{"name": "x", "qty": 0}])


def test_money_is_quantized_and_dumps_as_a_json_number():
    t = tx(amount=Decimal("166.666"))
    assert t.amount == Decimal("166.67")
    dumped = t.model_dump(mode="json")
    assert dumped["amount"] == 166.67 and isinstance(dumped["amount"], float)
    assert isinstance(t.model_dump()["amount"], Decimal)  # Python mode keeps Decimal


def test_models_are_frozen():
    t = tx()
    with pytest.raises(ValidationError):
        t.amount = Decimal("1")  # type: ignore[misc]


# ── LifeFact + typed values ──────────────────────────────────────────────────────────────


def test_fact_value_is_typed_by_fact_type():
    f = fact()
    assert isinstance(f.value, dm.OccupationValue) and f.value.title == "analist sportiv"
    member = fact(type="household_member", value={"role": "child", "age": 7})
    assert isinstance(member.value, dm.HouseholdMemberValue)
    custom = fact(type="custom", value={"anything": "fac cosplay", "n": 3})
    assert isinstance(custom.value, dm.CustomValue)
    assert custom.model_dump()["value"] == {"anything": "fac cosplay", "n": 3}


@pytest.mark.parametrize(
    "kw",
    [
        {"value": {}},  # occupation needs a title
        {"value": {"title": ""}},
        {"type": "household_member", "value": {"role": "pet"}},
        {"type": "household_member", "value": {"role": "child"}},  # a child needs an age
        {"type": "priority", "value": {"category": "concerts", "priority": "protected"}},
        {"type": "priority", "value": {"category": "entertainment", "priority": "important"}},
        {"valid_from": date(2026, 7, 31), "valid_to": date(2026, 7, 1)},
        {"persistence": "temporary"},  # needs valid_to
        {"confidence": 1.2},
        {"type": "religion"},
    ],
)
def test_fact_invalid(kw):
    with pytest.raises(ValidationError):
        fact(**kw)


def test_fact_valid_variants():
    fact(type="household_member", value={"role": "adult"})
    fact(type="household_member", value={"role": "child", "age": 11})
    fact(
        type="priority",
        value={"category": "entertainment", "label": "concerte", "priority": "protected"},
    )
    fact(persistence="temporary", valid_from=date(2026, 7, 1), valid_to=date(2026, 7, 31))
    fact(valid_from=date(2026, 7, 1), valid_to=date(2026, 7, 1))


def test_fact_active_on():
    f = fact(persistence="temporary", valid_from=date(2026, 7, 1), valid_to=date(2026, 7, 31))
    assert not f.active_on(date(2026, 6, 30))
    assert f.active_on(date(2026, 7, 1)) and f.active_on(date(2026, 7, 31))
    assert not f.active_on(date(2026, 8, 1))
    assert not fact(status="rejected").active_on(date(2026, 7, 1))
    assert fact().active_on(date(2030, 1, 1))


def test_fact_json_round_trip_keeps_diacritics_and_emoji():
    f = fact(
        text="Sunt analist sportiv, lucrez de acasă 📺 ăîșț", persistence=Persistence.PERMANENT
    )
    again = dm.LifeFact.model_validate_json(f.model_dump_json())
    assert again == f
    assert "📺" in json.loads(f.model_dump_json())["text"]


# ── Signature ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "kw",
    [
        {"amount_min": Decimal("9000"), "amount_max": Decimal("1500")},
        {"strength": 1.2},
        {"strength": -0.1},
        {"effect": "scales_baseline", "multiplier": Decimal("0")},
        {"category": None, "merchant_hints": []},  # explains needs a category or merchant hints
        {"effect": "expects_event", "expected_amount": None, "time_window": {"months": [8, 9]}},
        {"effect": "expects_event", "expected_amount": Decimal("600")},  # needs a date or months
        {"purpose": "good_purchase"},
        {"replacement_cycle_days": 0},
    ],
)
def test_signature_invalid(kw):
    with pytest.raises(ValidationError):
        signature(**kw)


def test_signature_valid_variants():
    signature(category=None, merchant_hints=["eMAG", "Altex"])
    signature(
        effect=SignatureEffect.SCALES_BASELINE,
        category=Category.GROCERIES,
        multiplier=Decimal("2.1"),
        purpose="household_care",
        strength=1,
    )
    signature(
        effect="expects_event",
        category="books",
        expected_amount=Decimal("600"),
        time_window={"months": [8, 9]},
        purpose="household_care",
    )
    signature(
        effect="expects_event", expected_amount=Decimal("600"), expected_date=date(2026, 9, 1)
    )


@pytest.mark.parametrize(
    "window",
    [
        {"weekdays": [8]},
        {"weekdays": [0]},
        {"months": [13]},
        {"from": "15:00", "to": "12:00"},
        {"from": "12:00", "to": "12:00"},
    ],
)
def test_time_window_invalid(window):
    with pytest.raises(ValidationError):
        dm.TimeWindow.model_validate(window)


def test_time_window_parses_from_and_to():
    w = dm.TimeWindow.model_validate({"weekdays": [5], "from": "12:00", "to": "15:00"})
    assert (w.from_, w.to, w.weekdays) == (time(12), time(15), (5,))
    assert w.model_dump(mode="json", by_alias=True)["from"] == "12:00:00"


# ── Pattern rule ─────────────────────────────────────────────────────────────────────────


def test_rule_match_and_outcome():
    r = dm.PatternRule(
        id=3,
        kind="classify",
        source="answer",
        confidence=0.7,
        hits=2,
        match={
            "category": "restaurants",
            "weekdays": [5],
            "from": "12:00",
            "to": "15:00",
            "amount_min": 60,
            "amount_max": 130,
        },
        outcome={"purpose": "social_connection", "label": "Prânz cu echipa"},
    )
    assert r.match.weekdays == (5,) and r.outcome.label == "Prânz cu echipa"


@pytest.mark.parametrize(
    "match",
    [
        {"weekdays": [8]},
        {"from": "15:00", "to": "12:00"},
        {"amount_min": 130, "amount_max": 60},
    ],
)
def test_rule_match_invalid(match):
    with pytest.raises(ValidationError):
        dm.RuleMatch.model_validate(match)


# ── the rest ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("model", "kw"),
    [
        (dm.Goal, {"id": 1, "amount": 0, "deadline": date(2026, 12, 31)}),
        (dm.IncomeSource, {"id": 1, "source": "Salariu", "amount": 7000, "day_of_month": 32}),
        (dm.FixedCost, {"id": 1, "name": "Chirie", "amount": 2000, "day_of_month": 0}),
        (dm.Pot, {"id": 1, "name": "x", "kind": "event", "target": 3000, "saved": -1}),
        (
            dm.Receivable,
            {"id": 1, "amount": 0, "debtor_label": "colegi", "expected_by": date(2026, 6, 29)},
        ),
        (dm.PlanPreferences, {"buffer_pct": Decimal("0.31")}),
        (dm.PlanPreferences, {"weekday_weights": {"Fri": 3.5}}),
        (dm.PlanPreferences, {"weekday_weights": {"Friday": 1.5}}),
        (dm.UserProfile, {"id": 1, "name": "x", "language": "fr"}),
        (dm.UserProfile, {"id": 1, "name": "x", "household_scale": Decimal("0.9")}),
    ],
)
def test_other_models_reject_invalid_values(model, kw):
    with pytest.raises(ValidationError):
        model(**kw)


def test_plan_preferences_defaults():
    p = dm.PlanPreferences()
    assert p.buffer_pct == Decimal("0.10") and p.weekday_weights == {} and p.pinned_days == {}


def test_user_context_is_frozen_and_complete():
    ctx = dm.UserContext(
        today=date(2026, 6, 15),
        profile=dm.UserProfile(id=1, name="Matei"),
        account=dm.Account(current_balance=Decimal("5200")),
    )
    assert ctx.goal is None and ctx.transactions == () and ctx.questions_asked_today == 0
    with pytest.raises(ValidationError):
        ctx.today = date(2026, 6, 16)  # type: ignore[misc]


# ── additions for the services (B3) ──────────────────────────────────────────────────────


def test_product_ledger_message_notification_views():
    p = dm.Product(
        id="depozit_6",
        name="Depozit 6 luni",
        kind="term_deposit",
        rate=Decimal("0.0550"),
        liquidity="locked",
        min_months=6,
        max_months=6,
    )
    assert p.mock is True
    day = dm.LedgerDay(date=date(2026, 6, 15), budget=Decimal("120"), spent=Decimal("18"))
    assert day.status == "ok"
    msg = dm.MessageView(
        id=381,
        role="assistant",
        content="Ce a fost?",
        created_at=AT,
        quick_replies=["Doar pentru mine"],
        speak=True,
    )
    assert msg.quick_replies == ("Doar pentru mine",) and msg.action_cards == ()
    n = dm.NotificationView(
        id=77, type="overspend", title="Planul s-a actualizat", body="…", created_at=AT
    )
    assert (n.read, n.opens_chat) == (False, False)


@pytest.mark.parametrize(
    ("model", "kw"),
    [
        (dm.Product, {"id": "x", "name": "x", "kind": "crypto", "rate": 1, "liquidity": "instant"}),
        (
            dm.Product,
            {
                "id": "x",
                "name": "x",
                "kind": "term_deposit",
                "rate": 1,
                "liquidity": "locked",
                "min_months": 12,
                "max_months": 6,
            },
        ),
        (dm.LedgerDay, {"date": date(2026, 6, 15), "spent": -1}),
        (dm.MessageView, {"id": 1, "role": "system", "content": "x", "created_at": AT}),
        (
            dm.MessageView,
            {"id": 1, "role": "user", "content": "x", "created_at": datetime(2026, 6, 15, 10, 0)},
        ),
    ],
)
def test_service_views_reject_invalid_values(model, kw):
    with pytest.raises(ValidationError):
        model(**kw)
