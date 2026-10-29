"""Results of the pure cores and the §15 functions (F2 step 7; arch 5.3.4, 5.3.6, 6.7, 9.3, 15).

The S0 stubs of both teams return these. Each has only the rules every producer must keep.
"""

from collections.abc import Mapping
from datetime import date as Date
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BeforeValidator, Field, JsonValue, StrictBool, model_validator

from app.domain.enums import (
    AgentEventType,
    AnnotationSource,
    Beneficiary,
    Category,
    Decision,
    Purpose,
)
from app.domain.models import (
    DomainModel,
    Factor,
    Id,
    MerchantId,
    NonNegMoney,
    PatternRule,
    Ratio,
    Text80,
    Text300,
    Timestamp,
)
from app.domain.money import Money


def _not_bool(value: object) -> object:
    if isinstance(value, bool):
        raise ValueError("a bool is not a number")
    return value


NonNegFloat = Annotated[float, BeforeValidator(_not_bool), Field(ge=0, allow_inf_nan=False)]
Probability = Ratio
Text4000 = Annotated[str, Field(min_length=1, max_length=4000)]


# ── context layer (David G.) ─────────────────────────────────────────────────────────────────


class QuestionHint(DomainModel):
    """Why a transaction is worth asking about (5.3.4 step 6): an i18n key + its params."""

    reason: Text80  # e.g. "basket_ratio"
    params: Mapping[str, JsonValue] = Field(default_factory=dict)  # e.g. {"ratio": 6}
    ask_what_item: StrictBool = False  # D32: multi-category merchant without items


class Evaluation(DomainModel):
    """`evaluate_transaction`'s result (§15); B3's `save_evaluation` stores it."""

    category: Category
    merchant_id: MerchantId | None = None
    merchant: Text80 | None = None
    purpose: Purpose
    beneficiary: Beneficiary
    effective_amount: NonNegMoney
    annotation_source: AnnotationSource
    confidence: Ratio
    life_fit: Ratio
    anomaly_score: Ratio
    unexplained: Ratio
    decision: Decision
    explanation: Text300 | None = None
    matched_fact_id: Id | None = None
    matched_rule_id: Id | None = None
    pot_id: Id | None = None
    goal_impact: NonNegFloat = 0.0
    question_hint: QuestionHint | None = None

    @model_validator(mode="after")
    def _ask_needs_a_hint(self) -> Self:
        if self.decision is Decision.ASK and self.question_hint is None:
            raise ValueError("decision ask needs a question_hint")
        return self


class FitResult(DomainModel):
    """C5's `life_fit` (5.3.4 step 3): the best explanation and its score."""

    score: Ratio
    source: Literal["signature", "expects_event", "rule", "precedent", "none"]
    fact_id: Id | None = None
    rule_id: Id | None = None
    explanation_key: Text80 | None = None
    params: Mapping[str, JsonValue] = Field(default_factory=dict)


class QuestionCandidate(DomainModel):
    """A transaction that could be today's question (5.3.6)."""

    transaction_id: Id
    occurred_at: Timestamp  # tie-break: the older one first
    unexplained: Ratio
    goal_impact: NonNegFloat
    question_hint: QuestionHint

    @property
    def priority(self) -> float:
        return self.unexplained * self.goal_impact


class RuleChange(DomainModel):
    """What C8 learned (5.3.7)."""

    action: Literal["created", "updated", "deactivated"]
    rule: PatternRule
    previous_confidence: Ratio | None = None


# ── engine (danutu) ──────────────────────────────────────────────────────────────────────────


class AnomalyFeatures(DomainModel):
    """E7 (5.3.4 step 4)."""

    z: Annotated[float, Field(allow_inf_nan=False)]
    stat: Ratio
    novelty: Ratio
    materiality: Ratio


class DayBudget(DomainModel):
    date: Date
    budget: Money
    weight: Annotated[Factor, Field(gt=0)] = Decimal("1")
    pinned: StrictBool = False


class PlanResult(DomainModel):
    """E2's `compute_plan` result.

    `days` (the whole horizon) and the 6.7 terms `available`, `free_money`, `still_to_save` are
    the integration's additions for danutu's E2 (None = not computed, e.g. a stub)."""

    today_budget: Money
    next_7_days: tuple[DayBudget, ...] = ()
    feasible: StrictBool
    infeasible_days: tuple[Date, ...] = ()
    days: tuple[DayBudget, ...] = ()
    available: Money | None = None
    free_money: Money | None = None
    still_to_save: NonNegMoney | None = None


class PlanSummary(DomainModel):
    """`recompute_plan`'s result (§15; the 6.7 tool result's `plan`)."""

    version: Annotated[int, Field(ge=1, strict=True)]
    feasible: StrictBool
    today_budget: Money
    previous_today_budget: Money | None = None
    next_7_days: tuple[DayBudget, ...] = ()
    reason: Text300 | None = None


class Driver(DomainModel):
    category: Category
    pp_per_100_lei: NonNegFloat


OptionKind = Literal["count_receivables", "move_deadline", "reduce_category"]
OptionParam = Money | Date | int | Text80
"""An option's label parameter: money stays a Decimal (a JSON number), a date an ISO date."""


class Option(DomainModel):
    """One E9 option. `label` is shown as is; `label_key` + `params` are danutu's i18n form
    (`option.move_deadline`, {"deadline": ..., "months": 2})."""

    label: Text80
    probability: Probability
    apply_hint: Mapping[str, JsonValue] = Field(default_factory=dict)
    kind: OptionKind | None = None
    label_key: Text80 | None = None
    params: Mapping[str, OptionParam] = Field(default_factory=dict)


class Forecast(DomainModel):
    """`forecast_goal`'s result (§15; 9.3 Forecast)."""

    probability: Probability
    previous_probability: Probability | None = None
    last_week_probability: Probability | None = None
    p10: Money
    p50: Money
    p90: Money
    expected_reach_date: Date | None = None
    drivers: tuple[Driver, ...] = ()
    options: tuple[Option, ...] | None = None
    # E8's bookkeeping (integration additions, bomboe's names): the plan version and sim day the
    # forecast was computed for, and whether it is this week's snapshot.
    plan_version: Annotated[int, Field(ge=0, strict=True)] | None = None
    sim_date: Date | None = None
    is_weekly_snapshot: StrictBool = False

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if not self.p10 <= self.p50 <= self.p90:
            raise ValueError("p10 <= p50 <= p90")
        return self


class SignalDraft(DomainModel):
    """E11's day-level signal: an `agent_events` row to create (type, event_date, payload).

    The payload carries engine values (Decimal money, ratios, categories); the caller stores it
    as JSON (money as numbers)."""

    type: AgentEventType
    date: Date
    payload: Mapping[str, OptionParam | float] = Field(default_factory=dict)


class SimDiff(DomainModel):
    today_budget: Money
    probability: Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)]


class SolveResult(DomainModel):
    deadline_needed: Date | None = None
    goal_amount_possible: Money | None = None
    reason: Text80 | None = None  # "target_not_reachable" when neither is found (E5)


class SimResult(DomainModel):
    """`simulate_plan`'s result (§15, 6.7): nothing is saved."""

    feasible: StrictBool
    today_budget: Money
    avg_daily_budget: Money
    probability: Probability
    diff_vs_current: SimDiff
    solve: SolveResult | None = None


class PropagationResult(DomainModel):
    """`on_fact_changed`'s result (§15, 5.3.9)."""

    fact_id: Id
    household_scale: Annotated[Factor, Field(gt=0)] | None = None
    changed_transaction_ids: tuple[Id, ...] = ()
    plan: PlanSummary | None = None
    forecast: Forecast | None = None


# ── agent (David G.) ─────────────────────────────────────────────────────────────────────────


class ActionCard(DomainModel):
    """A tap card (9.3); sending a payment request waits for the user's tap (D31)."""

    type: Literal["request_payment"]
    receivable_id: Id
    label: Text80


class AgentResult(DomainModel):
    """`run_agent`'s result (§15): never a tool-call internal (9.3)."""

    text: Text4000
    speak_text: Text300 | None = None
    quick_replies: tuple[Text80, ...] = ()
    action_cards: tuple[ActionCard, ...] = ()
    plan_changed: StrictBool = False
    ref_transaction_id: Id | None = None
