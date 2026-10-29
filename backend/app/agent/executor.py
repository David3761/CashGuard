"""The tool executor: one `tool_use` block in, one `tool_result` block out (A3; arch 6.4, 6.7).

The security rules (arch 6.4), in the order they apply:
1. **Whitelist.** Only a tool in the registry (A2's `TOOL_SPECS` x `handlers.registry.HANDLERS`)
   runs; the name is a dict key, never `getattr`/`eval`. Anything else → `unknown_tool`.
2. **Proactive runs are read-only** (D22, defence in depth behind A2's `tools_for`): only the
   `get_*` tools, `simulate_plan`, `suggest_savings_products`, `show_quick_replies` and
   `mark_event_handled` run; any other → `not_allowed_in_proactive`.
3. **`user_id` is injected** from `ctx`; an input carrying `user_id` is refused.
4. **Pydantic validation** with A2's input model → `invalid_input` with the fields and the
   reasons, so Claude can fix the call or ask the user (no input values are echoed).
5. `DomainError` → `is_error` with its code and message; any other exception → a generic
   `internal_error` (logged with its traceback): the agent loop always continues.
6. **D18:** after a successful money tool, `engine.recompute_plan(reason, trigger_ref)` and
   `engine.forecast_goal` run inside the same call, and the result carries `plan` + `forecast`
   (both include their previous values, so Claude can say "29.80 instead of 31.20").
7. **Every call is logged** through the `tool_calls` port (ok or error). A failing log never
   breaks the call.

The content of every `tool_result` is JSON: `{"ok": true, …}` or
`{"ok": false, "error": {"code", "message"}}` with `is_error: true`.

`execute_tool` and every handler are `async` (the ports are: bomboe's `AsyncSession` services,
danutu's async engine); the loop awaits one call at a time, in Claude's order.
"""

import importlib
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from typing import Any

from pydantic import BaseModel, ValidationError

from app.agent.handlers.common import PROACTIVE, Handler, RunState, ToolContext, to_jsonable
from app.errors import DomainError

log = logging.getLogger(__name__)

PROACTIVE_EXTRA_TOOLS = frozenset(
    {"simulate_plan", "suggest_savings_products", "show_quick_replies", "mark_event_handled"}
)
"""With every `get_*` tool, the only tools a proactive run may call (D22)."""

_INTERNAL_MESSAGE = "The tool failed on our side. Tell the user it didn't work; don't retry it."
_MAX_MESSAGE = 1000


@dataclass(frozen=True, slots=True)
class ToolEntry:
    """One whitelisted tool: its input model, its handler and its flags (from A2's spec)."""

    name: str
    input_model: type[BaseModel]
    handler: Handler
    money: bool = False
    write: bool = False


def allowed_in_proactive(name: str) -> bool:
    return name.startswith("get_") or name in PROACTIVE_EXTRA_TOOLS


def _flag(spec: Any, name: str) -> bool:
    """A spec flag, as `spec.flags.<name>`, `spec.flags[<name>]` or `spec.<name>`."""
    flags = getattr(spec, "flags", None)
    value = flags.get(name) if isinstance(flags, Mapping) else getattr(flags, name, None)
    return bool(getattr(spec, name, False) if value is None else value)


def build_registry(
    specs: Mapping[str, Any], handlers: Mapping[str, Handler]
) -> dict[str, ToolEntry]:
    """The whitelist: every spec that has a handler. A spec without one is logged and left out
    (Claude would get `unknown_tool`); a handler without a spec is never reachable."""
    registry: dict[str, ToolEntry] = {}
    for name, spec in specs.items():
        handler = handlers.get(name)
        if handler is None:
            log.warning("tool %s has a spec but no handler: not registered", name)
            continue
        registry[name] = ToolEntry(
            name=name,
            input_model=spec.input_model,
            handler=handler,
            money=_flag(spec, "money"),
            write=_flag(spec, "write"),
        )
    return registry


@cache
def default_registry() -> dict[str, ToolEntry]:
    """A2's `TOOL_SPECS` with this package's handlers (loaded on first use)."""
    specs = importlib.import_module("app.agent.tools").TOOL_SPECS
    from app.agent.handlers.registry import HANDLERS  # here: avoids an import cycle

    return build_registry(specs, HANDLERS)


def _block_parts(block: Any) -> tuple[str, str, Any]:
    if isinstance(block, Mapping):
        return str(block.get("id", "")), str(block.get("name", "")), block.get("input")
    return (
        str(getattr(block, "id", "")),
        str(getattr(block, "name", "")),
        getattr(block, "input", None),
    )


def _validation_message(error: ValidationError) -> str:
    parts = []
    for item in error.errors(include_url=False, include_input=False, include_context=False):
        where = ".".join(str(p) for p in item["loc"]) or "input"
        parts.append(f"{where}: {item['msg']}")
    return ("Invalid input. Fix these fields or ask the user: " + "; ".join(parts))[:_MAX_MESSAGE]


def _dumps(value: Any) -> str:
    return json.dumps(to_jsonable(value), ensure_ascii=False)


async def _log_call(
    ctx: ToolContext, run: RunState, tool_use_id: str, name: str, raw: Any, output: str, status: str
) -> None:
    try:
        tool_input = dict(raw) if isinstance(raw, Mapping) else {"_raw": repr(raw)[:200]}
        await ctx.services.tool_calls.log(
            ctx.user_id, run.run_id, tool_use_id, name[:64], tool_input, output, status
        )
    except Exception:
        log.exception("tool_calls.log failed for %s", name[:64])


async def _error(
    ctx: ToolContext, run: RunState, tool_use_id: str, name: str, raw: Any, code: str, message: str
) -> dict[str, Any]:
    content = _dumps({"ok": False, "error": {"code": code, "message": message[:_MAX_MESSAGE]}})
    await _log_call(ctx, run, tool_use_id, name, raw, content, "error")
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content, "is_error": True}


async def _recompute(
    ctx: ToolContext, run: RunState, name: str, tool_use_id: str, result: dict[str, Any]
) -> None:
    """D18: the new plan and forecast go into the same tool result."""
    reason = str(result.pop("_plan_reason", None) or name)
    trigger_ref = {"tool": name, "tool_use_id": tool_use_id, **result.pop("_trigger_ref", {})}
    plan = await ctx.engine.recompute_plan(ctx.db, ctx.user_id, reason, trigger_ref)
    forecast = await ctx.engine.forecast_goal(ctx.db, ctx.user_id, plan.version)
    result["plan"], result["forecast"] = plan, forecast
    run.plan_changed, run.plan, run.forecast = True, plan, forecast


async def execute_tool(
    ctx: ToolContext, run: RunState, block: Any, registry: Mapping[str, ToolEntry] | None = None
) -> dict[str, Any]:
    """Run one `tool_use` block for `ctx.user_id`; always returns a `tool_result` block."""
    tool_use_id, name, raw = _block_parts(block)
    entry = (default_registry() if registry is None else registry).get(name)
    if entry is None:
        message = f"Unknown tool {name[:64]!r}. Use only the tools offered in this run."
        return await _error(ctx, run, tool_use_id, name, raw, "unknown_tool", message)
    if run.trigger == PROACTIVE and not allowed_in_proactive(name):
        message = (
            f"{name} changes data, which a proactive run may not do. Suggest the change "
            "(simulate_plan can back it up); it happens when the user replies."
        )
        return await _error(ctx, run, tool_use_id, name, raw, "not_allowed_in_proactive", message)
    if not isinstance(raw, Mapping):
        return await _error(
            ctx, run, tool_use_id, name, raw, "invalid_input", "The input must be an object."
        )
    if "user_id" in raw:
        message = "Never pass user_id: the backend sets it. Call the tool again without it."
        return await _error(ctx, run, tool_use_id, name, raw, "invalid_input", message)
    try:
        args = entry.input_model.model_validate(dict(raw))
    except ValidationError as error:
        message = _validation_message(error)
        return await _error(ctx, run, tool_use_id, name, raw, "invalid_input", message)
    try:
        result = dict(await entry.handler(ctx, run, args.model_dump()))
        if entry.money:
            await _recompute(ctx, run, name, tool_use_id, result)
        result.pop("_plan_reason", None)
        result.pop("_trigger_ref", None)
        content = _dumps({"ok": True, **result})
    except DomainError as error:
        return await _error(ctx, run, tool_use_id, name, raw, error.code, error.message)
    except Exception:
        log.exception("tool %s failed", name)
        return await _error(ctx, run, tool_use_id, name, raw, "internal_error", _INTERNAL_MESSAGE)
    await _log_call(ctx, run, tool_use_id, name, raw, content, "ok")
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
