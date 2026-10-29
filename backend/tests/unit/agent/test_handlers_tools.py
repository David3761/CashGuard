"""A3 steps 3-4: the handlers through the executor with A2's real `TOOL_SPECS` input models."""

import json
from datetime import UTC, date, datetime
from typing import Any

import pytest

from app.agent.executor import default_registry, execute_tool
from app.agent.tools import TOOL_SPECS
from app.clock import FixedClock, use_clock
from app.domain.enums import FactStatus, Language
from tests.fakes.fake_services import (
    FakeAgentEvents,
    FakeLifeFacts,
    FakePatternRules,
    FakePots,
    FakeSignatures,
    Harness,
)


@pytest.fixture(autouse=True)
def _clock() -> Any:
    with use_clock(FixedClock(datetime(2026, 10, 28, 14, 0, tzinfo=UTC))) as c:
        yield c


def call(h: Harness, name: str, tool_input: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    block = {"id": "toolu_1", "name": name, "input": tool_input}
    out = execute_tool(h.ctx, h.run, block)
    return bool(out.get("is_error")), json.loads(out["content"])


def ok(h: Harness, name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    failed, body = call(h, name, tool_input)
    assert not failed, body
    return body


def code(h: Harness, name: str, tool_input: dict[str, Any]) -> str:
    failed, body = call(h, name, tool_input)
    assert failed, body
    return str(body["error"]["code"])


def test_every_a2_tool_is_registered_with_its_flags() -> None:
    registry = default_registry()
    assert set(registry) == set(TOOL_SPECS)
    assert registry["annotate_transaction"].money
    assert not registry["get_transactions"].money


def test_proactive_annotate_is_refused_with_the_real_registry() -> None:
    h = Harness(trigger="proactive")
    h.add_tx(918, "500.00")
    tool_input = {
        "transaction_id": 918,
        "purpose": "on_behalf_of_others",
        "beneficiary": "shared",
        "people_count": 5,
        "others_will_repay": True,
    }
    assert code(h, "annotate_transaction", tool_input) == "not_allowed_in_proactive"
    assert h.services.transactions.get(1, 918).effective_amount == 500


def test_unknown_tool_with_the_real_registry() -> None:
    assert code(Harness(), "drop_database", {}) == "unknown_tool"


# ── life facts & rules ───────────────────────────────────────────────────────────────────────


OCCUPATION = {
    "type": "occupation",
    "value": {"title": "analist sportiv"},
    "text": "Sunt analist sportiv",
    "persistence": "permanent",
}


def test_add_life_fact_saves_signatures_propagates_and_replans() -> None:
    h = Harness()
    body = ok(h, "add_life_fact", OCCUPATION)
    fact_id = body["fact"]["id"]
    assert body["fact"]["status"] == FactStatus.CONFIRMED
    assert body["fact"]["valid_from"] == "2026-10-28"
    assert h.context.names() == ["signatures_for_fact", "on_fact_changed"]
    sigs = h.services.signatures
    assert isinstance(sigs, FakeSignatures)
    assert (1, fact_id) in sigs.by_fact
    assert body["plan"]["version"] == 8
    assert "fact: occupation" in h.engine.calls[0][1][1]


def test_add_life_fact_temporary_without_valid_to_is_an_error() -> None:
    h = Harness()
    assert code(h, "add_life_fact", {**OCCUPATION, "persistence": "temporary"}) in {
        "invalid_fact",
        "invalid_input",
    }
    facts = h.services.life_facts
    assert isinstance(facts, FakeLifeFacts)
    assert facts.table.rows == {}


def test_update_another_users_fact_is_not_found() -> None:
    owner = Harness(user_id=2)
    fact_id = ok(owner, "add_life_fact", OCCUPATION)["fact"]["id"]
    intruder = Harness(user_id=1, services=owner.services)
    assert code(intruder, "update_life_fact", {"fact_id": fact_id, "text": "x"}) == "not_found"
    assert code(intruder, "expire_life_fact", {"fact_id": fact_id}) == "not_found"


def test_expire_life_fact_clears_its_signatures() -> None:
    h = Harness()
    fact_id = ok(h, "add_life_fact", OCCUPATION)["fact"]["id"]
    body = ok(h, "expire_life_fact", {"fact_id": fact_id})
    assert body["fact"]["status"] == "expired"
    assert body["signatures"] == 0


def test_create_pattern_rule_is_explicit_at_0_9() -> None:
    h = Harness()
    body = ok(
        h,
        "create_pattern_rule",
        {
            "kind": "classify",
            "match": {"category": "restaurants", "weekdays": [5], "from": "12:00", "to": "15:00"},
            "outcome": {"purpose": "social_connection", "label": "Prânz cu echipa"},
        },
    )
    assert body["rule"]["confidence"] == 0.9
    assert body["rule"]["source"] == "explicit"
    assert "plan" not in body  # not a money tool
    rules = h.services.pattern_rules
    assert isinstance(rules, FakePatternRules)
    assert len(rules.table.rows) == 1


def test_classify_rule_without_purpose_is_an_error() -> None:
    h = Harness()
    tool_input = {"kind": "classify", "match": {"category": "restaurants"}, "outcome": {}}
    assert code(h, "create_pattern_rule", tool_input) in {"invalid_rule", "invalid_input"}


# ── pots & goals ─────────────────────────────────────────────────────────────────────────────


def test_create_pot_and_link_a_transaction() -> None:
    h = Harness()
    h.add_tx(77, "900.00")
    pot = ok(
        h,
        "create_pot",
        {"name": "Vacanță august", "target": 3000, "deadline": "2027-08-15", "kind": "event"},
    )["pot"]
    assert (pot["saved"], pot["status"]) == (0.0, "active")
    body = ok(h, "link_transaction_to_pot", {"transaction_id": 77, "pot_id": pot["id"]})
    assert body["plan"]
    assert body["forecast"]
    assert h.services.transactions.get(1, 77).pot_id == pot["id"]


def test_link_to_another_users_pot_is_not_found() -> None:
    h = Harness(user_id=1)
    h.add_tx(77, "900.00")
    pots = h.services.pots
    assert isinstance(pots, FakePots)
    other = pots.create(
        2, {"name": "x", "kind": "event", "target": 10, "saved": 0, "status": "active"}
    )
    assert (
        code(h, "link_transaction_to_pot", {"transaction_id": 77, "pot_id": other.id})
        == "not_found"
    )


def test_closed_pot_refuses_links() -> None:
    h = Harness()
    h.add_tx(77, "900.00")
    pot_id = ok(h, "create_pot", {"name": "Trip", "target": 3000, "kind": "event"})["pot"]["id"]
    ok(h, "close_pot", {"pot_id": pot_id})
    assert code(h, "link_transaction_to_pot", {"transaction_id": 77, "pot_id": pot_id}) == (
        "pot_not_active"
    )


def test_set_goal_with_an_active_goal_is_goal_already_active() -> None:
    h = Harness()
    body = ok(h, "set_goal", {"amount": 10000, "deadline": "2027-06-30"})
    assert body["goal"]["amount"] == 10000.0
    assert body["plan"]["previous_today_budget"] == 31.2
    assert code(h, "set_goal", {"amount": 5000, "deadline": "2027-06-30"}) == "goal_already_active"
    assert ok(h, "update_goal", {"amount": 12000})["goal"]["amount"] == 12000.0


def test_update_goal_without_a_goal_and_a_past_deadline() -> None:
    h = Harness()
    assert code(h, "update_goal", {"amount": 100}) == "no_active_goal"
    assert code(h, "set_goal", {"amount": 100, "deadline": "2026-01-01"}) == "invalid_deadline"


# ── onboarding, shaping, events ──────────────────────────────────────────────────────────────


def test_complete_onboarding_lists_what_is_missing_including_life_context() -> None:
    h = Harness()
    ok(h, "set_goal", {"amount": 10000, "deadline": "2027-06-30"})
    ok(h, "add_income_source", {"source": "Salariu", "amount": 7000, "day_of_month": 10})
    failed, body = call(h, "complete_onboarding", {})
    assert failed
    assert body["error"]["code"] == "onboarding_incomplete"
    assert "fixed_costs" in body["error"]["message"]
    assert "life_context" in body["error"]["message"]
    assert "goal," not in body["error"]["message"]
    ok(h, "add_fixed_cost", {"name": "Chirie", "amount": 2000, "day_of_month": 1})
    ok(h, "add_life_fact", OCCUPATION)
    assert ok(h, "complete_onboarding", {})["onboarded"] is True


def test_shape_budget_merges_a2_list_shapes() -> None:
    h = Harness()
    body = ok(
        h,
        "shape_budget",
        {
            "weekday_weights": [{"weekday": 6, "weight": 1.5}],
            "pin_days": [{"date": "2026-11-07", "amount": 150}],
            "category_caps": [{"category": "food_delivery", "amount_per_week": 100}],
            "buffer_pct": 0.2,
        },
    )
    prefs = body["preferences"]
    assert prefs["weekday_weights"]["Sat"] == 1.5
    assert prefs["weekday_weights"]["Mon"] == 1.0
    assert prefs["pinned_days"] == {"2026-11-07": 150.0}
    assert prefs["category_caps"] == {"food_delivery": 100.0}
    body = ok(
        h,
        "shape_budget",
        {
            "unpin_days": ["2026-11-07"],
            "category_caps": [{"category": "food_delivery", "amount_per_week": None}],
        },
    )
    assert body["preferences"]["pinned_days"] == {}
    assert body["preferences"]["category_caps"] == {}
    assert body["preferences"]["buffer_pct"] == 0.2


def test_life_event_update_of_another_user_is_not_found() -> None:
    owner = Harness(user_id=2)
    event_id = ok(
        owner,
        "add_life_event",
        {"name": "Concert", "date": "2026-11-20", "est_cost": 100, "type": "social"},
    )["life_event"]["id"]
    intruder = Harness(user_id=1, services=owner.services)
    assert code(intruder, "cancel_life_event", {"event_id": event_id}) == "not_found"
    assert ok(owner, "cancel_life_event", {"event_id": event_id})["life_event"]["status"] == (
        "cancelled"
    )


def test_update_life_profile_refuses_facts() -> None:
    h = Harness()
    assert code(h, "update_life_profile", {"key": "occupation", "value": "dev"}) == (
        "use_add_life_fact"
    )
    assert ok(h, "update_life_profile", {"key": "what_works", "value": "liste"})["key"]


# ── reads & ui ───────────────────────────────────────────────────────────────────────────────


def test_reads_write_nothing_and_skip_the_recompute() -> None:
    h = Harness()
    h.add_tx(1, "85.00")
    h.add_tx(2, "40.00", category="restaurants")
    h.add_tx(3, "999.00", user_id=2)
    before = (len(h.services.transactions.rows), h.engine.calls[:])  # type: ignore[attr-defined]
    listed = ok(h, "get_transactions", {"from": "2026-10-20", "to": "2026-10-28"})
    assert [t["id"] for t in listed["transactions"]] == [1, 2] or listed["count"] == 2
    summary = ok(h, "get_spending_summary", {"period_days": 7})
    assert summary["total_effective"] == 125.0
    assert summary["by_category"][0] == {"category": "groceries", "effective": 85.0}
    ok(h, "get_plan_status", {})
    ok(h, "get_goal_forecast", {})
    assert (len(h.services.transactions.rows), h.engine.calls) == before  # type: ignore[attr-defined]
    assert h.run.plan_changed is False


def test_simulate_plan_saves_nothing() -> None:
    h = Harness()
    body = ok(
        h,
        "simulate_plan",
        {"add_events": [{"name": "PS5", "date": "2026-11-20", "est_cost": 2500}]},
    )
    assert body["saved"] is False
    assert body["simulation"]["probability"] == 0.79
    assert h.engine.names() == ["simulate_plan"]
    assert h.run.plan_changed is False


def test_suggest_savings_products_ranks_by_the_goal_horizon() -> None:
    h = Harness()
    h.services.products.products = [  # type: ignore[attr-defined]
        {"id": "flex", "liquidity": "instant", "rate": 0.02, "min_months": 0, "max_months": 12},
        {"id": "depo", "liquidity": "locked", "rate": 0.055, "min_months": 6, "max_months": 24},
    ]
    ok(h, "set_goal", {"amount": 10000, "deadline": date(2027, 8, 1).isoformat()})
    ok(h, "add_income_source", {"source": "Salariu", "amount": 7000, "day_of_month": 10})
    body = ok(h, "suggest_savings_products", {})
    assert body["horizon_months"] == 9
    assert body["stable_income"] is True
    assert [p["id"] for p in body["products"]] == ["depo", "flex"]
    assert [p["rank"] for p in body["products"]] == [1, 2]
    assert all(p["fits"] and p["mock"] for p in body["products"])
    assert body["products"][0]["reason_key"] == "top.locked_fits"
    assert "venit stabil" in body["products"][0]["why_for_you"]  # the user's language (RO)


def test_suggest_savings_products_puts_liquidity_first_for_an_irregular_income() -> None:
    h = Harness(language=Language.EN)
    h.services.products.products = [  # type: ignore[attr-defined]
        {"id": "flex", "liquidity": "instant", "rate": 0.02, "min_months": 0, "max_months": 12},
        {"id": "acct", "liquidity": "notice", "rate": 0.035, "min_months": 3, "max_months": 24},
        {"id": "depo", "liquidity": "locked", "rate": 0.055, "min_months": 6, "max_months": 24},
    ]
    ok(h, "set_goal", {"amount": 3000, "deadline": date(2027, 8, 1).isoformat()})
    ok(
        h,
        "add_life_fact",
        {
            "type": "income_pattern",
            "value": {"irregular": True, "note": "tips"},
            "text": "Venitul meu variază",
            "persistence": "permanent",
        },
    )
    body = ok(h, "suggest_savings_products", {})
    assert [p["id"] for p in body["products"]] == ["flex", "acct", "depo"]
    assert body["products"][0]["why_for_you"].startswith("Your income changes")


def test_show_quick_replies_stores_them_on_the_run() -> None:
    h = Harness(trigger="proactive")
    options = ["Doar pentru mine", "Și pentru alții", "Prefer să nu spun"]
    assert ok(h, "show_quick_replies", {"options": options})["quick_replies"] == options
    assert h.run.quick_replies == options


def test_mark_event_handled_only_for_the_users_event() -> None:
    h = Harness(user_id=1, trigger="proactive")
    events = h.services.agent_events
    assert isinstance(events, FakeAgentEvents)
    mine = events.create(1, {"status": "pending"})
    theirs = events.create(2, {"status": "pending"})
    assert ok(h, "mark_event_handled", {"event_id": mine["id"]})["status"] == "handled"
    assert code(h, "mark_event_handled", {"event_id": theirs["id"]}) == "not_found"


def test_transfer_to_savings_returns_plan_and_undo() -> None:
    h = Harness()
    body = ok(h, "transfer_to_savings", {"amount": 200})
    assert body["undo_available"] is True
    assert body["plan"]["version"] == 8
