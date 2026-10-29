"""The agent's adapter over the merged pieces (D42; our side of B9 / B8).

`AgentWiring` implements the loop's `AgentServices` with:
- `setup`: the user's `UserContext` (B4's loader, injected) → A4 `render_snapshot` + A2
  `tools_for`, once per run (D46), plus the open question and the active pots;
- `execute_tool`: A3's executor with this run's `ToolContext` / `RunState`; the cards and the
  plan change A3 collects in `RunState` are copied into the result JSON the loop reads;
- `history` and `finish_run`: injected loaders (bomboe's messages / agent_runs services).

TODO(B4/B9): the real `load_context` / `load_history` / `record_run` come from bomboe's
services; until then the tests pass in-memory ones.
"""

import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from anthropic.types.beta import BetaMessageParam, BetaToolResultBlockParam, BetaToolUseBlock

from app.agent.executor import ToolEntry, execute_tool
from app.agent.fallbacks import OpenQuestion, PotRef
from app.agent.handlers.common import RunState, ToolContext
from app.agent.loop import RunSetup, RunStatus
from app.agent.snapshot import render_snapshot
from app.agent.tools import ToolState, tools_for
from app.domain.enums import AgentEventStatus, AgentEventType
from app.domain.user_context import UserContext

LoadContext = Callable[[int], Awaitable[UserContext]]
LoadHistory = Callable[[int, int], Awaitable[list[BetaMessageParam]]]
RecordRun = Callable[[int | None, RunStatus, str | None], Awaitable[None]]


def _open_question(ctx: UserContext, event_id: int | None) -> OpenQuestion | None:
    """The asked (or, for a proactive run, this) transaction question and its transaction."""
    questions = [
        e
        for e in ctx.agent_events
        if e.type == AgentEventType.TRANSACTION_QUESTION
        and e.ref_transaction_id is not None
        and (e.id == event_id or e.status == AgentEventStatus.ASKED)
    ]
    if not questions:
        return None
    event = max(questions, key=lambda e: (e.id == event_id, e.id))
    tx = next((t for t in ctx.transactions if t.id == event.ref_transaction_id), None)
    if tx is None:
        return None
    return OpenQuestion(
        transaction_id=tx.id,
        amount=Decimal(tx.amount),
        merchant=tx.merchant or tx.merchant_raw,
        category=str(tx.category) if tx.category else "other",
        merchant_id=tx.merchant_id,
        agent_event_id=event.id,
        ask_what_item=bool(event.payload.get("ask_what_item")),
    )


@dataclass
class AgentWiring:
    """`AgentServices` over A2/A3/A4 (one instance per process; runs keyed by user)."""

    load_context: LoadContext
    tool_context: Callable[[int], ToolContext]
    load_history: LoadHistory
    record_run: RecordRun | None = None
    registry: Mapping[str, ToolEntry] | None = None  # None: A3's default registry
    _runs: dict[int, RunState] = field(default_factory=dict)

    async def setup(self, user_id: int, trigger: str, event_id: int | None) -> RunSetup:
        ctx = await self.load_context(user_id)
        event = next((e for e in ctx.agent_events if e.id == event_id), None)
        self._runs[user_id] = RunState(trigger=trigger)
        return RunSetup(
            language=str(ctx.profile.language),
            snapshot=render_snapshot(ctx, trigger, event, ctx.profile.language),
            tools=tools_for(ToolState(has_active_goal=ctx.goal is not None), trigger),
            open_question=_open_question(ctx, event_id),
            pots=tuple(PotRef(p.id, p.name) for p in ctx.pots),
        )

    async def history(self, user_id: int, limit: int) -> list[BetaMessageParam]:
        return (await self.load_history(user_id, limit))[-limit:]

    async def execute_tool(
        self, user_id: int, run_id: int | None, block: BetaToolUseBlock
    ) -> BetaToolResultBlockParam:
        run = self._runs.setdefault(user_id, RunState())
        run.run_id = run_id
        cards_before = len(run.action_cards)
        plan_before = run.plan_changed
        result = execute_tool(self.tool_context(user_id), run, block, self.registry)
        content = result.get("content")
        out: BetaToolResultBlockParam = {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": content if isinstance(content, str) else json.dumps(content, default=str),
        }
        if result.get("is_error"):
            out["is_error"] = True
            return out
        data = _json(out["content"])
        if len(run.action_cards) > cards_before:
            data["action_card"] = run.action_cards[-1]
        if run.plan_changed and not plan_before:
            data.setdefault("plan", True)
        out["content"] = json.dumps(data, default=str)
        return out

    async def finish_run(self, run_id: int | None, status: RunStatus, reason: str | None) -> None:
        if self.record_run is not None:
            await self.record_run(run_id, status, reason)


def _json(content: object) -> dict[str, Any]:
    try:
        data = json.loads(content) if isinstance(content, str) else None
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}
