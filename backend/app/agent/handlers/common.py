"""What every tool handler shares: the per-call context, the per-run state and small helpers (A3).

A handler is `async handler(ctx, run, args) -> dict`: `args` is the validated tool input
(`input_model.model_dump()`), and the dict is the JSON tool result Claude reads. `user_id` comes
only from `ctx` (the backend), never from `args` (arch 6.4 rule 1). A handler raises `DomainError`
for an expected failure; the executor turns it into an `is_error` result.

A handler may return two private keys the executor pops before serialising: `_plan_reason` (the
`plans.reason` text of the D18 recompute) and `_trigger_ref` (extra ids for `trigger_ref`).
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel

from app.agent.ports import ContextPort, EnginePort, LazyContext, LazyEngine, Row, Services
from app.domain.enums import Language
from app.domain.money import decimal_to_json
from app.errors import DomainError

PROACTIVE = "proactive"


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Who the call is for and what it may use; built by the agent loop per run."""

    user_id: int
    services: Services
    engine: EnginePort = field(default_factory=LazyEngine)
    context: ContextPort = field(default_factory=LazyContext)
    db: Any = None  # the unit of work's session, handed to the engine / context functions
    language: Language = Language.RO


@dataclass(slots=True)
class RunState:
    """What the tools of one agent run collect for the reply (A6 reads it after the loop)."""

    trigger: str = "chat"
    run_id: int | None = None
    quick_replies: list[str] = field(default_factory=list)
    action_cards: list[dict[str, Any]] = field(default_factory=list)
    pushes: list[tuple[str, dict[str, Any]]] = field(default_factory=list)  # WS, after commit
    plan_changed: bool = False
    plan: Any = None
    forecast: Any = None


Handler = Callable[[ToolContext, RunState, Mapping[str, Any]], Awaitable[dict[str, Any]]]


def to_jsonable(value: Any) -> Any:
    """`value` with models, Decimals, dates and enums turned into JSON values (money → number)."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, bool | int | float | str) or value is None:
        return value.value if isinstance(value, Enum) else value
    if isinstance(value, Decimal):
        return decimal_to_json(value)
    if isinstance(value, Enum):
        return to_jsonable(value.value)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(to_jsonable(k)): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [to_jsonable(v) for v in value]
    raise TypeError(f"not JSON-serialisable: {type(value).__name__}")


def pick(args: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    """The first of `names` present (and not None) in `args`: e.g. `from_date` / `from_`."""
    for name in names:
        if args.get(name) is not None:
            return args[name]
    return default


def changes(args: Mapping[str, Any], *skip: str) -> dict[str, Any]:
    """The fields Claude actually set (not None), minus the ids in `skip`."""
    return {k: v for k, v in args.items() if v is not None and k not in skip}


def need_changes(found: Mapping[str, Any], what: str) -> None:
    if not found:
        raise DomainError("nothing_to_change", f"Give at least one field to change on the {what}.")


def row_id(row: Row) -> int:
    value = row["id"]
    if not isinstance(value, int):
        raise TypeError("a row id must be an int")
    return value
