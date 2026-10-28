"""Shared domain objects (F2): frozen Pydantic models every pure core takes and returns.

The services (B3) and `load_user_context` (B4) build them from DB rows; the engine and the
context layer never see ORM rows. Field names follow the DB columns (arch §4).
"""

from datetime import date, time
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AwareDatetime,
    ConfigDict,
    Field,
    SerializeAsAny,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.domain.base import Frozen, Money, Month, NonNegativeMoney, PositiveMoney, Score, Weekday
from app.domain.enums import (
    AgentEventStatus,
    AgentEventType,
    AnnotationSource,
    Beneficiary,
    Category,
    CoachStyle,
    Decision,
    Direction,
    FactSource,
    FactStatus,
    FactType,
    GoalStatus,
    Language,
    LifeEventStatus,
    LifeEventType,
    Persistence,
    PotKind,
    PotStatus,
    Purpose,
    ReceivableStatus,
    RuleKind,
    RuleSource,
    SignatureEffect,
    SignatureOrigin,
    TransactionSource,
    TransactionStatus,
    TransferKind,
)
from app.domain.results import Forecast, PlanSummary

WeekdayName = Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# ── transactions ─────────────────────────────────────────────────────────────────────────


class Item(Frozen):
    """One line of an e-receipt (D32)."""

    name: str = Field(min_length=1)
    qty: int = Field(default=1, ge=1)
    amount: NonNegativeMoney | None = None


class TxView(Frozen):
    """A transaction as the cores see it. `effective_amount` defaults to `amount`."""

    id: int
    amount: PositiveMoney
    direction: Direction = Direction.DEBIT
    occurred_at: AwareDatetime
    merchant_raw: str
    merchant_id: str | None = None
    merchant: str | None = None
    mcc: str | None = None
    category: Category | None = None
    items: tuple[Item, ...] | None = None
    description: str | None = None
    status: TransactionStatus = TransactionStatus.UNRESOLVED
    source: TransactionSource = TransactionSource.SIM
    effective_amount: NonNegativeMoney = Field(default_factory=lambda data: data["amount"])
    purpose: Purpose | None = None
    beneficiary: Beneficiary | None = None
    annotation_source: AnnotationSource | None = None
    annotation_confidence: Score | None = None
    explanation: str | None = None
    life_fit: Score | None = None
    anomaly_score: Score | None = None
    unexplained: Score | None = None
    decision: Decision | None = None
    matched_fact_id: int | None = None
    matched_rule_id: int | None = None
    pot_id: int | None = None
    receivable_id: int | None = None

    @model_validator(mode="after")
    def _effective_within_amount(self) -> Self:
        if self.effective_amount > self.amount:
            raise ValueError("effective_amount must be between 0 and amount")
        return self


# ── life facts ───────────────────────────────────────────────────────────────────────────


class FactValue(Frozen):
    """Base of the typed `LifeFact.value` payloads."""


class OccupationValue(FactValue):
    title: str = Field(min_length=1)
    work_mode: Literal["remote", "office", "hybrid"] | None = None
    employer: str | None = None


class HouseholdMemberValue(FactValue):
    role: Literal["adult", "child"]
    age: int | None = Field(default=None, ge=0, le=120)
    relation: str | None = None  # "partner", "mama", …

    @model_validator(mode="after")
    def _child_needs_age(self) -> Self:
        if self.role == "child" and self.age is None:
            raise ValueError("a child needs an age")
        return self


class PetValue(FactValue):
    kind: str = Field(min_length=1)
    count: int = Field(default=1, ge=1)


class VehicleValue(FactValue):
    kind: str = "car"
    fuel: str | None = None


class ActivityValue(FactValue):
    name: str = Field(min_length=1)
    per_week: float | None = Field(default=None, gt=0)


class PriorityValue(FactValue):
    """`protected` is never cut; `reduce` is where the user wants to cut (arch 4.4)."""

    category: Category
    label: str | None = None  # the user's word, e.g. "concerte" for entertainment
    priority: Literal["protected", "reduce"]


class LifeEventValue(FactValue):
    name: str = Field(min_length=1)
    starts_on: date | None = None
    est_cost: NonNegativeMoney | None = None


class CustomValue(FactValue):
    """Any other fact type: free keys."""

    model_config = ConfigDict(frozen=True, extra="allow")


FACT_VALUES: dict[FactType, type[FactValue]] = {
    FactType.OCCUPATION: OccupationValue,
    FactType.HOUSEHOLD_MEMBER: HouseholdMemberValue,
    FactType.PET: PetValue,
    FactType.VEHICLE: VehicleValue,
    FactType.ACTIVITY: ActivityValue,
    FactType.PRIORITY: PriorityValue,
    FactType.LIFE_EVENT: LifeEventValue,
}  # every other type → CustomValue


def _typed_value(value: Any, fact_type: Any) -> Any:
    if isinstance(value, FactValue):
        return value
    model = FACT_VALUES.get(fact_type, CustomValue) if fact_type in set(FactType) else CustomValue
    return model.model_validate(value)


class LifeFact(Frozen):
    id: int | None = None
    type: FactType
    value: SerializeAsAny[FactValue]
    text: str | None = None
    source: FactSource
    status: FactStatus = FactStatus.CONFIRMED
    confidence: Score = 0.95
    persistence: Persistence = Persistence.PERMANENT
    valid_from: date | None = None
    valid_to: date | None = None
    evidence: tuple[Any, ...] = ()

    @field_validator("value", mode="before")
    @classmethod
    def _value_by_type(cls, value: Any, info: ValidationInfo) -> Any:
        return _typed_value(value, info.data.get("type"))

    @model_validator(mode="after")
    def _validity(self) -> Self:
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to must be on or after valid_from")
        if self.persistence == Persistence.TEMPORARY and self.valid_to is None:
            raise ValueError("a temporary fact needs valid_to")
        return self

    def active_on(self, day: date) -> bool:
        """Confirmed and inside its validity window (bounds inclusive)."""
        return (
            self.status == FactStatus.CONFIRMED
            and (self.valid_from is None or self.valid_from <= day)
            and (self.valid_to is None or day <= self.valid_to)
        )


class LifeFactDraft(Frozen):
    """A guessed fact before it's saved (`infer_hypotheses`, 5.3.8)."""

    type: FactType
    value: SerializeAsAny[FactValue]
    text: str
    question: str  # the 1-tap card: "Ai mașină?"
    confidence: Score

    @field_validator("value", mode="before")
    @classmethod
    def _value_by_type(cls, value: Any, info: ValidationInfo) -> Any:
        return _typed_value(value, info.data.get("type"))


# ── signatures & rules ───────────────────────────────────────────────────────────────────


class TimeWindow(Frozen):
    """`{"weekdays": [5], "from": "12:00", "to": "15:00"}` or `{"months": [8, 9]}`."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )

    weekdays: tuple[Weekday, ...] = ()
    from_: time | None = Field(default=None, alias="from")
    to: time | None = None
    months: tuple[Month, ...] = ()

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.from_ is not None and self.to is not None and self.from_ >= self.to:
            raise ValueError("from must be before to")
        return self


class Signature(Frozen):
    """What a fact predicts about spending (arch 5.3.3)."""

    id: int | None = None
    fact_id: int | None = None
    effect: SignatureEffect
    category: Category | None = None
    merchant_hints: tuple[str, ...] = ()
    item_keywords: tuple[str, ...] = ()
    amount_min: NonNegativeMoney | None = None
    amount_max: NonNegativeMoney | None = None
    multiplier: Decimal | None = Field(default=None, gt=0)
    time_window: TimeWindow | None = None
    expected_date: date | None = None
    expected_amount: NonNegativeMoney | None = None
    replacement_cycle_days: int | None = Field(default=None, gt=0)
    purpose: Purpose
    strength: Score
    origin: SignatureOrigin = SignatureOrigin.LIBRARY
    active: bool = True

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        lo, hi = self.amount_min, self.amount_max
        if lo is not None and hi is not None and lo > hi:
            raise ValueError("amount_min must not exceed amount_max")
        if self.effect == SignatureEffect.EXPLAINS and not (self.category or self.merchant_hints):
            raise ValueError("an explains signature needs a category or merchant hints")
        if self.effect == SignatureEffect.SCALES_BASELINE and not (
            self.category and self.multiplier
        ):
            raise ValueError("a scales_baseline signature needs a category and a multiplier")
        if self.effect == SignatureEffect.EXPECTS_EVENT:
            has_when = self.expected_date is not None or bool(
                self.time_window and self.time_window.months
            )
            if self.expected_amount is None or not has_when:
                raise ValueError("an expects_event signature needs an amount and a date or months")
        return self


class RuleMatch(Frozen):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )

    merchant_id: str | None = None
    category: Category | None = None
    weekdays: tuple[Weekday, ...] = ()
    from_: time | None = Field(default=None, alias="from")
    to: time | None = None
    amount_min: NonNegativeMoney | None = None
    amount_max: NonNegativeMoney | None = None

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.from_ is not None and self.to is not None and self.from_ >= self.to:
            raise ValueError("from must be before to")
        lo, hi = self.amount_min, self.amount_max
        if lo is not None and hi is not None and lo > hi:
            raise ValueError("amount_min must not exceed amount_max")
        return self


class RuleOutcome(Frozen):
    purpose: Purpose | None = None
    beneficiary: Beneficiary | None = None
    label: str | None = None  # "Prânz cu echipa"
    own_share_ratio: Decimal | None = Field(default=None, ge=0, le=1)


class PatternRule(Frozen):
    """A learned pattern (arch 5.3.7)."""

    id: int | None = None
    kind: RuleKind
    match: RuleMatch
    outcome: RuleOutcome = RuleOutcome()
    confidence: Score
    hits: int = Field(default=0, ge=0)
    misses: int = Field(default=0, ge=0)
    source: RuleSource
    active: bool = True
    last_hit_at: AwareDatetime | None = None


# ── money & plan inputs ──────────────────────────────────────────────────────────────────


class Account(Frozen):
    current_balance: Money = Decimal("0")  # may be negative
    savings_pot: NonNegativeMoney = Decimal("0")


class Goal(Frozen):
    id: int
    amount: PositiveMoney
    deadline: date
    motivation: str | None = None
    status: GoalStatus = GoalStatus.ACTIVE
    soft: bool = True  # the deadline may move (E9)


class IncomeSource(Frozen):
    id: int
    source: str
    amount: PositiveMoney
    day_of_month: int = Field(ge=1, le=31)


class FixedCost(Frozen):
    id: int
    name: str
    amount: PositiveMoney
    day_of_month: int = Field(ge=1, le=31)


class LifeEvent(Frozen):
    id: int
    name: str
    date: date
    est_cost: NonNegativeMoney
    type: LifeEventType
    status: LifeEventStatus = LifeEventStatus.PLANNED


class Pot(Frozen):
    id: int
    name: str
    kind: PotKind
    goal_id: int | None = None
    life_event_id: int | None = None
    fact_id: int | None = None
    target: PositiveMoney
    saved: NonNegativeMoney = Decimal("0")
    deadline: date | None = None
    monthly_contribution: NonNegativeMoney = Decimal("0")
    status: PotStatus = PotStatus.ACTIVE


class Receivable(Frozen):
    id: int
    transaction_id: int | None = None
    amount: PositiveMoney
    debtor_label: str = Field(min_length=1)
    people_count: int | None = Field(default=None, ge=1)
    amount_each: NonNegativeMoney | None = None
    expected_by: date
    status: ReceivableStatus = ReceivableStatus.OPEN
    requested_at: AwareDatetime | None = None
    paid_at: AwareDatetime | None = None


class Transfer(Frozen):
    id: int
    amount: PositiveMoney
    kind: TransferKind = TransferKind.MANUAL
    pot_id: int | None = None
    income_transaction_id: int | None = None
    created_at: AwareDatetime | None = None
    undone_at: AwareDatetime | None = None


class PlanPreferences(Frozen):
    """How the user shaped the budget (arch 6.7, D19)."""

    weekday_weights: dict[WeekdayName, Annotated[float, Field(ge=0.5, le=3)]] = Field(
        default_factory=dict
    )
    pinned_days: dict[date, NonNegativeMoney] = Field(default_factory=dict)
    category_caps: dict[Category, NonNegativeMoney] = Field(
        default_factory=dict
    )  # per week, soft limit
    buffer_pct: Decimal = Field(default=Decimal("0.10"), ge=0, le=Decimal("0.3"))


class Baseline(Frozen):
    """Cached per-category baseline (arch 5.3.5), on effective amounts."""

    category: Category
    personal_median: NonNegativeMoney | None = None
    personal_mad: NonNegativeMoney | None = None
    n: int = Field(default=0, ge=0)
    prior_median: NonNegativeMoney | None = None
    household_multiplier: Decimal = Field(default=Decimal("1"), gt=0)
    expected_median: NonNegativeMoney | None = None
    monthly_expected: NonNegativeMoney | None = None


class Merchant(Frozen):
    id: str  # slug, e.g. "mega_image"
    canonical_name: str
    aliases: tuple[str, ...] = ()
    category: Category
    mcc: str | None = None
    typical_basket: NonNegativeMoney | None = None
    multi_category: bool = False


# ── the user ─────────────────────────────────────────────────────────────────────────────


class UserProfile(Frozen):
    id: int
    name: str
    age: int | None = Field(default=None, ge=0, le=120)
    language: Language = Language.RO
    coach_style: CoachStyle = CoachStyle.WARM
    timezone: str = "Europe/Bucharest"
    city: str | None = None
    household_scale: Decimal = Field(default=Decimal("1.00"), ge=1)
    onboarded_at: AwareDatetime | None = None


class AgentEventView(Frozen):
    id: int
    type: AgentEventType
    status: AgentEventStatus = AgentEventStatus.PENDING
    payload: dict[str, Any] = Field(default_factory=dict)
    event_date: date
    ref_transaction_id: int | None = None
    created_at: AwareDatetime | None = None
    asked_at: AwareDatetime | None = None
    answered_at: AwareDatetime | None = None


class UserContext(Frozen):
    """Everything about one user on one day: what the engine, the context layer and the
    snapshot builder all read (built by `services.context_loader.load_user_context`, B4)."""

    today: date
    profile: UserProfile
    account: Account
    goal: Goal | None = None
    goal_pot: Pot | None = None
    income_sources: tuple[IncomeSource, ...] = ()
    fixed_costs: tuple[FixedCost, ...] = ()
    life_events: tuple[LifeEvent, ...] = ()  # planned
    pots: tuple[Pot, ...] = ()  # active, incl. the goal pot
    receivables: tuple[Receivable, ...] = ()  # open or requested
    facts: tuple[LifeFact, ...] = ()  # confirmed and active on `today`
    hypotheses: tuple[LifeFact, ...] = ()
    signatures: tuple[Signature, ...] = ()  # active
    rules: tuple[PatternRule, ...] = ()  # active
    plan_preferences: PlanPreferences = PlanPreferences()
    baselines: dict[Category, Baseline] = Field(default_factory=dict)
    transactions: tuple[TxView, ...] = ()  # resolved, last `history_days`
    plan: PlanSummary | None = None
    forecast: Forecast | None = None
    last_weekly_forecast: Forecast | None = None
    events: tuple[AgentEventView, ...] = ()  # pending or asked
    questions_asked_today: int = Field(default=0, ge=0)
