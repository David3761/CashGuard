"""What the pure cores return (F2 step 3). Shapes follow arch 6.7, 15.1 and 9.3."""

from datetime import date
from typing import Any, Literal

from pydantic import Field

from app.domain.base import Frozen, Money, NonNegativeMoney, Score
from app.domain.enums import (
    AgentEventType,
    AnnotationSource,
    Beneficiary,
    Category,
    Decision,
    Purpose,
)

# ── context layer (David G.) ─────────────────────────────────────────────────────────────


class QuestionHint(Frozen):
    reason: str  # i18n key, e.g. "basket_ratio"
    params: dict[str, Any] = Field(
        default_factory=dict
    )  # e.g. {"ratio": 6, "merchant": "Mega Image"}
    ask_what_item: bool = False  # multi-category merchant without items (D32)


class Evaluation(Frozen):
    """How one transaction is read (arch 5.3.4); the pipeline saves it as is."""

    category: Category
    merchant_id: str | None = None
    merchant: str | None = None
    purpose: Purpose
    beneficiary: Beneficiary = Beneficiary.SELF
    effective_amount: NonNegativeMoney
    annotation_source: AnnotationSource = AnnotationSource.AUTO
    annotation_confidence: Score | None = None
    life_fit: Score
    anomaly_score: Score
    unexplained: Score
    decision: Decision
    explanation: str | None = None  # the "because", in the user's language
    matched_fact_id: int | None = None
    matched_rule_id: int | None = None
    pot_id: int | None = None
    goal_impact: float = Field(default=0, ge=0)
    question_hint: QuestionHint | None = None


class FitResult(Frozen):
    score: Score
    source: Literal["signature", "rule", "precedent", "expected_event", "none"] = "none"
    fact_id: int | None = None
    rule_id: int | None = None
    explanation_key: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class QuestionCandidate(Frozen):
    transaction_id: int
    priority: float = Field(ge=0)  # unexplained × goal_impact
    hint: QuestionHint | None = None
    event_type: AgentEventType = AgentEventType.TRANSACTION_QUESTION


class RuleChange(Frozen):
    rule_id: int | None = None
    action: Literal["created", "strengthened", "weakened", "deactivated"]
    confidence: Score


class PropagationResult(Frozen):
    fact_id: int
    signatures: int = Field(default=0, ge=0)
    reevaluated_transaction_ids: tuple[int, ...] = ()
    plan_version: int | None = None
    previous_probability: Score | None = None
    probability: Score | None = None


# ── engine (danutu) ──────────────────────────────────────────────────────────────────────


class AnomalyFeatures(Frozen):
    z: float
    stat: Score
    novelty: Score
    materiality: Score


class DayBudget(Frozen):
    date: date
    budget: Money
    weight: float = 1.0
    pinned: bool = False


class PlanResult(Frozen):
    """`compute_plan` output (arch 6.7)."""

    today_budget: Money
    next_7_days: tuple[DayBudget, ...] = ()
    feasible: bool
    infeasible_days: tuple[date, ...] = ()


class PlanSummary(Frozen):
    """A saved plan version, as tool results and `/state` show it (arch 6.7, 9.3)."""

    version: int = Field(ge=1)
    feasible: bool
    today_budget: Money
    previous_today_budget: Money | None = None
    next_7_days: tuple[DayBudget, ...] = ()
    reason: str | None = None


class Driver(Frozen):
    category: Category
    pp_per_100_lei: float = Field(ge=0)


class Option(Frozen):
    kind: Literal["count_receivables", "move_deadline", "reduce_category"]
    label: str
    probability: Score
    apply_hint: dict[str, Any] = Field(default_factory=dict)


class Forecast(Frozen):
    """Goal probability (arch 6.7). "77%, era 71%, săptămâna trecută 72%"."""

    probability: Score
    previous_probability: Score | None = None
    last_week_probability: Score | None = None
    p10: Money
    p50: Money
    p90: Money
    expected_reach_date: date | None = None
    drivers: tuple[Driver, ...] = ()
    options: tuple[Option, ...] | None = None
    plan_version: int | None = None
    sim_date: date | None = None
    is_weekly_snapshot: bool = False


class SimDiff(Frozen):
    today_budget: Money
    probability: float


class Solve(Frozen):
    deadline_needed: date | None = None
    goal_amount_possible: Money | None = None
    reason: str | None = None


class SimResult(Frozen):
    """`simulate_plan`: what-if, nothing saved (arch 6.7)."""

    feasible: bool
    today_budget: Money
    avg_daily_budget: Money
    probability: Score
    diff_vs_current: SimDiff
    solve: Solve | None = None


# ── agent (David G.) ─────────────────────────────────────────────────────────────────────


class AgentResult(Frozen):
    """What one agent run produces (arch 15.1); B9 saves and pushes it."""

    text: str
    speak_text: str | None = None
    quick_replies: tuple[str, ...] = ()
    action_cards: tuple[dict[str, Any], ...] = ()
    plan_changed: bool = False
    ref_transaction_id: int | None = None
