"""Response shapes of arch 9.3. Money is a JSON number (2 dp), dates YYYY-MM-DD, timestamps ISO
UTC with Z, labels already in the user's language."""

import json
from datetime import UTC, date, datetime
from typing import Annotated, Any, Final

from pydantic import AwareDatetime, BaseModel, JsonValue, PlainSerializer, field_validator

from app.domain.base import Money
from app.domain.enums import CoachStyle, Language


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


Timestamp = Annotated[AwareDatetime, PlainSerializer(_utc, return_type=str, when_used="json")]


class Me(BaseModel):
    user_id: int
    name: str
    language: str
    coach_style: str
    onboarded: bool


class MePatch(BaseModel):
    language: Language | None = None
    coach_style: CoachStyle | None = None


class AccountOut(BaseModel):
    current_balance: Money
    savings_pot: Money


class Onboarding(BaseModel):
    goal: bool
    income: bool
    fixed_costs: bool
    life_context: bool
    done: bool


class GoalOut(BaseModel):
    amount: Money
    deadline: date
    motivation: str | None
    progress_pct: float
    days_left: int


class DayOut(BaseModel):
    date: date
    budget: Money
    weight: float
    pinned: bool


class PlanOut(BaseModel):
    version: int
    feasible: bool
    today_budget: Money
    spent_today: Money
    today_status: str
    next_7_days: list[DayOut]


class EventOut(BaseModel):
    id: int
    name: str
    date: date
    est_cost: Money


class ForecastOut(BaseModel):
    probability: float
    previous_probability: float | None
    last_week_probability: float | None
    p10: Money
    p50: Money
    p90: Money
    expected_reach_date: date | None


class PotOut(BaseModel):
    id: int
    name: str
    kind: str
    saved: Money
    target: Money
    monthly_contribution: Money
    deadline: date | None
    status: str


class ReceivableItem(BaseModel):
    id: int
    amount: Money
    debtor_label: str
    status: str


class ReceivablesSummary(BaseModel):
    open_total: Money
    items: list[ReceivableItem]


class PendingQuestion(BaseModel):
    agent_event_id: int
    transaction_id: int | None
    message_id: int | None


class State(BaseModel):
    date: date
    account: AccountOut
    onboarding: Onboarding
    goal: GoalOut | None
    plan: PlanOut | None
    upcoming_events: list[EventOut]
    streak_days: int
    unread_notifications: int
    forecast: ForecastOut | None
    pots: list[PotOut]
    receivables: ReceivablesSummary
    pending_question: PendingQuestion | None
    last_plan_change: str | None


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    quick_replies: list[str]
    speak: bool
    speak_text: str | None
    input_mode: str | None
    ref_transaction_id: int | None
    action_cards: list[dict[str, Any]]
    created_at: Timestamp


class MessagesOut(BaseModel):
    messages: list[MessageOut]


class NotificationOut(BaseModel):
    id: int
    type: str
    title: str
    body: str
    opens_chat: bool
    read: bool
    created_at: Timestamp


class NotificationsOut(BaseModel):
    notifications: list[NotificationOut]


class PlanVersion(BaseModel):
    version: int
    created_at: Timestamp | None
    feasible: bool
    today_budget: Money


class PlanHistory(BaseModel):
    versions: list[PlanVersion]


class TransactionOut(BaseModel):
    id: int
    occurred_at: Timestamp
    merchant: str
    category: str | None
    category_label: str | None
    amount: Money
    effective_amount: Money
    purpose: str | None
    purpose_label: str | None
    explanation: str | None
    decision: str | None
    annotation_source: str | None
    awaiting_answer: bool
    items: list[dict[str, Any]] | None
    receivable_id: int | None
    pot_id: int | None
    status: str


class Scores(BaseModel):
    life_fit: float | None
    anomaly_score: float | None
    unexplained: float | None


class Ref(BaseModel):
    id: int
    text: str | None


class TransactionDetail(TransactionOut):
    scores: Scores
    matched_fact: Ref | None
    matched_rule: Ref | None


class TransactionsOut(BaseModel):
    transactions: list[TransactionOut]


class TransactionPatch(BaseModel):
    purpose: str | None = None
    own_amount: Money | None = None
    people_count: int | None = None


class TransferOut(BaseModel):
    id: int
    amount: Money
    kind: str
    pot_id: int | None
    undone_at: Timestamp | None


class ReceivableOut(BaseModel):
    id: int
    transaction_id: int | None
    amount: Money
    debtor_label: str
    people_count: int | None
    amount_each: Money | None
    expected_by: date
    status: str
    requested_at: Timestamp | None
    paid_at: Timestamp | None


class ReceivablesOut(BaseModel):
    receivables: list[ReceivableOut]


class DriverOut(BaseModel):
    category: str
    category_label: str | None
    pp_per_100_lei: float


class OptionOut(BaseModel):
    label: str
    probability: float
    apply_hint: dict[str, Any]


class HistoryPoint(BaseModel):
    date: date
    probability: float


class ForecastDetail(ForecastOut):
    drivers: list[DriverOut]
    options: list[OptionOut] | None
    history: list[HistoryPoint]


class PotsOut(BaseModel):
    pots: list[PotOut]


class ProductOut(BaseModel):
    id: str
    name: str
    kind: str
    rate: float
    liquidity: str
    why_for_you: str | None


class ProductsOut(BaseModel):
    products: list[ProductOut]


class LifeFactOut(BaseModel):
    id: int
    type: str
    text: str | None
    value: dict[str, Any]
    status: str
    source: str
    confidence: float
    persistence: str
    valid_from: date | None
    valid_to: date | None
    explains: list[str]


class LifeFactsOut(BaseModel):
    facts: list[LifeFactOut]


class LifeFactIn(BaseModel):
    type: str
    value: dict[str, Any]
    text: str | None = None
    persistence: str = "permanent"
    valid_from: date | None = None
    valid_to: date | None = None


class LifeFactPatch(BaseModel):
    value: dict[str, Any] | None = None
    text: str | None = None
    persistence: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None


NOTE_MAX_JSON_CHARS: Final = 2000


class NoteIn(BaseModel):
    """A soft note (`what_works`, …): any small JSON value, e.g. a string or a list of strings.
    Stored as JSONB, so it is bounded: at most NOTE_MAX_JSON_CHARS characters as JSON."""

    value: JsonValue

    @field_validator("value")
    @classmethod
    def _small(cls, value: JsonValue) -> JsonValue:
        if len(json.dumps(value, ensure_ascii=False)) > NOTE_MAX_JSON_CHARS:
            raise ValueError(f"must be at most {NOTE_MAX_JSON_CHARS} characters as JSON")
        return value


class LifeProfileOut(BaseModel):
    life_profile: dict[str, Any]
    plan_preferences: dict[str, Any]
    goal: dict[str, Any] | None
    events: list[EventOut]
    income_sources: list[dict[str, Any]]
    fixed_costs: list[dict[str, Any]]
