"""F2 steps 4-8 (fast mode): life facts, signatures and rules, plan and money rows, results,
the user context and the persona builders. Happy paths and the key rule of each model."""

import json
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.enums import Decision, FactType, HouseholdRole, Purpose
from app.domain.models import (
    FACT_VALUE_MODELS,
    Baseline,
    HouseholdMemberValue,
    LifeFact,
    OccupationValue,
    PatternRule,
    PlanPreferences,
    Pot,
    Product,
    Receivable,
    Signature,
    TimeWindow,
)
from app.domain.results import (
    ActionCard,
    AgentResult,
    Evaluation,
    Forecast,
    PlanSummary,
    QuestionCandidate,
    QuestionHint,
    SimResult,
)
from app.domain.user_context import UserContext
from tests.builders import (
    CREATED,
    TODAY,
    andrei_ctx,
    at,
    bianca_ctx,
    ctx,
    fact,
    ioana_ctx,
    matei_ctx,
    rule,
    signature,
    tx,
)

# ── step 4: life facts ───────────────────────────────────────────────────────────────────────


def test_every_fact_type_has_a_value_model_and_a_valid_default() -> None:
    assert set(FACT_VALUE_MODELS) == set(FactType)
    for fact_type in FactType:
        assert isinstance(fact(fact_type).value, FACT_VALUE_MODELS[fact_type])


def test_the_arch_value_examples_are_typed_by_the_fact_type() -> None:
    occupation = fact(
        FactType.OCCUPATION, value={"title": "analist sportiv", "work_mode": "remote"}
    )
    child = fact(FactType.HOUSEHOLD_MEMBER, value={"role": "child", "age": 7})

    assert occupation.value == OccupationValue(title="analist sportiv", work_mode="remote")
    assert isinstance(child.value, HouseholdMemberValue)
    assert child.value.role is HouseholdRole.CHILD


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param(
            {"type": FactType.HOUSEHOLD_MEMBER, "value": {"role": "child"}}, id="child, no age"
        ),
        pytest.param({"value": {"title": "   "}}, id="blank title"),
        pytest.param({"value": {"species": "cat"}}, id="a pet value for an occupation"),
        pytest.param({"persistence": "temporary"}, id="temporary without valid_to"),
        pytest.param({"valid_to": date(2025, 12, 31)}, id="valid_to before valid_from"),
        pytest.param({"value": {"title": "x", "user_id": 2}}, id="unknown key in the value"),
    ],
)  # fmt: skip
def test_fact_rules(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        fact(**changes)  # type: ignore[arg-type]


def test_a_fact_round_trips_through_json_with_diacritics() -> None:
    original = fact(text="Sunt analist sportiv, lucrez de acasă 📺")

    assert LifeFact.model_validate_json(original.model_dump_json()) == original
    assert original.active_on(TODAY)


# ── step 5: signatures & rules ───────────────────────────────────────────────────────────────


def test_the_arch_signatures_and_rule_examples_validate() -> None:
    tv = signature()
    scales = Signature.model_validate(
        {"effect": "scales_baseline", "category": "groceries", "multiplier": 2.1,
         "purpose": "household_care", "strength": 1, "origin": "library"}
    )  # fmt: skip
    window = TimeWindow.model_validate({"weekdays": [5, 5, 1], "from": "12:00", "to": "15:00"})

    assert tv.purpose is Purpose.WORK_TOOL
    assert scales.multiplier == Decimal("2.1")
    assert window.weekdays == (1, 5)
    assert window.model_dump(mode="json") == {
        "weekdays": [1, 5], "from": "12:00", "to": "15:00", "months": []
    }  # fmt: skip


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"amount_min": "9001"}, id="min above max"),
        pytest.param({"category": None, "merchant_hints": []}, id="explains without a target"),
        pytest.param({"category": "health_pharmacy"}, id="health is sensitive"),
        pytest.param({"purpose": "good_purchase"}, id="unknown purpose"),
        pytest.param({"strength": 1.2}, id="strength above 1"),
    ],
)
def test_signature_rules(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        signature(**changes)


def test_matei_friday_rule_and_its_rules() -> None:
    friday = rule()

    assert friday.match.from_ is not None
    assert friday.match.from_.hour == 12
    assert PatternRule.model_validate_json(friday.model_dump_json()) == friday
    assert friday.replace(confidence=0.9).confidence == 0.9
    with pytest.raises(ValidationError, match="purpose"):
        rule(outcome={})
    with pytest.raises(ValidationError, match="merchant or a category"):
        rule(match={"weekdays": [5]})
    with pytest.raises(ValidationError, match="from must be before to"):
        rule(match={"category": "restaurants", "from": "15:00", "to": "12:00"})


# ── step 6: plan & money rows ────────────────────────────────────────────────────────────────


def test_plan_and_money_rows_validate() -> None:
    receivable = Receivable.model_validate(
        {"id": 9, "transaction_id": 918, "amount": 400, "debtor_label": "colegi", "people_count": 5,
         "amount_each": 100, "expected_by": "2026-06-29", "status": "open", "created_at": CREATED}
    )  # fmt: skip
    pot = Pot.model_validate(
        {"id": 3, "name": "Vacanță august", "kind": "event", "target": 3000, "saved": 0,
         "deadline": "2026-08-15", "monthly_contribution": 1500, "status": "active"}
    )  # fmt: skip
    baseline = Baseline.model_validate(
        {"category": "groceries", "personal_median": 85, "personal_mad": 25, "n": 40,
         "prior_median": 80, "household_multiplier": 1, "expected_median": 85,
         "monthly_expected": 1100}
    )  # fmt: skip

    assert receivable.model_dump(mode="json")["amount"] == 400.0
    assert pot.monthly_contribution == Decimal("1500.00")
    assert baseline.expected_median == Decimal("85.00")


def test_plan_preferences_default_and_fill_missing_weekdays() -> None:
    assert PlanPreferences().buffer_pct == Decimal("0.10")
    shaped = PlanPreferences.model_validate({"weekday_weights": {"Sat": 1.5, "Sun": 1.5}})

    assert shaped.weekday_weights["Mon"] == Decimal("1")
    assert shaped.weekday_weights["Sat"] == Decimal("1.5")
    with pytest.raises(ValidationError):
        PlanPreferences.model_validate({"weekday_weights": {"Sat": 3.5}})


def test_a_product_needs_min_below_max_months() -> None:
    raw = {"id": 1, "name": "Depozit 6 luni", "kind": "term_deposit", "rate": "0.05",
           "liquidity": "locked", "min_months": 6, "max_months": 12}  # fmt: skip

    assert Product.model_validate(raw).mock is True
    with pytest.raises(ValidationError, match="min_months"):
        Product.model_validate({**raw, "min_months": 12})


# ── step 7: results ──────────────────────────────────────────────────────────────────────────


def test_evaluation_for_the_scene_a_question() -> None:
    hint = QuestionHint(reason="basket_ratio", params={"ratio": 6})
    raw = {"category": "groceries", "merchant_id": "mega_image", "purpose": "unknown",
           "beneficiary": "self", "effective_amount": 500, "annotation_source": "auto",
           "confidence": 0.3, "life_fit": 0.1, "anomaly_score": 0.8, "unexplained": 0.72,
           "decision": "ask", "goal_impact": 0.1}  # fmt: skip

    evaluation = Evaluation.model_validate({**raw, "question_hint": hint})

    assert evaluation.decision is Decision.ASK
    with pytest.raises(ValidationError, match="question_hint"):
        Evaluation.model_validate(raw)


def test_question_candidate_priority() -> None:
    candidate = QuestionCandidate(
        transaction_id=918,
        occurred_at=at(TODAY, 13, 5),
        unexplained=0.72,
        goal_impact=0.1,
        question_hint=QuestionHint(reason="basket_ratio"),
    )

    assert candidate.priority == pytest.approx(0.072)


def test_plan_forecast_and_simulation_results() -> None:
    plan = PlanSummary.model_validate(
        {"version": 8, "feasible": True, "today_budget": 29.8, "previous_today_budget": 31.2,
         "next_7_days": [{"date": "2026-11-07", "budget": 44.7}]}
    )  # fmt: skip
    forecast = Forecast.model_validate(
        {"probability": 0.77, "previous_probability": 0.71, "last_week_probability": 0.72,
         "p10": 8650, "p50": 10900, "p90": 12400, "expected_reach_date": "2026-12-04",
         "drivers": [{"category": "food_delivery", "pp_per_100_lei": 2.1}]}
    )  # fmt: skip
    simulation = SimResult.model_validate(
        {"feasible": True, "today_budget": 38.1, "avg_daily_budget": 36.4, "probability": 0.79,
         "diff_vs_current": {"today_budget": 6.9, "probability": 0.08}}
    )  # fmt: skip

    assert plan.model_dump(mode="json")["today_budget"] == 29.8
    assert forecast.p50 == Decimal("10900.00")
    assert simulation.diff_vs_current.probability == 0.08
    with pytest.raises(ValidationError, match="p10"):
        Forecast.model_validate({**forecast.model_dump(), "p50": 1})


def test_agent_result_with_the_payment_card() -> None:
    result = AgentResult(
        text="Am înțeles! Cheltuiala ta reală e 100 lei.",
        quick_replies=("Da", "Altă sumă"),
        action_cards=(
            ActionCard(type="request_payment", receivable_id=9, label="Trimite cererea"),
        ),
        plan_changed=True,
        ref_transaction_id=918,
    )

    assert json.loads(result.model_dump_json())["action_cards"][0]["receivable_id"] == 9
    assert set(AgentResult.model_fields) == {
        "text", "speak_text", "quick_replies", "action_cards", "plan_changed", "ref_transaction_id"
    }  # fmt: skip


# ── step 8: the user context + builders ──────────────────────────────────────────────────────


def test_every_persona_builder_gives_a_valid_context_that_round_trips() -> None:
    for build in (ctx, matei_ctx, andrei_ctx, bianca_ctx, ioana_ctx):
        context = build()
        assert build() == context  # deterministic: no counters, no clock
        assert UserContext.model_validate_json(context.model_dump_json()) == context


def test_the_personas_differ_where_their_lives_differ() -> None:
    andrei, bianca, ioana, matei = andrei_ctx(), bianca_ctx(), ioana_ctx(), matei_ctx()

    assert any(s.purpose is Purpose.WORK_TOOL for s in andrei.signatures)
    assert not any(s.purpose is Purpose.WORK_TOOL for s in bianca.signatures)
    assert sorted(
        f.value.age for f in ioana.facts
        if isinstance(f.value, HouseholdMemberValue) and f.value.age is not None
    ) == [7, 11]  # fmt: skip
    assert not any(f.type is FactType.HOUSEHOLD_MEMBER for f in matei.facts)
    assert matei.rules[0].outcome.label == "Prânz cu echipa"
    assert matei.goal is not None
    assert matei.goal.amount == Decimal("10000.00")


def test_the_context_rejects_an_inconsistent_view() -> None:
    expired = fact(id=9, valid_to=date(2026, 6, 14))
    hypothesis = fact(id=8, status="hypothesis")

    with pytest.raises(ValidationError, match="not confirmed and active"):
        ctx(facts=[expired])
    with pytest.raises(ValidationError, match="not confirmed and active"):
        ctx(facts=[hypothesis])
    with pytest.raises(ValidationError, match="hypotheses"):
        ctx(hypotheses=[fact()])
    assert ctx(facts=[fact(valid_to=TODAY)]).facts[0].valid_to == TODAY


def test_the_tx_builder_takes_plain_overrides() -> None:
    assert tx(amount="500", effective_amount="100").effective_amount == Decimal("100.00")
