"""A2: tool schemas, registry and `tools_for` (arch 6.4, 6.6, 6.7, 6.8, D20-D22, D46)."""

import json
import re
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.agent.tools import (
    MAX_OPTIONAL_PARAMS,
    MAX_STRICT_TOOLS,
    MAX_UNION_PARAMS,
    STRICT_PRIORITY,
    TOOL_SPECS,
    ToolState,
    input_schema,
    schema_cost,
    tools_for,
)

# Arch 6.6, in the doc's order (every 🆕 tool included).
ARCH_TOOLS = {
    "get_transactions", "get_spending_summary", "get_plan_status", "set_goal", "update_goal",
    "add_life_event", "update_life_event", "cancel_life_event", "add_income_source",
    "update_income_source", "remove_income_source", "add_fixed_cost", "update_fixed_cost",
    "remove_fixed_cost", "complete_onboarding", "record_slip_reason", "shape_budget",
    "simulate_plan", "record_reflection", "update_life_profile", "suggest_savings_products",
    "transfer_to_savings", "show_quick_replies", "mark_event_handled", "get_transaction",
    "annotate_transaction", "create_receivable", "cancel_receivable", "mark_receivable_paid",
    "offer_payment_request", "add_life_fact", "update_life_fact", "expire_life_fact",
    "confirm_hypothesis", "create_pattern_rule", "create_pot", "update_pot", "close_pot",
    "link_transaction_to_pot", "get_goal_forecast",
}  # fmt: skip
# Arch 6.7 "Money-related tools" (golden).
MONEY_TOOLS = {
    "set_goal", "update_goal", "add_life_event", "update_life_event", "cancel_life_event",
    "add_income_source", "update_income_source", "remove_income_source", "add_fixed_cost",
    "update_fixed_cost", "remove_fixed_cost", "shape_budget", "record_slip_reason",
    "transfer_to_savings", "complete_onboarding", "annotate_transaction", "create_receivable",
    "cancel_receivable", "mark_receivable_paid", "add_life_fact", "update_life_fact",
    "expire_life_fact", "confirm_hypothesis", "create_pot", "update_pot", "close_pot",
    "link_transaction_to_pot",
}  # fmt: skip
# D22: get_* tools, simulate_plan, suggest_savings_products, show_quick_replies, mark_event_handled.
PROACTIVE_TOOLS = {
    "get_transactions", "get_transaction", "get_spending_summary", "get_plan_status",
    "get_goal_forecast", "simulate_plan", "suggest_savings_products", "show_quick_replies",
    "mark_event_handled",
}  # fmt: skip
# Keys the API rejects in a strict schema (structured outputs limitations).
UNSUPPORTED = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
               "minLength", "maxLength", "maxItems", "$ref", "$defs"}  # fmt: skip

SCHEMAS = {name: input_schema(spec.input_model) for name, spec in TOOL_SPECS.items()}


def _objects(node: Any) -> list[dict[str, Any]]:
    found = []
    if isinstance(node, dict):
        if node.get("type") == "object":
            found.append(node)
        for value in node.values():
            found.extend(_objects(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_objects(item))
    return found


def _keys(node: Any) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {key for value in node.values() for key in _keys(value)}
    if isinstance(node, list):
        return {key for item in node for key in _keys(item)}
    return set()


def _property_names(node: Any) -> set[str]:
    return {name for obj in _objects(node) for name in obj["properties"]}


def test_the_registry_has_exactly_the_arch_tools() -> None:
    assert set(TOOL_SPECS) == ARCH_TOOLS


@pytest.mark.parametrize("name", sorted(TOOL_SPECS))
def test_every_schema_is_valid_json_schema(name: str) -> None:
    Draft202012Validator.check_schema(SCHEMAS[name])
    assert SCHEMAS[name]["type"] == "object"


@pytest.mark.parametrize("name", sorted(TOOL_SPECS))
def test_every_object_is_closed_and_lists_its_required_keys(name: str) -> None:
    for obj in _objects(SCHEMAS[name]):
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) <= set(obj["properties"])


@pytest.mark.parametrize("name", sorted(TOOL_SPECS))
def test_no_schema_uses_a_keyword_strict_mode_rejects(name: str) -> None:
    assert not _keys(SCHEMAS[name]) & UNSUPPORTED
    for obj in _objects(SCHEMAS[name]):
        assert obj.get("minItems", 0) <= 1


def test_no_user_id_anywhere() -> None:
    for name, schema in SCHEMAS.items():
        assert "user_id" not in _property_names(schema), name
    assert "user_id" not in json.dumps(SCHEMAS)


def test_a_smuggled_user_id_is_rejected_by_the_input_model() -> None:
    with pytest.raises(ValidationError, match="user_id"):
        TOOL_SPECS["get_transaction"].input_model.model_validate(
            {"transaction_id": 918, "user_id": 2}
        )


def test_names_are_unique_snake_case_and_short() -> None:
    names = [tool["name"] for tool in tools_for(ToolState(has_active_goal=False), "chat")]
    assert len(names) == len(set(names))
    for name in TOOL_SPECS:
        assert re.fullmatch(r"[a-z][a-z0-9]*(_[a-z0-9]+)*", name)
        assert len(name) <= 64


@pytest.mark.parametrize("name", sorted(TOOL_SPECS))
def test_descriptions_say_when_to_use_the_tool(name: str) -> None:
    description = TOOL_SPECS[name].description
    assert len(description) >= 40
    assert "Use it " in description


def test_the_money_flag_equals_the_arch_money_tools() -> None:
    assert {name for name, spec in TOOL_SPECS.items() if spec.flags.money} == MONEY_TOOLS
    assert all(spec.flags.write for spec in TOOL_SPECS.values() if spec.flags.money)


def test_the_read_only_flag_equals_the_d22_set() -> None:
    assert {name for name, spec in TOOL_SPECS.items() if spec.flags.read_only} == PROACTIVE_TOOLS


def _names(has_active_goal: bool, trigger: str) -> list[str]:
    return [tool["name"] for tool in tools_for(ToolState(has_active_goal=has_active_goal), trigger)]


def test_without_an_active_goal_set_goal_is_offered_and_update_goal_is_not() -> None:
    names = _names(False, "chat")
    assert "set_goal" in names
    assert "update_goal" not in names
    assert set(names) == ARCH_TOOLS - {"update_goal"}


def test_with_an_active_goal_update_goal_is_offered_and_set_goal_is_not() -> None:
    names = _names(True, "chat")
    assert "update_goal" in names
    assert "set_goal" not in names
    assert set(names) == ARCH_TOOLS - {"set_goal"}


@pytest.mark.parametrize("has_active_goal", [False, True])
def test_a_proactive_run_gets_exactly_the_read_only_set(has_active_goal: bool) -> None:
    assert set(_names(has_active_goal, "proactive")) == PROACTIVE_TOOLS


@pytest.mark.parametrize(
    ("has_active_goal", "trigger"),
    [(False, "chat"), (True, "chat"), (False, "onboarding"), (True, "proactive")],
)
def test_the_tool_list_is_deterministic_and_within_the_strict_limits(
    has_active_goal: bool, trigger: str
) -> None:
    tools = tools_for(ToolState(has_active_goal=has_active_goal), trigger)
    again = tools_for(ToolState(has_active_goal=has_active_goal), trigger)
    assert json.dumps(tools) == json.dumps(again)
    names = [tool["name"] for tool in tools]
    assert names == [name for name in TOOL_SPECS if name in set(names)]  # registry order
    strict = [tool for tool in tools if tool.get("strict")]
    assert 0 < len(strict) <= MAX_STRICT_TOOLS
    costs = [schema_cost(dict(tool["input_schema"])) for tool in strict]
    assert sum(optional for optional, _ in costs) <= MAX_OPTIONAL_PARAMS
    assert sum(unions for _, unions in costs) <= MAX_UNION_PARAMS
    assert all("cache_control" not in tool for tool in tools)  # the LLM wrapper owns caching


def test_the_typical_calls_are_strict_in_a_chat_run() -> None:
    strict = {
        tool["name"]
        for tool in tools_for(ToolState(has_active_goal=True), "chat")
        if tool.get("strict")
    }
    assert {
        "annotate_transaction",
        "offer_payment_request",
        "add_life_event",
        "update_goal",
    } <= strict
    assert strict <= set(STRICT_PRIORITY)


def test_a_caller_cannot_mutate_the_cached_schemas() -> None:
    tools = tools_for(ToolState(has_active_goal=False), "chat")
    tools[0]["input_schema"]["properties"] = {}
    assert (
        tools_for(ToolState(has_active_goal=False), "chat")[0]["input_schema"]
        != tools[0]["input_schema"]
    )


# The arch 6.6 "typical calls" (and the 6.7 shaping examples): valid for both the schema Claude
# sees and the executor's Pydantic check.
TYPICAL_CALLS = [
    ("annotate_transaction", {"transaction_id": 918, "purpose": "on_behalf_of_others",
                              "beneficiary": "shared", "people_count": 5,
                              "others_will_repay": True, "debtor_label": "colegi"}),
    ("offer_payment_request", {"receivable_id": 9}),
    ("annotate_transaction", {"transaction_id": 920, "purpose": "unplanned_discretionary",
                              "beneficiary": "self"}),
    ("add_life_fact", {"type": "occupation", "value": {"title": "analist sportiv"},
                       "text": "Sunt analist sportiv", "persistence": "permanent"}),
    ("add_life_fact", {"type": "household_member", "value": {"role": "adult", "relation": "mama"},
                       "text": "Stă și mama la noi", "persistence": "temporary",
                       "valid_to": "2026-08-31"}),
    ("add_life_event", {"name": "Vacanță", "date": "2026-08-15", "est_cost": 3000,
                        "type": "trip"}),
    ("create_pot", {"name": "Vacanță august", "target": 3000, "deadline": "2026-08-15",
                    "kind": "event", "life_event_id": 42}),
    ("update_fixed_cost", {"fixed_cost_id": 3, "amount": 2400}),
    ("create_pattern_rule", {"kind": "classify",
                             "match": {"category": "restaurants", "weekdays": [5],
                                       "from": "12:00", "to": "15:00"},
                             "outcome": {"purpose": "social_connection",
                                         "label": "Prânz cu echipa"}}),
    ("create_pattern_rule", {"kind": "suppress", "match": {"category": "restaurants",
                                                           "amount_max": 30}, "outcome": {}}),
    ("simulate_plan", {"add_events": [{"name": "PS5", "date": "2026-11-20", "est_cost": 2500}]}),
    ("simulate_plan", {"target_daily_budget": 40}),
    ("shape_budget", {"weekday_weights": [{"weekday": 6, "weight": 1.5},
                                          {"weekday": 7, "weight": 1.5}]}),
    ("shape_budget", {"pin_days": [{"date": "2026-11-14", "amount": 150}]}),
    ("shape_budget", {"category_caps": [{"category": "food_delivery", "amount_per_week": 100}]}),
    ("shape_budget", {"category_caps": [{"category": "food_delivery", "amount_per_week": None}]}),
    ("shape_budget", {"buffer_pct": 0}),
    ("get_transactions", {"from": "2026-06-01", "to": "2026-06-15", "category": "groceries"}),
    ("set_goal", {"amount": 10000, "deadline": "2026-12-31", "motivation": "Fond de urgență"}),
    ("get_plan_status", {}),
]  # fmt: skip


@pytest.mark.parametrize(("name", "args"), TYPICAL_CALLS)
def test_the_typical_calls_validate(name: str, args: dict[str, Any]) -> None:
    Draft202012Validator(SCHEMAS[name]).validate(args)
    TOOL_SPECS[name].input_model.model_validate(args)


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("annotate_transaction", {"transaction_id": 0, "purpose": "x", "beneficiary": "self"}),
        ("shape_budget", {"buffer_pct": 0.5}),
        ("shape_budget", {"weekday_weights": [{"weekday": 8, "weight": 1}]}),
        ("add_life_event", {"name": "x", "date": "2026-08-15", "est_cost": -1, "type": "trip"}),
        ("show_quick_replies", {"options": []}),
    ],
)
def test_pydantic_still_checks_the_limits_the_schema_leaves_out(
    name: str, args: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        TOOL_SPECS[name].input_model.model_validate(args)
