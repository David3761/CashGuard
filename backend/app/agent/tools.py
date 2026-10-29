"""The agent's tools (A2): one input model per arch 6.6 tool, the registry and `tools_for`.

- Every tool takes ids, never names, and **never a `user_id`** (arch 6.4 rule 1): the executor
  (A3) injects it. Each input model is frozen with `extra="forbid"`, so the executor's Pydantic
  validation (arch 6.4 rule 3) rejects a smuggled key.
- `tool_param(name, strict)` turns a model into the plain dict `LLM.create` sends (no
  `cache_control`: the wrapper owns it). The JSON schema keeps only what strict tool use accepts:
  `$ref`s are inlined, `additionalProperties: false` is on every object, an optional field is
  simply not `required` (no `null` branch, so it isn't a union), and the numeric / length limits
  are dropped from the schema (the API rejects them) but still checked by Pydantic.
- **Strict budget.** The API allows at most 20 strict tools, 24 optional parameters and 16 union
  parameters per request (structured-outputs limits, checked 2026-10-29), and arch 6.6 has 40
  tools. So `tools_for` marks tools strict in `STRICT_PRIORITY` order while they fit the budget;
  the rest are sent without `strict` (same schema; the executor's Pydantic check still runs).
- `tools_for(state, trigger)` is computed **once per run** (D46): `set_goal` only without an
  active goal, `update_goal` only with one (D21); a proactive run gets exactly the D22 read-only
  set. The order is `TOOL_SPECS` order, so the tool block is byte-stable (prompt caching, 6.8).

The handlers live in `app/agent/handlers/` and the executor in `app/agent/executor.py` (A3).
"""

import copy
import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated, Any, Final

from anthropic.types.beta import BetaToolParam
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.domain.enums import (
    Beneficiary,
    Category,
    FactType,
    LifeEventType,
    Persistence,
    PotKind,
    Purpose,
    RuleKind,
    SignatureEffect,
)
from app.domain.models import FactValue
from app.domain.money import Money

JsonSchema = dict[str, Any]

# ── shared field types ──────────────────────────────────────────────────────────────────────
# The limits are Pydantic's (the executor's check); the schema sent to Claude drops them.
Id = Annotated[int, Field(gt=0, description="An id printed in the snapshot, e.g. [tx 918].")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
PositiveMoney = Annotated[Money, Field(gt=0, description="Lei, e.g. 120.5.")]
NonNegMoney = Annotated[Money, Field(ge=0, description="Lei, e.g. 120.5.")]
DayOfMonth = Annotated[int, Field(ge=1, le=31, description="1-31.")]
Weekday = Annotated[int, Field(ge=1, le=7, description="ISO weekday: Monday = 1 ... Sunday = 7.")]
HourMinute = Annotated[str, StringConstraints(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]
Weight = Annotated[float, Field(ge=0.5, le=3, description="0.5-3; 1 = a normal day.")]
BufferPct = Annotated[float, Field(ge=0, le=0.3, description="0-0.3; the default is 0.10.")]


class ToolInput(BaseModel):
    """The base of every tool input: immutable, unknown keys rejected (no smuggled `user_id`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class NoInput(ToolInput):
    """A tool without parameters."""


# ── reads (arch 6.6) ────────────────────────────────────────────────────────────────────────


class GetTransactionsIn(ToolInput):
    from_: dt.date = Field(alias="from", description="First day, YYYY-MM-DD.")
    to: dt.date = Field(description="Last day (inclusive), YYYY-MM-DD.")
    category: Category | None = None


class GetSpendingSummaryIn(ToolInput):
    period_days: int = Field(ge=1, le=180, description="How many days back, 1-180.")


class GetTransactionIn(ToolInput):
    transaction_id: Id


class ShowQuickRepliesIn(ToolInput):
    options: tuple[Annotated[str, StringConstraints(min_length=1, max_length=40)], ...] = Field(
        min_length=1, max_length=4, description="1-4 short reply buttons, in the user's language."
    )


class MarkEventHandledIn(ToolInput):
    event_id: int = Field(gt=0, description="The N of a pending [agent_event N] in the snapshot.")


class AddEvent(ToolInput):
    name: Text
    date: dt.date
    est_cost: NonNegMoney


class DayAmount(ToolInput):
    date: dt.date
    amount: NonNegMoney


class WeekdayWeight(ToolInput):
    weekday: Weekday
    weight: Weight


class SimulatePlanIn(ToolInput):
    """D20: every field optional; nothing is saved."""

    goal_amount: PositiveMoney | None = None
    deadline: dt.date | None = None
    add_events: tuple[AddEvent, ...] = ()
    remove_event_ids: tuple[Id, ...] = ()
    income_delta: Money | None = Field(None, description="Monthly change in lei, + or -.")
    fixed_cost_delta: Money | None = Field(None, description="Monthly change in lei, + or -.")
    weekday_weights: tuple[WeekdayWeight, ...] = ()
    pin_days: tuple[DayAmount, ...] = ()
    buffer_pct: BufferPct | None = None
    target_daily_budget: PositiveMoney | None = Field(
        None, description="Solve mode: the daily budget the user wants."
    )


# ── goal, events, income, fixed costs ───────────────────────────────────────────────────────


class SetGoalIn(ToolInput):
    amount: PositiveMoney
    deadline: dt.date
    motivation: LongText | None = None


class UpdateGoalIn(ToolInput):
    amount: PositiveMoney | None = None
    deadline: dt.date | None = None
    motivation: LongText | None = None


class AddLifeEventIn(ToolInput):
    name: Text
    date: dt.date
    est_cost: NonNegMoney
    type: LifeEventType


class UpdateLifeEventIn(ToolInput):
    event_id: int = Field(gt=0, description="The N of a planned [event N] in the snapshot.")
    name: Text | None = None
    date: dt.date | None = None
    est_cost: NonNegMoney | None = None
    type: LifeEventType | None = None


class LifeEventIdIn(ToolInput):
    event_id: int = Field(gt=0, description="The N of a planned [event N] in the snapshot.")


class AddIncomeSourceIn(ToolInput):
    source: Text
    amount: PositiveMoney
    day_of_month: DayOfMonth


class UpdateIncomeSourceIn(ToolInput):
    income_source_id: Id
    source: Text | None = None
    amount: PositiveMoney | None = None
    day_of_month: DayOfMonth | None = None


class IncomeSourceIdIn(ToolInput):
    income_source_id: Id


class AddFixedCostIn(ToolInput):
    name: Text
    amount: PositiveMoney
    day_of_month: DayOfMonth


class UpdateFixedCostIn(ToolInput):
    fixed_cost_id: Id
    name: Text | None = None
    amount: PositiveMoney | None = None
    day_of_month: DayOfMonth | None = None


class FixedCostIdIn(ToolInput):
    fixed_cost_id: Id


# ── shaping, slips, reflections, profile, savings ───────────────────────────────────────────


class RecordSlipReasonIn(ToolInput):
    date: dt.date
    reason: Text
    detail: LongText | None = None
    recurring: bool = Field(description="True when it happens every week on this weekday.")


class CategoryCap(ToolInput):
    category: Category
    amount_per_week: NonNegMoney | None = Field(description="Lei per week; null removes the cap.")


class ShapeBudgetIn(ToolInput):
    weekday_weights: tuple[WeekdayWeight, ...] = ()
    pin_days: tuple[DayAmount, ...] = ()
    unpin_days: tuple[dt.date, ...] = ()
    category_caps: tuple[CategoryCap, ...] = ()
    buffer_pct: BufferPct | None = None


class RecordReflectionIn(ToolInput):
    motivation: int = Field(ge=1, le=5, description="1-5: how motivated the user feels.")
    answer: LongText
    reason: LongText | None = None


class UpdateLifeProfileIn(ToolInput):
    key: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$")] = Field(
        description="A snake_case note key, e.g. what_works."
    )
    value: LongText


class TransferToSavingsIn(ToolInput):
    amount: PositiveMoney


# ── transactions & receivables ──────────────────────────────────────────────────────────────


class AnnotateTransactionIn(ToolInput):
    transaction_id: Id
    purpose: Purpose
    beneficiary: Beneficiary
    own_amount: NonNegMoney | None = Field(
        None, description="The user's own part in lei, if they said it (wins over people_count)."
    )
    people_count: int | None = Field(None, ge=1, le=100, description="People paid for, incl. user.")
    others_will_repay: bool | None = None
    debtor_label: Text | None = Field(None, description="Who owes, in the user's words: colegi.")
    note: LongText | None = None


class CreateReceivableIn(ToolInput):
    debtor_label: Text
    amount: PositiveMoney | None = None
    transaction_id: Id | None = None
    people_count: int | None = Field(None, ge=1, le=100)
    expected_by: dt.date | None = None


class ReceivableIdIn(ToolInput):
    receivable_id: Id


# ── life facts & rules ──────────────────────────────────────────────────────────────────────
# `value` is validated with F2's per-type value models (`LifeFact.value`'s union); A3's handler
# checks that it matches `type` with `FACT_VALUE_MODELS` (it builds the `LifeFactDraft`).


class SignatureDraft(ToolInput):
    """What a fact predicts about spending (arch 5.3.3); C4 validates it with F2's `Signature`."""

    effect: SignatureEffect
    purpose: Purpose
    category: Category | None = None
    merchant_hints: tuple[Text, ...] = ()
    item_keywords: tuple[Text, ...] = ()
    amount_min: NonNegMoney | None = None
    amount_max: NonNegMoney | None = None


class AddLifeFactIn(ToolInput):
    type: FactType
    value: FactValue = Field(description="The value object for this fact type.")
    text: LongText = Field(description="One line in the user's words, e.g. Sunt analist sportiv.")
    persistence: Persistence
    valid_from: dt.date | None = None
    valid_to: dt.date | None = Field(None, description="Needed when persistence is temporary.")
    signatures: tuple[SignatureDraft, ...] = ()


class UpdateLifeFactIn(ToolInput):
    fact_id: Id
    value: FactValue | None = None
    text: LongText | None = None
    persistence: Persistence | None = None
    valid_to: dt.date | None = None


class ExpireLifeFactIn(ToolInput):
    fact_id: Id
    valid_to: dt.date | None = Field(None, description="The last day it held; default today.")


class ConfirmHypothesisIn(ToolInput):
    fact_id: Id
    accepted: bool


class RuleMatchIn(ToolInput):
    """The `match` Claude sends; A3 validates it into F2's `RuleMatch` (times as "HH:MM" strings
    here: the schema's `format: time` would ask for seconds and a zone)."""

    category: Category | None = None
    merchant_id: Annotated[str, StringConstraints(max_length=40)] | None = None
    weekdays: tuple[Weekday, ...] = ()
    from_: HourMinute | None = Field(None, alias="from", description="HH:MM, with to.")
    to: HourMinute | None = Field(None, description="HH:MM, with from.")
    amount_min: NonNegMoney | None = None
    amount_max: NonNegMoney | None = None


class RuleOutcomeIn(ToolInput):
    purpose: Purpose | None = Field(None, description="Needed for a classify rule.")
    label: Text | None = Field(None, description="Shown in the feed, e.g. Prânz cu echipa.")


class CreatePatternRuleIn(ToolInput):
    kind: RuleKind
    match: RuleMatchIn
    outcome: RuleOutcomeIn


# ── pots ────────────────────────────────────────────────────────────────────────────────────


class CreatePotIn(ToolInput):
    name: Text
    target: PositiveMoney
    deadline: dt.date | None = None
    kind: PotKind
    life_event_id: Id | None = None


class UpdatePotIn(ToolInput):
    pot_id: Id
    name: Text | None = None
    target: PositiveMoney | None = None
    deadline: dt.date | None = None


class PotIdIn(ToolInput):
    pot_id: Id


class LinkTransactionToPotIn(ToolInput):
    transaction_id: Id
    pot_id: Id


# ── the registry ────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ToolFlags:
    """money: recompute plan + forecast after it (arch 6.7 MONEY_TOOLS, D18). write: changes the
    user's data, so never in a proactive run (D22). read_only = not write: the D22 set."""

    money: bool = False
    write: bool = False

    @property
    def read_only(self) -> bool:
        return not self.write


@dataclass(frozen=True, slots=True)
class ToolSpec:
    input_model: type[ToolInput]
    description: str
    flags: ToolFlags


READ: Final = ToolFlags()
WRITE: Final = ToolFlags(write=True)
MONEY: Final = ToolFlags(money=True, write=True)


def _spec(model: type[ToolInput], flags: ToolFlags, description: str) -> ToolSpec:
    return ToolSpec(input_model=model, description=description, flags=flags)


TOOL_SPECS: Final[Mapping[str, ToolSpec]] = MappingProxyType(
    {
        # reads (D22: the only tools of a proactive run)
        "get_transactions": _spec(
            GetTransactionsIn,
            READ,
            "List the user's transactions between two dates, optionally for one category. "
            "Use it when the user asks about spending older than the snapshot's 14 days or "
            "wants a list.",
        ),
        "get_transaction": _spec(
            GetTransactionIn,
            READ,
            "Read one transaction with its annotation, scores and matched fact or rule. Use"
            " it when you need details of a transaction id that the snapshot shows only "
            "briefly.",
        ),
        "get_spending_summary": _spec(
            GetSpendingSummaryIn,
            READ,
            "Spending totals per category for the last N days. Use it when the user asks "
            "how much they spent on something over a period, instead of adding numbers "
            "yourself.",
        ),
        "get_plan_status": _spec(
            NoInput,
            READ,
            "The current plan: today's budget, feasibility and the next 7 days. Use it when"
            " the user asks how much they can spend and the snapshot's plan may be "
            "outdated.",
        ),
        "get_goal_forecast": _spec(
            NoInput,
            READ,
            "The goal forecast: probability now and last week, P10-P90, drivers and "
            "options. Use it when the user asks whether they will reach the goal or what "
            "changed.",
        ),
        "simulate_plan": _spec(
            SimulatePlanIn,
            READ,
            "What-if: recompute the plan with changes, saving nothing. Use it for every "
            "'what if' or 'can I afford' question and to compare options before proposing "
            "one; with target_daily_budget it solves for the deadline or goal that gives "
            "that budget.",
        ),
        "suggest_savings_products": _spec(
            NoInput,
            READ,
            "Savings products ranked for this person, each with a one-line reason. Use it "
            "when the user asks where to keep their savings or which product fits them.",
        ),
        "show_quick_replies": _spec(
            ShowQuickRepliesIn,
            READ,
            "Attach up to 4 reply buttons to your message. Use it when the user can answer "
            "with a short choice, e.g. a follow-up like 'Was your part about 100 lei? [Yes]"
            " [Other]'.",
        ),
        "mark_event_handled": _spec(
            MarkEventHandledIn,
            READ,
            "Mark a pending agent event as handled. Use it after you have brought up the "
            "event from the snapshot's pending events, so it isn't raised again.",
        ),
        # goal (D21: exactly one of the two is offered)
        "set_goal": _spec(
            SetGoalIn,
            MONEY,
            "Create the user's savings goal. Use it when there is no active goal and the "
            "user states an amount and a deadline (onboarding, or after a goal was "
            "completed).",
        ),
        "update_goal": _spec(
            UpdateGoalIn,
            MONEY,
            "Change the active goal's amount, deadline or motivation. Use it when the user "
            "wants to move the deadline or change the target, after comparing with "
            "simulate_plan.",
        ),
        # life events
        "add_life_event": _spec(
            AddLifeEventIn,
            MONEY,
            "Save a planned event that will cost money before the goal deadline (trip, "
            "gift, concert, big purchase). Use it whenever the user mentions a future plan "
            "with a cost; if the cost is unknown, ask the user before calling.",
        ),
        "update_life_event": _spec(
            UpdateLifeEventIn,
            MONEY,
            "Change a planned event's name, date, cost or type. Use it when the user "
            "corrects an event the snapshot lists with its id.",
        ),
        "cancel_life_event": _spec(
            LifeEventIdIn,
            MONEY,
            "Cancel a planned event. Use it when the user says an event from the snapshot "
            "is off or won't cost anything any more.",
        ),
        # income & fixed costs
        "add_income_source": _spec(
            AddIncomeSourceIn,
            MONEY,
            "Add a regular income (salary, scholarship, rent received) with its monthly "
            "amount and day. Use it when the user mentions an income the snapshot doesn't "
            "list.",
        ),
        "update_income_source": _spec(
            UpdateIncomeSourceIn,
            MONEY,
            "Change an income's amount, day or name. Use it when the user says their salary"
            " changed or moved to another day.",
        ),
        "remove_income_source": _spec(
            IncomeSourceIdIn,
            MONEY,
            "Remove an income. Use it when the user says an income from the snapshot stopped.",
        ),
        "add_fixed_cost": _spec(
            AddFixedCostIn,
            MONEY,
            "Add a monthly fixed cost (rent, utilities, subscription) with its amount and "
            "day. Use it when the user mentions a recurring bill the snapshot doesn't list.",
        ),
        "update_fixed_cost": _spec(
            UpdateFixedCostIn,
            MONEY,
            "Change a fixed cost's amount, day or name. Use it when the user says a bill "
            "changed, e.g. 'I moved, the rent is 2,400 now'.",
        ),
        "remove_fixed_cost": _spec(
            FixedCostIdIn,
            MONEY,
            "Remove a fixed cost. Use it when the user says a bill from the snapshot ended.",
        ),
        "complete_onboarding": _spec(
            NoInput,
            MONEY,
            "Finish onboarding and build the first plan. Use it when the snapshot's "
            "onboarding checklist is complete (goal, income, fixed costs, life context).",
        ),
        # shaping, slips, reflections, profile, savings
        "record_slip_reason": _spec(
            RecordSlipReasonIn,
            MONEY,
            "Record why a whole day went over budget. Use it only for a day-level "
            "overspend; the reason for one transaction goes through annotate_transaction "
            "instead.",
        ),
        "shape_budget": _spec(
            ShapeBudgetIn,
            MONEY,
            "Change how the budget is spread: weekday weights, pinned days, weekly category"
            " caps and the safety buffer. Use it when the user asks for more money on some "
            "days, a fixed amount on a date, a cap on a category, or a different buffer.",
        ),
        "record_reflection": _spec(
            RecordReflectionIn,
            WRITE,
            "Save the answer to the weekly reflection. Use it when the user answers the "
            "Sunday reflection question from the pending events.",
        ),
        "update_life_profile": _spec(
            UpdateLifeProfileIn,
            WRITE,
            "Save a soft coaching note (what works or doesn't for this user). Use it only "
            "for coaching notes; facts about the user's life go through add_life_fact.",
        ),
        "transfer_to_savings": _spec(
            TransferToSavingsIn,
            MONEY,
            "Move money from the balance to the savings pot. Use it when the user "
            "explicitly asks to put an amount aside now.",
        ),
        # transactions & receivables
        "annotate_transaction": _spec(
            AnnotateTransactionIn,
            MONEY,
            "Record why a transaction happened and who it was for; the code computes the "
            "effective amount and creates a receivable when others will repay. Use it when "
            "the user explains a transaction, e.g. the open question's ('I bought for 5 "
            "colleagues').",
        ),
        "create_receivable": _spec(
            CreateReceivableIn,
            MONEY,
            "Record money someone owes the user. Use it when the user says a person will "
            "pay them back and it isn't already part of an annotate_transaction call.",
        ),
        "cancel_receivable": _spec(
            ReceivableIdIn,
            MONEY,
            "Cancel a receivable. Use it when the user says nobody owes them that money after all.",
        ),
        "mark_receivable_paid": _spec(
            ReceivableIdIn,
            MONEY,
            "Mark a receivable as paid. Use it when the user says the person paid them back.",
        ),
        "offer_payment_request": _spec(
            ReceivableIdIn,
            WRITE,
            "Attach a tap card that lets the user request payment for an open receivable; "
            "it sends nothing by itself. Use it right after creating a receivable, or when "
            "the user wants to ask the debtor for the money.",
        ),
        # life facts & rules
        "add_life_fact": _spec(
            AddLifeFactIn,
            MONEY,
            "Save a fact about the user's life (job, household member, housing, pet, "
            "activity, priority...) so purchases are judged against their life. Use it "
            "whenever the user tells you something lasting about themselves, e.g. 'I'm a "
            "sports analyst'.",
        ),
        "update_life_fact": _spec(
            UpdateLifeFactIn,
            MONEY,
            "Change a saved fact. Use it when the user corrects a fact the snapshot lists "
            "with its id, e.g. they moved house.",
        ),
        "expire_life_fact": _spec(
            ExpireLifeFactIn,
            MONEY,
            "End a fact that no longer holds. Use it when the user says a fact stopped "
            "being true, e.g. 'my mother moved out'.",
        ),
        "confirm_hypothesis": _spec(
            ConfirmHypothesisIn,
            MONEY,
            "Accept or reject an open hypothesis. Use it when the user's words confirm or "
            "deny a hypothesis the snapshot lists, e.g. 'yes, I have a car'.",
        ),
        "create_pattern_rule": _spec(
            CreatePatternRuleIn,
            WRITE,
            "Save a recurring pattern: classify matching transactions, or never ask about "
            "them (suppress). Use it when the user says 'every Friday we eat with the team'"
            " or 'don't ask me about coffee'.",
        ),
        # pots
        "create_pot": _spec(
            CreatePotIn,
            MONEY,
            "Create a named savings pot for an event, an emergency or anything else. Use it"
            " when the user wants to save separately for something, e.g. an August trip.",
        ),
        "update_pot": _spec(
            UpdatePotIn,
            MONEY,
            "Change a pot's name, target or deadline. Use it when the user changes a plan "
            "the pot saves for.",
        ),
        "close_pot": _spec(
            PotIdIn,
            MONEY,
            "Close a pot. Use it when the user no longer needs a pot from the snapshot.",
        ),
        "link_transaction_to_pot": _spec(
            LinkTransactionToPotIn,
            MONEY,
            "Pay a transaction from a pot. Use it when the user says a purchase was the "
            "thing a pot saved for, e.g. the trip booking.",
        ),
    }
)

STRICT_PRIORITY: Final[tuple[str, ...]] = (
    "annotate_transaction",
    "offer_payment_request",
    "add_life_event",
    "set_goal",
    "update_goal",
    "create_receivable",
    "mark_receivable_paid",
    "cancel_receivable",
    "transfer_to_savings",
    "confirm_hypothesis",
    "link_transaction_to_pot",
    "cancel_life_event",
    "get_transaction",
    "mark_event_handled",
    "show_quick_replies",
    "get_transactions",
    "get_spending_summary",
    "add_income_source",
    "add_fixed_cost",
    "remove_income_source",
    "remove_fixed_cost",
    "close_pot",
)
"""The tools worth `strict` first: the typical calls (arch 6.6) and the ones with exact money."""

MAX_STRICT_TOOLS: Final = 20
MAX_OPTIONAL_PARAMS: Final = 24
MAX_UNION_PARAMS: Final = 16

_DROPPED_KEYS: Final = frozenset(
    {
        "title", "default", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
        "multipleOf", "minLength", "maxLength", "pattern", "maxItems", "examples",
    }
)  # fmt: skip


def _without_null(prop: JsonSchema) -> JsonSchema:
    """An optional property's schema without its `null` branch: optional means "leave it out"."""
    if "anyOf" not in prop:
        return prop
    branches = [branch for branch in prop["anyOf"] if branch != {"type": "null"}]
    if len(branches) != 1:
        return {**prop, "anyOf": branches}
    rest = {key: value for key, value in prop.items() if key != "anyOf"}
    return {**branches[0], **rest}


def _inline(node: Any, defs: Mapping[str, Any]) -> Any:
    """`node` with every `$ref` inlined and the keys strict tool use rejects dropped."""
    if isinstance(node, list):
        return [_inline(item, defs) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        target = _inline(defs[node["$ref"].rsplit("/", 1)[-1]], defs)
        target.pop("description", None)  # the enum's docstring: the field's own one is enough
        if "description" in node:
            target["description"] = node["description"]
        return target
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _DROPPED_KEYS or key == "$defs":
            continue
        if key == "properties":
            required = set(node.get("required", ()))
            out[key] = {
                name: _inline(prop, defs)
                if name in required
                else _without_null(_inline(prop, defs))
                for name, prop in value.items()
            }
        else:
            out[key] = _inline(value, defs)
    if out.get("minItems", 0) > 1:
        out["minItems"] = 1  # only 0 and 1 are accepted
    if out.get("type") == "object":
        out["additionalProperties"] = False
        out.setdefault("properties", {})
        out["required"] = list(out.get("required", []))
    return out


def input_schema(model: type[ToolInput]) -> JsonSchema:
    """The strict-compatible JSON schema of a tool's input (see the module docstring)."""
    raw = model.model_json_schema(by_alias=True)
    schema: JsonSchema = _inline(raw, raw.get("$defs", {}))
    schema.pop("description", None)  # the tool's description says it
    return schema


def _walk_objects(node: Any) -> list[JsonSchema]:
    found: list[JsonSchema] = []
    if isinstance(node, dict):
        if node.get("type") == "object":
            found.append(node)
        for value in node.values():
            found.extend(_walk_objects(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk_objects(item))
    return found


def schema_cost(schema: JsonSchema) -> tuple[int, int]:
    """(optional parameters, union parameters) of a schema, as the strict limits count them."""
    optional = unions = 0
    for obj in _walk_objects(schema):
        required = set(obj["required"])
        for name, prop in obj["properties"].items():
            optional += name not in required
            unions += "anyOf" in prop or isinstance(prop.get("type"), list)
    return optional, unions


_SCHEMAS: Final[Mapping[str, JsonSchema]] = MappingProxyType(
    {name: input_schema(spec.input_model) for name, spec in TOOL_SPECS.items()}
)
_COSTS: Final[Mapping[str, tuple[int, int]]] = MappingProxyType(
    {name: schema_cost(schema) for name, schema in _SCHEMAS.items()}
)


def tool_param(name: str, *, strict: bool) -> BetaToolParam:
    """The plain tool dict for `LLM.create` (a fresh copy: callers may not mutate the cache)."""
    param: BetaToolParam = {
        "name": name,
        "description": TOOL_SPECS[name].description,
        "input_schema": copy.deepcopy(_SCHEMAS[name]),
    }
    if strict:
        param["strict"] = True
    return param


def strict_names(names: list[str]) -> frozenset[str]:
    """The tools of `names` sent as strict: `STRICT_PRIORITY` order, within the API's limits."""
    chosen: set[str] = set()
    optional = unions = 0
    for name in STRICT_PRIORITY:
        if name not in names or len(chosen) == MAX_STRICT_TOOLS:
            continue
        cost_optional, cost_unions = _COSTS[name]
        if (
            optional + cost_optional > MAX_OPTIONAL_PARAMS
            or unions + cost_unions > MAX_UNION_PARAMS
        ):
            continue
        chosen.add(name)
        optional += cost_optional
        unions += cost_unions
    return frozenset(chosen)


@dataclass(frozen=True, slots=True)
class ToolState:
    """What `tools_for` needs to know about the user (A6 builds it from the run's context)."""

    has_active_goal: bool


def tools_for(state: ToolState, trigger: str) -> list[BetaToolParam]:
    """The tool list of one agent run, computed once per run (D46), in `TOOL_SPECS` order."""
    names = [
        name
        for name, spec in TOOL_SPECS.items()
        if (trigger != "proactive" or spec.flags.read_only)
        and not (name == "set_goal" and state.has_active_goal)
        and not (name == "update_goal" and not state.has_active_goal)
    ]
    strict = strict_names(names)
    return [tool_param(name, strict=name in strict) for name in names]
