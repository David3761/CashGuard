"""Domain models (F2): the typed, immutable views every pure core uses (work-breakdown F2).

Every model is a `DomainModel`:
- **frozen**: assigning a field raises, so no value can skip its validator (e.g. `Money`'s
  rounding). Change a model with `replace(**changes)`, which validates like a new model;
  `model_copy(update=...)` doesn't, so don't use it.
- **extra="forbid"**: an unknown key (e.g. a smuggled `user_id`) is an error.
- sequences are tuples (deeply immutable); maps are typed `Mapping` (read-only for mypy).
- `model_validate_json` reads every number exactly and rejects duplicate keys
  (`money.parse_json`): pydantic's own JSON parser reads numbers as floats first.

Scores and probabilities are `float` (`Ratio`, 0-1); money is `Money` and anything multiplied with
money is a `Factor` (both `Decimal`, both JSON numbers): `Decimal * float` raises (plan Q1).
Timestamps are tz-aware (`Timestamp`: never Unix-time numbers). There's no `user_id` on a view
(the services scope every query, and `UserContext` carries the one user id).
"""

import re
from collections.abc import Mapping
from datetime import date as Date
from datetime import datetime, time
from decimal import Decimal
from types import MappingProxyType
from typing import Annotated, Any, Final, Literal, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
    PlainSerializer,
    StrictBool,
    StringConstraints,
    ValidationError,
    ValidationInfo,
    WithJsonSchema,
    field_validator,
    model_validator,
)
from pydantic.config import ExtraValues
from pydantic_core import InitErrorDetails

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
    HouseholdRole,
    InputMode,
    Language,
    LedgerStatus,
    LifeEventStatus,
    LifeEventType,
    Liquidity,
    MessageRole,
    Persistence,
    PotKind,
    PotStatus,
    PriorityLevel,
    ProductKind,
    Purpose,
    ReceivableStatus,
    RuleKind,
    RuleSource,
    SignatureEffect,
    SignatureOrigin,
    TransferKind,
    TxSource,
    TxStatus,
)
from app.domain.money import Money, decimal_to_json, parse_json, to_decimal

# ── the base model ───────────────────────────────────────────────────────────────────────────


class DomainModel(BaseModel):
    """Frozen, no unknown keys, changed only through `replace`, JSON read exactly.

    pydantic's bypasses are closed: `model_copy(update=...)` re-validates, `model_construct`
    raises, and `extra=` overrides of `extra="forbid"` are refused.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )

    def replace(self, **changes: object) -> Self:
        """A copy with `changes`, validated like a new model (unknown fields are errors)."""
        return self.model_validate({**self.model_dump(by_alias=False), **changes})

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        """A validated copy (pydantic's skips validation). `deep` is moot: models are frozen."""
        return self.replace(**(update or {}))

    @classmethod
    def model_construct(  # type: ignore[override]  # the pydantic plugin types it per model
        cls, _fields_set: set[str] | None = None, **values: Any
    ) -> Self:
        """Refused: it skips validation. Use `model_validate`."""
        raise TypeError(f"{cls.__name__}.model_construct skips validation: use model_validate")

    @classmethod
    def model_validate(
        cls,
        obj: Any,
        *,
        strict: bool | None = None,
        extra: ExtraValues | None = None,
        from_attributes: bool | None = None,
        context: Any | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> Self:
        """pydantic's, without the `extra=` override (it would undo `extra="forbid"`)."""
        _refuse_extra(cls, extra)
        return super().model_validate(
            obj,
            strict=strict,
            from_attributes=from_attributes,
            context=context,
            by_alias=by_alias,
            by_name=by_name,
        )

    @classmethod
    def model_validate_strings(
        cls,
        obj: Any,
        *,
        strict: bool | None = None,
        extra: ExtraValues | None = None,
        context: Any | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> Self:
        _refuse_extra(cls, extra)
        return super().model_validate_strings(
            obj, strict=strict, context=context, by_alias=by_alias, by_name=by_name
        )

    @classmethod
    def model_validate_json(
        cls,
        json_data: str | bytes | bytearray,
        *,
        strict: bool | None = None,
        extra: ExtraValues | None = None,
        context: Any | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> Self:
        """Numbers read exactly; duplicate keys, NaN, bad JSON and deep nesting are a
        `ValidationError` (json_invalid), like pydantic's own parse errors."""
        _refuse_extra(cls, extra)
        if strict:  # it would mean python-mode strictness (e.g. no date strings): refuse it
            raise TypeError("DomainModel.model_validate_json has no strict mode")
        return cls.model_validate(
            parse_json_or_error(json_data, cls.__name__),
            context=context,
            by_alias=by_alias,
            by_name=by_name,
        )


def _refuse_extra(cls: type[BaseModel], extra: ExtraValues | None) -> None:
    if extra is not None:
        raise TypeError(f"{cls.__name__}: extra= is refused (domain models forbid unknown keys)")


def parse_json_or_error(data: str | bytes | bytearray, title: str) -> object:
    """`money.parse_json`, with every parse failure turned into a pydantic `ValidationError`."""
    try:
        return parse_json(data)
    except (ValueError, RecursionError) as error:
        detail = InitErrorDetails(
            type="json_invalid", loc=(), input=data, ctx={"error": str(error)}
        )
        raise ValidationError.from_exception_data(title, [detail], input_type="json") from None


# ── shared field types ───────────────────────────────────────────────────────────────────────


def _not_bool(value: object) -> object:
    if isinstance(value, bool):  # True would silently be 1.0
        raise ValueError("a bool is not a number")
    return value


_ISO_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]{1,6})?)?(Z|[+-][0-9]{2}:[0-9]{2})"
)


def _timestamp_input(value: object) -> object:
    # pydantic's lax datetime reads ints, floats and numeric strings as Unix time (20260615 ->
    # 1970-08-23): only datetimes and ISO-8601 strings with an offset are timestamps here.
    if isinstance(value, datetime) or (isinstance(value, str) and _ISO_TIMESTAMP.fullmatch(value)):
        return value
    raise ValueError("a timestamp is an aware datetime or ISO-8601 with an offset")


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    if len(set(values)) != len(values):
        raise ValueError("values must be unique")
    return values


Id = Annotated[int, Field(gt=0, le=2**63 - 1, strict=True)]
"""A database id: a positive BIGINT (strict: not True, not "5")."""
MerchantId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(_[a-z0-9]+)*$", max_length=40)]
"""A merchant slug, e.g. "mega_image" (D47; C1's data/merchants.json)."""
Mcc = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}$")]
"""An ISO 18245 merchant category code: 4 digits as text (0742 keeps its 0)."""
Timestamp = Annotated[AwareDatetime, BeforeValidator(_timestamp_input)]
"""A tz-aware instant: an aware datetime or an ISO-8601 string with an offset (never Unix time)."""
Text80 = Annotated[str, StringConstraints(min_length=1, max_length=80), AfterValidator(_not_blank)]
Text200 = Annotated[
    str, StringConstraints(min_length=1, max_length=200), AfterValidator(_not_blank)
]
Text300 = Annotated[
    str, StringConstraints(min_length=1, max_length=300), AfterValidator(_not_blank)
]
Text500 = Annotated[
    str, StringConstraints(min_length=1, max_length=500), AfterValidator(_not_blank)
]
"""Texts kept exactly as given: at most N characters, not only whitespace (they reach prompts)."""
PositiveMoney = Annotated[Money, Field(gt=0)]
NonNegMoney = Annotated[Money, Field(ge=0)]
Ratio = Annotated[float, BeforeValidator(_not_bool), Field(ge=0, le=1, allow_inf_nan=False)]
"""A score, confidence or probability in [0, 1]."""
Factor = Annotated[
    Decimal,
    BeforeValidator(to_decimal),
    PlainSerializer(decimal_to_json, return_type=float, when_used="json"),
    WithJsonSchema({"type": "number"}),
]
"""An exact Decimal that multiplies money (a multiplier, a household scale); a JSON number."""


# ── transactions & the merchant catalogue ───────────────────────────────────────────────────


class Item(DomainModel):
    """A receipt line (arch 4.4 `transactions.items`, D32)."""

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    qty: Annotated[int, Field(ge=1, strict=True)] = 1
    amount: NonNegMoney | None = None


class TxView(DomainModel):
    """A transaction as the cores read it (arch 4.1 + 4.4 columns; §15 calls it `Transaction`).

    `category` is None only before the first evaluation of a transaction that came without a
    script category (arch F2, Q8); every resolved one has it.
    """

    id: Id
    occurred_at: Timestamp
    merchant_raw: Text200  # B8's ingest limit
    merchant: Text80 | None = None  # a canonical name (Merchant's limit)
    merchant_id: MerchantId | None = None
    mcc: Mcc | None = None
    category: Category | None = None
    direction: Direction
    amount: PositiveMoney
    effective_amount: NonNegMoney
    items: tuple[Item, ...] | None = None  # None = no item data (D32), () = an empty receipt
    description: Text500 | None = None
    purpose: Purpose | None = None
    beneficiary: Beneficiary | None = None
    annotation_source: AnnotationSource | None = None
    annotation_confidence: Ratio | None = None
    explanation: Text300 | None = None  # the "because"
    decision: Decision | None = None
    life_fit: Ratio | None = None
    anomaly_score: Ratio | None = None
    unexplained: Ratio | None = None
    matched_fact_id: Id | None = None
    matched_rule_id: Id | None = None
    pot_id: Id | None = None
    receivable_id: Id | None = None
    status: TxStatus | None = None  # bomboe's services fill it (the queue state)
    source: TxSource | None = None

    @model_validator(mode="after")
    def _effective_within_amount(self) -> Self:
        if self.effective_amount > self.amount:
            raise ValueError(
                f"effective_amount {self.effective_amount} must not exceed amount {self.amount}"
            )
        return self


class Merchant(DomainModel):
    """A merchant of the catalogue (arch 4.4 `merchants`; C1's data/merchants.json)."""

    id: MerchantId
    canonical_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
    ]
    aliases: Annotated[
        tuple[Annotated[str, StringConstraints(min_length=3, max_length=60)], ...],
        Field(min_length=1),
        AfterValidator(_unique),
    ]
    category: Category
    mcc: Mcc
    typical_basket: PositiveMoney
    multi_category: bool = False


# ── life facts (arch 4.4 life_facts, 5.3.2; one value shape per FactType: plan step 4) ──────


def _sorted_unique(values: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(sorted(set(values)))


Weekdays = Annotated[
    tuple[Annotated[int, Field(ge=1, le=7, strict=True)], ...], AfterValidator(_sorted_unique)
]
"""ISO weekdays (Mon = 1 … Sun = 7), sorted and unique."""
Months = Annotated[
    tuple[Annotated[int, Field(ge=1, le=12, strict=True)], ...], AfterValidator(_sorted_unique)
]
SmallCount = Annotated[int, Field(ge=1, le=1000, strict=True)]


class OccupationValue(DomainModel):
    title: Text200
    work_mode: Text80 | None = None
    employer: Text80 | None = None  # bomboe's F2 field


class EmploymentValue(DomainModel):
    kind: Text80  # employee, freelancer, student, part_time, …


class IncomePatternValue(DomainModel):
    irregular: StrictBool  # E8 bootstraps income from history when true
    note: Text300 | None = None


class HouseholdMemberValue(DomainModel):
    """Another person in the household (the user is implicit: alone = scale 1.0, E6)."""

    role: HouseholdRole
    age: Annotated[int, Field(ge=0, le=120, strict=True)] | None = None
    relation: Text80 | None = None

    @model_validator(mode="after")
    def _child_needs_age(self) -> Self:
        if self.role is HouseholdRole.CHILD and self.age is None:
            raise ValueError("a child needs an age")
        return self


class PetValue(DomainModel):
    species: Text80
    count: SmallCount = 1


class HousingValue(DomainModel):
    kind: Text80  # rent, own, shared_flat, with_parents, …
    note: Text300 | None = None


class CityValue(DomainModel):
    name: Text80


class VehicleValue(DomainModel):
    kind: Text80 = "car"
    fuel: Text80 | None = None  # bomboe's F2 field


class CommuteValue(DomainModel):
    mode: Text80


class ActivityValue(DomainModel):
    name: Text80
    per_week: SmallCount | None = None


class SocialPatternValue(DomainModel):
    name: Text80
    weekdays: Weekdays = ()


class LifeEventValue(DomainModel):
    name: Text80
    date: Date | None = None
    months: Months = ()


class RhythmValue(DomainModel):
    name: Text80
    weekdays: Weekdays = ()


class PriorityValue(DomainModel):
    category: Text80  # free text ("concerts" isn't a Category); C4 maps it to a protects signature
    priority: PriorityLevel
    label: Text80 | None = None  # bomboe's F2 field (a display label)


class CustomValue(DomainModel):
    description: Text300


FactValue = (
    OccupationValue | EmploymentValue | IncomePatternValue | HouseholdMemberValue | PetValue
    | HousingValue | CityValue | VehicleValue | CommuteValue | ActivityValue | SocialPatternValue
    | LifeEventValue | RhythmValue | PriorityValue | CustomValue
)  # fmt: skip
FACT_VALUE_MODELS: Final[Mapping[FactType, type[DomainModel]]] = MappingProxyType(
    {
        FactType.OCCUPATION: OccupationValue,
        FactType.EMPLOYMENT: EmploymentValue,
        FactType.INCOME_PATTERN: IncomePatternValue,
        FactType.HOUSEHOLD_MEMBER: HouseholdMemberValue,
        FactType.PET: PetValue,
        FactType.HOUSING: HousingValue,
        FactType.CITY: CityValue,
        FactType.VEHICLE: VehicleValue,
        FactType.COMMUTE: CommuteValue,
        FactType.ACTIVITY: ActivityValue,
        FactType.SOCIAL_PATTERN: SocialPatternValue,
        FactType.LIFE_EVENT: LifeEventValue,
        FactType.RHYTHM: RhythmValue,
        FactType.PRIORITY: PriorityValue,
        FactType.CUSTOM: CustomValue,
    }
)
"""The value model of each fact type: `LifeFact.value` is validated with the one for its `type`."""


class Evidence(DomainModel):
    message_ids: tuple[Id, ...] = ()
    transaction_ids: tuple[Id, ...] = ()


class LifeFactDraft(DomainModel):
    """A life fact before it's saved (§15 `infer_hypotheses`, the add_life_fact handler)."""

    type: FactType
    value: FactValue
    text: Text500  # the user's own words
    source: FactSource
    status: FactStatus
    confidence: Ratio
    persistence: Persistence
    valid_from: Date
    valid_to: Date | None = None
    evidence: Evidence = Evidence()

    @field_validator("value", mode="before")
    @classmethod
    def _value_for_type(cls, value: object, info: ValidationInfo) -> object:
        model = FACT_VALUE_MODELS.get(info.data.get("type"))  # type: ignore[arg-type]
        if model is None:  # the type itself failed: its error is reported
            return value
        if isinstance(value, BaseModel) and not isinstance(value, model):
            raise ValueError(f"value must be {model.__name__} for type {info.data['type']}")
        return model.model_validate(value)

    @model_validator(mode="after")
    def _validity_window(self) -> Self:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not be before valid_from")
        if self.persistence is Persistence.TEMPORARY and self.valid_to is None:
            raise ValueError("temporary facts need valid_to")
        return self

    def active_on(self, day: Date) -> bool:
        """Inside its validity window on `day` (both ends inclusive)."""
        return self.valid_from <= day and (self.valid_to is None or day <= self.valid_to)


class LifeFact(LifeFactDraft):
    """A saved life fact (arch 4.4 `life_facts`, 9.3 LifeFact)."""

    id: Id
    created_at: Timestamp  # C5's tie-break: the most recent fact


# ── signatures & learned rules (arch 4.4, 5.3.3, 5.3.7) ─────────────────────────────────────


def _whole_minutes(value: time) -> time:
    if value.second or value.microsecond or value.tzinfo is not None:
        raise ValueError("a time of day is whole minutes, no zone (HH:MM)")
    return value


HourMinute = Annotated[
    time,
    AfterValidator(_whole_minutes),
    PlainSerializer(lambda t: t.strftime("%H:%M"), return_type=str, when_used="json"),
]
"""A time of day in whole minutes; "HH:MM" in JSON (arch 4.4 time windows)."""
NonNegMoneyOrNone = NonNegMoney | None


class _TimeFilter(DomainModel):
    weekdays: Weekdays = ()
    from_: HourMinute | None = Field(default=None, alias="from")
    to: HourMinute | None = None

    @model_validator(mode="after")
    def _from_before_to(self) -> Self:
        if (self.from_ is None) != (self.to is None):
            raise ValueError("from and to come together")
        if self.from_ is not None and self.to is not None and self.from_ >= self.to:
            raise ValueError("from must be before to (no window across midnight)")
        return self


class TimeWindow(_TimeFilter):
    """When a signature applies: weekdays + from/to and/or months (arch 4.4)."""

    months: Months = ()


def _min_not_above_max(low: Decimal | None, high: Decimal | None) -> None:
    if low is not None and high is not None and low > high:
        raise ValueError("amount_min must not exceed amount_max")


class Signature(DomainModel):
    """What a life fact predicts about spending (arch 4.4 `spending_signatures`, 5.3.3)."""

    id: Id | None = None  # None until saved
    fact_id: Id | None = None  # None for a library entry not yet tied to a fact
    effect: SignatureEffect
    category: Category | None = None
    merchant_hints: tuple[Text80, ...] = ()
    item_keywords: tuple[Text80, ...] = ()
    amount_min: NonNegMoneyOrNone = None
    amount_max: NonNegMoneyOrNone = None
    multiplier: Annotated[Factor, Field(gt=0)] | None = None
    time_window: TimeWindow | None = None
    expected_date: Date | None = None
    expected_amount: PositiveMoney | None = None
    replacement_cycle_days: Annotated[int, Field(ge=1, le=36500, strict=True)] | None = None
    purpose: Purpose
    strength: Ratio
    origin: SignatureOrigin  # no default: a Claude signature must never pass as library
    active: StrictBool = True

    @model_validator(mode="after")
    def _rules(self) -> Self:
        _min_not_above_max(self.amount_min, self.amount_max)
        targeted = self.category is not None or bool(self.merchant_hints)
        if self.effect in (SignatureEffect.EXPLAINS, SignatureEffect.PROTECTS) and not targeted:
            raise ValueError(f"{self.effect} needs a category or merchant hints")
        if self.effect is SignatureEffect.SCALES_BASELINE and (
            self.category is None or self.multiplier is None
        ):
            raise ValueError("scales_baseline needs a category and a multiplier")
        if self.effect is SignatureEffect.EXPECTS_EVENT:
            months = self.time_window.months if self.time_window else ()
            if self.expected_amount is None or (self.expected_date is None and not months):
                raise ValueError("expects_event needs expected_amount and a date or months")
        if self.category is Category.HEALTH_PHARMACY:
            raise ValueError("no signature may target health_pharmacy (sensitive, arch 4.5)")
        return self


class RuleMatch(_TimeFilter):
    """What a learned rule matches (arch 4.4 `pattern_rules.match`)."""

    merchant_id: MerchantId | None = None
    category: Category | None = None
    amount_min: NonNegMoneyOrNone = None
    amount_max: NonNegMoneyOrNone = None

    @model_validator(mode="after")
    def _rules(self) -> Self:
        _min_not_above_max(self.amount_min, self.amount_max)
        if self.merchant_id is None and self.category is None:
            raise ValueError("a rule matches a merchant or a category (else it matches everything)")
        return self


class RuleOutcome(DomainModel):
    """What a classify rule decides (arch 4.4 `pattern_rules.outcome`); empty for suppress."""

    purpose: Purpose | None = None
    label: Text80 | None = None
    own_share_ratio: Annotated[Factor, Field(ge=0, le=1)] | None = None
    beneficiary: Beneficiary | None = None  # bomboe's F2 field


class PatternRule(DomainModel):
    """A learned or explicit rule (arch 4.4 `pattern_rules`, 5.3.7)."""

    id: Id | None = None  # None until saved
    kind: RuleKind
    match: RuleMatch
    outcome: RuleOutcome = RuleOutcome()
    confidence: Ratio
    hits: Annotated[int, Field(ge=0, strict=True)] = 0
    misses: Annotated[int, Field(ge=0, strict=True)] = 0
    source: RuleSource
    active: StrictBool = True
    created_at: Timestamp
    last_hit_at: Timestamp | None = None

    @model_validator(mode="after")
    def _classify_needs_purpose(self) -> Self:
        if self.kind is RuleKind.CLASSIFY and self.outcome.purpose is None:
            raise ValueError("a classify rule needs outcome.purpose")
        return self


# ── plan & money rows (arch 4.1, 4.2, 4.4, 6.7, 9.3) ────────────────────────────────────────

DayOfMonth = Annotated[int, Field(ge=1, le=31, strict=True)]
WeekdayName = Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAY_NAMES: Final[tuple[WeekdayName, ...]] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
Weight = Annotated[Factor, Field(ge=Decimal("0.5"), le=Decimal("3"))]


class Receivable(DomainModel):
    """Money others owe the user (arch 4.4 `receivables`, 9.3 Receivable)."""

    id: Id
    transaction_id: Id | None = None
    amount: PositiveMoney
    debtor_label: Text80  # "colegi", "Andrei"
    people_count: SmallCount | None = None
    amount_each: NonNegMoneyOrNone = None
    expected_by: Date
    status: ReceivableStatus
    requested_at: Timestamp | None = None
    paid_at: Timestamp | None = None
    created_at: Timestamp


class Pot(DomainModel):
    """A named savings pot (arch 4.4 `pots`, 9.3 Pot); the goal has its own."""

    id: Id
    name: Text80
    kind: PotKind
    goal_id: Id | None = None
    life_event_id: Id | None = None
    fact_id: Id | None = None
    target: PositiveMoney
    saved: NonNegMoney
    deadline: Date | None = None
    monthly_contribution: NonNegMoney = Decimal("0")
    status: PotStatus


class Goal(DomainModel):
    """The user's goal (arch 4.1 `goals`; one active at a time, D17)."""

    id: Id
    amount: PositiveMoney
    deadline: Date
    motivation: Text300 | None = None
    status: GoalStatus
    created_at: Timestamp
    soft: StrictBool = (
        True  # the deadline may move (bomboe's `goals.soft`; E9 moves soft ones only)
    )


class IncomeSource(DomainModel):
    id: Id
    source: Text80
    amount: PositiveMoney
    day_of_month: DayOfMonth  # day 31 in a short month is E1's job


class FixedCost(DomainModel):
    id: Id
    name: Text80
    amount: PositiveMoney
    day_of_month: DayOfMonth


class LifeEvent(DomainModel):
    """A planned event with a cost (arch 4.1 `life_events`)."""

    id: Id
    name: Text80
    date: Date
    est_cost: NonNegMoney
    type: LifeEventType
    status: LifeEventStatus = LifeEventStatus.PLANNED


class PlanPreferences(DomainModel):
    """How the user shaped the budget (arch 6.7 `plan_preferences`); defaults = no preference."""

    weekday_weights: Mapping[WeekdayName, Weight] = Field(
        default_factory=lambda: dict.fromkeys(WEEKDAY_NAMES, Decimal("1"))
    )
    pinned_days: Mapping[Date, NonNegMoney] = Field(default_factory=dict)
    category_caps: Mapping[Category, NonNegMoney] = Field(default_factory=dict)  # per week
    buffer_pct: Annotated[Factor, Field(ge=0, le=Decimal("0.3"))] = Decimal("0.10")

    @field_validator("weekday_weights", mode="before")
    @classmethod
    def _every_weekday(cls, value: object) -> object:
        if isinstance(value, Mapping):  # a partial shape_budget input: the rest weigh 1
            return {day: value.get(day, Decimal("1")) for day in WEEKDAY_NAMES} | dict(value)
        return value


class Baseline(DomainModel):
    """A category's expected spending (arch 4.4 `category_baselines`, 5.3.5; E6's output)."""

    category: Category
    personal_median: NonNegMoney
    personal_mad: NonNegMoney
    n: Annotated[int, Field(ge=0, strict=True)]
    prior_median: NonNegMoney
    household_multiplier: Annotated[Factor, Field(gt=0)]
    expected_median: NonNegMoney
    monthly_expected: NonNegMoney


class Transfer(DomainModel):
    """A move to savings (arch 4.2 `transfers`; §15 `auto_save` returns one)."""

    id: Id
    amount: PositiveMoney
    kind: TransferKind
    pot_id: Id | None = None
    income_transaction_id: Id | None = None
    created_at: Timestamp
    undone_at: Timestamp | None = None


# ── the rows of the user context (arch 4.1, 4.2, 4.4, 6.5) ──────────────────────────────────


class UserProfile(DomainModel):
    # bomboe's services fill the users row id (`current_user`); 0 = not a stored user (pure tests).
    id: Annotated[int, Field(ge=0, le=2**63 - 1, strict=True)] = 0
    name: Text80
    age: Annotated[int, Field(ge=0, le=120, strict=True)] | None = None
    language: Language
    coach_style: CoachStyle
    household_scale: Annotated[Factor, Field(gt=0)] = Decimal("1")
    city: Text80 | None = None  # from the city fact (users has no city column)
    timezone: Text80 = "Europe/Bucharest"
    onboarded_at: Timestamp | None = None


class Account(DomainModel):
    """No account row yet → zeros (bomboe's B4 builds `Account()` for a fresh user)."""

    current_balance: Money = Decimal("0")  # may be negative
    savings_pot: NonNegMoney = Decimal("0")


class AgentEventView(DomainModel):
    """An agent event (arch 4.1 + 4.4 `agent_events`)."""

    id: Id
    type: AgentEventType
    status: AgentEventStatus
    payload: Mapping[str, JsonValue] = Field(default_factory=dict)
    ref_transaction_id: Id | None = None
    event_date: Date | None = None  # bomboe's dedup day (day-level types are unique per day)
    created_at: Timestamp
    asked_at: Timestamp | None = None
    answered_at: Timestamp | None = None
    handled_at: Timestamp | None = None


class LedgerDay(DomainModel):
    date: Date
    budget: Money
    spent: NonNegMoney
    status: LedgerStatus


class Slip(DomainModel):
    date: Date
    amount_over: NonNegMoney
    reason: Text300  # free text: the user's own words
    detail: Text500 | None = None
    recurring: StrictBool = False


class Reflection(DomainModel):
    week_start: Date
    motivation: Annotated[int, Field(ge=1, le=5, strict=True)] | None = None
    answer: Text500 | None = None
    reason: Text300 | None = None


class Product(DomainModel):
    """A mock savings product (arch 4.4 `products`)."""

    id: MerchantId  # a slug (data/products.json, products.id TEXT), like the merchants' ids
    name: Text80
    kind: ProductKind
    rate: Annotated[Factor, Field(ge=0)]
    liquidity: Liquidity
    min_months: Annotated[int, Field(ge=0, strict=True)]
    max_months: Annotated[int, Field(ge=1, strict=True)]
    mock: StrictBool = True
    description: Text300 | None = None

    @model_validator(mode="after")
    def _months(self) -> Self:
        if self.min_months >= self.max_months:
            raise ValueError("min_months must be below max_months")
        return self


# ── bomboe's API views (B6a: messages and notifications as the API returns them) ─────────────


class MessageView(DomainModel):
    """A chat message as the API returns it (arch 9.3)."""

    id: Id
    role: MessageRole
    content: Annotated[str, StringConstraints(max_length=8000)]
    quick_replies: tuple[Text80, ...] = ()
    action_cards: tuple[Mapping[str, JsonValue], ...] = ()
    input_mode: InputMode | None = None
    speak: StrictBool = False
    speak_text: Text300 | None = None
    ref_transaction_id: Id | None = None
    agent_event_id: Id | None = None
    created_at: Timestamp


class NotificationView(DomainModel):
    """An in-app notification (arch 4.1 `notifications`, B13)."""

    id: Id
    type: Text80
    title: Text200
    body: Text500
    read: StrictBool = False
    opens_chat: StrictBool = False
    agent_event_id: Id | None = None
    message_id: Id | None = None
    created_at: Timestamp
