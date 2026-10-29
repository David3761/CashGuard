"""A3 step 1: the tool executor's security rules and the D18 recompute (arch 6.4, 6.7)."""

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

from app.agent.executor import ToolEntry, allowed_in_proactive, build_registry, execute_tool
from app.agent.handlers.common import RunState, ToolContext
from app.errors import DomainError
from tests.fakes.fake_services import FakeToolCalls, Harness


class NoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: float = Field(gt=0)


async def _ok(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    return {"user_id_seen": ctx.user_id, "args": dict(args)}


async def _domain_error(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    raise DomainError("goal_already_active", "A goal is already active: use update_goal.")


async def _boom(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    raise RuntimeError("db exploded with secret details")


@dataclass(frozen=True)
class Flags:
    money: bool = False
    write: bool = False
    read_only: bool = False


@dataclass(frozen=True)
class Spec:
    input_model: type[BaseModel]
    description: str = "test"
    flags: Flags = field(default_factory=Flags)


SPECS = {
    "get_plan_status": Spec(NoInput, flags=Flags(read_only=True)),
    "set_goal": Spec(GoalIn, flags=Flags(money=True, write=True)),
    "update_life_profile": Spec(NoInput, flags=Flags(write=True)),
    "fails_domain": Spec(NoInput, flags=Flags(write=True)),
    "fails_boom": Spec(NoInput, flags=Flags(write=True)),
    "spec_without_handler": Spec(NoInput),
}
HANDLERS = {
    "get_plan_status": _ok,
    "set_goal": _ok,
    "update_life_profile": _ok,
    "fails_domain": _domain_error,
    "fails_boom": _boom,
    "handler_without_spec": _ok,
}
REGISTRY = build_registry(SPECS, HANDLERS)


def _block(name: str, tool_input: object, tool_use_id: str = "toolu_1") -> dict[str, Any]:
    return {"type": "tool_use", "id": tool_use_id, "name": name, "input": tool_input}


async def _run(h: Harness, name: str, tool_input: object) -> tuple[dict[str, Any], dict[str, Any]]:
    out = await execute_tool(h.ctx, h.run, _block(name, tool_input), REGISTRY)
    return out, json.loads(out["content"])


def _log(h: Harness) -> FakeToolCalls:
    calls = h.services.tool_calls
    assert isinstance(calls, FakeToolCalls)
    return calls


def test_registry_is_the_specs_that_have_a_handler() -> None:
    assert set(REGISTRY) == {
        "get_plan_status",
        "set_goal",
        "update_life_profile",
        "fails_domain",
        "fails_boom",
    }
    assert REGISTRY["set_goal"] == ToolEntry("set_goal", GoalIn, _ok, money=True, write=True)


async def test_happy_call_injects_user_id_and_returns_a_json_tool_result() -> None:
    h = Harness(user_id=42)
    out, body = await _run(h, "get_plan_status", {})
    assert out == {"type": "tool_result", "tool_use_id": "toolu_1", "content": out["content"]}
    assert body == {"ok": True, "user_id_seen": 42, "args": {}}
    assert "plan" not in body  # not a money tool


@pytest.mark.parametrize("name", ["drop_tables", "spec_without_handler", "handler_without_spec"])
async def test_unknown_tool_is_an_error(name: str) -> None:
    h = Harness()
    out, body = await _run(h, name, {})
    assert out["is_error"] is True
    assert body["error"]["code"] == "unknown_tool"


async def test_invalid_input_names_the_field_without_echoing_the_value() -> None:
    h = Harness()
    out, body = await _run(h, "set_goal", {"amount": -5})
    assert out["is_error"] is True
    assert body["error"]["code"] == "invalid_input"
    assert "amount" in body["error"]["message"]
    assert "-5" not in body["error"]["message"]
    assert h.engine.calls == []  # nothing recomputed


@pytest.mark.parametrize("tool_input", [None, [1, 2], "x"])
async def test_non_object_input_is_an_error(tool_input: object) -> None:
    _, body = await _run(Harness(), "get_plan_status", tool_input)
    assert body["error"]["code"] == "invalid_input"


async def test_user_id_in_the_input_is_refused() -> None:
    h = Harness(user_id=1)
    out, body = await _run(h, "set_goal", {"amount": 100, "user_id": 2})
    assert out["is_error"] is True
    assert body["error"]["code"] == "invalid_input"
    assert "user_id" in body["error"]["message"]


@pytest.mark.parametrize("name", ["set_goal", "update_life_profile"])
async def test_a_write_tool_in_a_proactive_run_is_refused(name: str) -> None:
    h = Harness(trigger="proactive")
    out, body = await _run(h, name, {"amount": 100} if name == "set_goal" else {})
    assert out["is_error"] is True
    assert body["error"]["code"] == "not_allowed_in_proactive"
    assert h.engine.calls == []


async def test_a_read_tool_in_a_proactive_run_works() -> None:
    _, body = await _run(Harness(trigger="proactive"), "get_plan_status", {})
    assert body["ok"] is True


def test_proactive_whitelist_is_d22() -> None:
    for name in ("get_transactions", "get_goal_forecast", "simulate_plan", "show_quick_replies"):
        assert allowed_in_proactive(name)
    for name in ("annotate_transaction", "set_goal", "transfer_to_savings", "add_life_fact"):
        assert not allowed_in_proactive(name)


async def test_domain_error_becomes_is_error_with_its_code() -> None:
    out, body = await _run(Harness(), "fails_domain", {})
    assert out["is_error"] is True
    assert body["error"] == {
        "code": "goal_already_active",
        "message": "A goal is already active: use update_goal.",
    }


async def test_unexpected_exception_is_generic_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    h = Harness()
    with caplog.at_level(logging.ERROR, logger="app.agent.executor"):
        out, body = await _run(h, "fails_boom", {})
    assert out["is_error"] is True
    assert body["error"]["code"] == "internal_error"
    assert "secret" not in out["content"]
    assert any("fails_boom" in r.getMessage() and r.exc_info for r in caplog.records)
    # the loop keeps going: the next call works
    assert (await _run(h, "get_plan_status", {}))[1]["ok"] is True


async def test_money_tool_result_has_plan_and_forecast_with_previous_values() -> None:
    h = Harness()
    out, body = await _run(h, "set_goal", {"amount": 10000})
    assert "is_error" not in out
    assert body["plan"] == {
        "version": 8,
        "feasible": True,
        "today_budget": 29.8,
        "previous_today_budget": 31.2,
        "next_7_days": [],
        "reason": "set_goal",
    }
    assert body["forecast"]["probability"] == 0.77
    assert body["forecast"]["previous_probability"] == 0.71
    assert h.engine.names() == ["recompute_plan", "forecast_goal"]
    _, (_, _, trigger_ref) = h.engine.calls[0]
    assert trigger_ref == {"tool": "set_goal", "tool_use_id": "toolu_1"}
    assert h.engine.calls[1] == ("forecast_goal", (1, 8))
    assert h.run.plan_changed is True


async def test_a_money_tool_without_a_plan_is_not_an_error() -> None:
    # danutu's recompute_plan returns None while there is no goal (E4): nothing to forecast.
    h = Harness()
    h.engine.no_plan = True
    out, body = await _run(h, "set_goal", {"amount": 10000})
    assert "is_error" not in out
    assert (body["ok"], body["plan"], body["forecast"]) == (True, None, None)
    assert h.engine.names() == ["recompute_plan"]
    assert h.run.plan_changed is False


async def test_every_call_is_logged_ok_or_error() -> None:
    h = Harness()
    await _run(h, "get_plan_status", {})
    await _run(h, "nope", {})
    await _run(h, "set_goal", {"amount": 0})
    await _run(h, "fails_boom", {})
    rows = _log(h).rows
    assert [(r["tool_name"], r["status"]) for r in rows] == [
        ("get_plan_status", "ok"),
        ("nope", "error"),
        ("set_goal", "error"),
        ("fails_boom", "error"),
    ]
    assert all(r["user_id"] == 1 and r["run_id"] == 55 for r in rows)


async def test_a_failing_log_does_not_break_the_call() -> None:
    h = Harness()

    async def broken_log(*args: object) -> None:
        raise RuntimeError("log down")

    _log(h).log = broken_log  # type: ignore[method-assign,assignment]
    assert (await _run(h, "get_plan_status", {}))[1]["ok"] is True


async def test_sdk_style_block_objects_work() -> None:
    @dataclass
    class Block:
        id: str
        name: str
        input: dict[str, Any]

    h = Harness()
    out = await execute_tool(h.ctx, h.run, Block("toolu_9", "get_plan_status", {}), REGISTRY)
    assert out["tool_use_id"] == "toolu_9"
    assert json.loads(out["content"])["ok"] is True
