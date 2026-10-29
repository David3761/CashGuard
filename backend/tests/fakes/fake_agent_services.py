"""`FakeAgentServices`: an in-memory stand-in for the agent's ports (loop + proactive).

It holds Scene A's state (Matei, tx 918: 500 lei at Mega Image) and a tiny executor whose
`annotate_transaction` does what A3's handler does for a split: effective = amount / people,
a receivable for the others' share. Every call is recorded. TODO(A3): swap the tiny executor for
A3's `execute_tool` over fake services once it lands.
"""

import itertools
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from anthropic.types.beta import (
    BetaMessageParam,
    BetaToolParam,
    BetaToolResultBlockParam,
    BetaToolUseBlock,
)

from app.agent.fallbacks import OpenQuestion, PotRef
from app.agent.loop import RunSetup, RunStatus

SNAPSHOT = "SNAPSHOT: Matei, goal 10.000 lei, OPEN QUESTION [tx 918] Mega Image 500 lei"

CHAT_TOOLS = (
    "get_plan_status",
    "get_transaction",
    "annotate_transaction",
    "offer_payment_request",
    "link_transaction_to_pot",
    "create_pattern_rule",
    "show_quick_replies",
    "set_goal",
)
PROACTIVE_TOOLS = ("get_plan_status", "get_transaction", "show_quick_replies", "mark_event_handled")


def tool_spec(name: str) -> BetaToolParam:
    return {
        "name": name,
        "description": f"{name} (fake)",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    }


def scene_a_question(*, merchant: str = "Mega Image", ask_what_item: bool = False) -> OpenQuestion:
    return OpenQuestion(
        transaction_id=918,
        amount=Decimal(500),
        merchant=merchant,
        category="groceries",
        merchant_id="mega_image",
        agent_event_id=77,
        ask_what_item=ask_what_item,
    )


@dataclass
class Tx:
    amount: Decimal
    effective_amount: Decimal
    purpose: str | None = None
    beneficiary: str | None = None
    pot_id: int | None = None


class ToolFailure(Exception):
    """What a handler raises for a domain error (→ is_error)."""


@dataclass
class FakeAgentServices:
    language: str = "ro"
    open_question: OpenQuestion | None = field(default_factory=scene_a_question)
    pots: Sequence[PotRef] = ()
    tool_names: Sequence[str] = CHAT_TOOLS
    stored_history: list[BetaMessageParam] = field(default_factory=list)

    # state
    transactions: dict[int, Tx] = field(
        default_factory=lambda: {918: Tx(Decimal(500), Decimal(500))}
    )
    receivables: dict[int, dict[str, Any]] = field(default_factory=dict)
    rules: list[dict[str, Any]] = field(default_factory=list)
    # records
    setup_calls: list[tuple[int, str, int | None]] = field(default_factory=list)
    history_limits: list[int] = field(default_factory=list)
    executed: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    runs: list[tuple[int | None, RunStatus, str | None]] = field(default_factory=list)
    overrides: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = field(default_factory=dict)
    _ids: "itertools.count[int]" = field(default_factory=lambda: itertools.count(9))

    # ── AgentServices ──
    async def setup(self, user_id: int, trigger: str, event_id: int | None) -> RunSetup:
        self.setup_calls.append((user_id, trigger, event_id))
        names = PROACTIVE_TOOLS if trigger == "proactive" else self.tool_names
        return RunSetup(
            language=self.language,
            snapshot=SNAPSHOT,
            tools=[tool_spec(name) for name in names],
            open_question=self.open_question,
            pots=self.pots,
        )

    async def history(self, user_id: int, limit: int) -> list[BetaMessageParam]:
        self.history_limits.append(limit)
        return list(self.stored_history[-limit:])

    async def execute_tool(
        self, user_id: int, run_id: int | None, block: BetaToolUseBlock
    ) -> BetaToolResultBlockParam:
        args = dict(block.input) if isinstance(block.input, dict) else {}
        self.executed.append((block.name, args))
        handler = self.overrides.get(block.name) or getattr(self, f"_h_{block.name}", None)
        try:
            if handler is None:
                raise ToolFailure(f"unknown tool {block.name}")
            data = handler(args)
        except (ToolFailure, KeyError, ValueError) as err:
            return {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(err),
                "is_error": True,
            }
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": json.dumps(data, default=str),
        }

    async def finish_run(self, run_id: int | None, status: RunStatus, reason: str | None) -> None:
        self.runs.append((run_id, status, reason))

    # ── tiny handlers (the D18 "plan" key marks a money tool) ──
    def _h_get_plan_status(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"daily_budget": "45.00"}

    def _h_get_transaction(self, args: dict[str, Any]) -> dict[str, Any]:
        tx = self.transactions[int(args["transaction_id"])]
        return {"amount": tx.amount, "effective_amount": tx.effective_amount}

    def _h_show_quick_replies(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    def _h_set_goal(self, args: dict[str, Any]) -> dict[str, Any]:
        if "amount" not in args:
            raise ToolFailure("amount: field required")
        return {"ok": True, "plan": {"daily_budget": "40.00"}}

    def _h_annotate_transaction(self, args: dict[str, Any]) -> dict[str, Any]:
        tx = self.transactions[int(args["transaction_id"])]
        people = int(args.get("people_count") or 1)
        share = (tx.amount / people).quantize(Decimal("0.01"))
        tx.effective_amount, tx.purpose, tx.beneficiary = (
            share,
            args["purpose"],
            args["beneficiary"],
        )
        data: dict[str, Any] = {"effective_amount": share, "plan": {"daily_budget": "47.00"}}
        if args.get("others_will_repay") and people > 1:
            rcv_id = next(self._ids)
            owed = tx.amount - share
            self.receivables[rcv_id] = {"amount": owed, "debtor_label": args.get("debtor_label")}
            data["receivable"] = {"id": rcv_id, "amount": owed}
        return data

    def _h_offer_payment_request(self, args: dict[str, Any]) -> dict[str, Any]:
        rcv_id = int(args["receivable_id"])
        if rcv_id not in self.receivables:
            raise ToolFailure(f"no receivable {rcv_id}")
        card = {
            "type": "request_payment",
            "receivable_id": rcv_id,
            "label": "Trimite cererea (4 \u00d7 100 lei)",
        }
        return {"ok": True, "action_card": card}

    def _h_link_transaction_to_pot(self, args: dict[str, Any]) -> dict[str, Any]:
        tx = self.transactions[int(args["transaction_id"])]
        tx.pot_id = int(args["pot_id"])
        return {"ok": True, "plan": {"daily_budget": "47.00"}}

    def _h_create_pattern_rule(self, args: dict[str, Any]) -> dict[str, Any]:
        self.rules.append(args)
        return {"rule_id": len(self.rules)}

    def state(self) -> dict[str, Any]:
        """Comparable end state (A9: the chips path == the LLM path)."""
        return {
            "transactions": {k: vars(v).copy() for k, v in self.transactions.items()},
            "receivables": [dict(v) for v in self.receivables.values()],
            "rules": list(self.rules),
        }
