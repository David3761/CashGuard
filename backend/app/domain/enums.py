"""Fixed value lists (arch 4.1 / 4.2 / 4.4 / 4.5, 6.2, 9.3; work-breakdown F2).

The values are stored in the DB (B2 builds its CHECK constraints from these enums) and sent in JSON,
so they are part of the contract: never rename one. `StrEnum` makes `str()`, f-strings and
`json.dumps` give the value; `@unique` makes a duplicate value an import error instead of an alias.

Values are unique *within* an enum, not across enums: e.g. `Decision.AUTO == AnnotationSource.AUTO`
and `PotStatus.ACTIVE == GoalStatus.ACTIVE`, so they are equal dict and set keys. A map that mixes
enums must key by `(type(member), member)`. The tests list every overlap, so a new one is a
conscious decision.

The fixed sets are tuples in the doc's order. A frozenset of strings iterates in hash order, which
changes per process (PYTHONHASHSEED), and snapshots and prompt caching need a stable order.
`in` works with members and with the plain strings read from the DB.

Deliberately left without an enum (decided 2026-10-29):
- `life_events.source` (4.1, no list) uses the `FactSource` values: events come from the same
  places as facts (onboarding, chat, voice, user edits, inference, the seed).
- `slips.reason` is free text: the user's own words.
- `notifications.type` (B13), `agent_runs.trigger` / `status` and `tool_calls.status` (B15, A6)
  belong to their owners; the occupation `work_mode` is free text inside the fact value.
"""

from enum import StrEnum, unique
from typing import Final

# ── transactions, users, products (arch 4.2 / 4.4 / 4.5) ────────────────────────────────────


@unique
class Category(StrEnum):
    """Transaction categories (arch 4.5)."""

    GROCERIES = "groceries"
    RESTAURANTS = "restaurants"
    FOOD_DELIVERY = "food_delivery"
    TRANSPORT = "transport"
    FUEL = "fuel"
    ELECTRONICS = "electronics"
    CLOTHING = "clothing"
    SPORT = "sport"
    HEALTH_PHARMACY = "health_pharmacy"
    KIDS = "kids"
    EDUCATION = "education"
    BOOKS = "books"
    ENTERTAINMENT = "entertainment"
    SUBSCRIPTIONS = "subscriptions"
    TRAVEL = "travel"
    HOUSING_RENT = "housing_rent"
    UTILITIES = "utilities"
    TELECOM = "telecom"
    GIFTS = "gifts"
    PETS = "pets"
    HOUSEHOLD_GOODS = "household_goods"
    PERSONAL_CARE = "personal_care"
    TRANSFERS = "transfers"
    INCOME = "income"
    SAVINGS = "savings"
    OTHER = "other"


@unique
class Purpose(StrEnum):
    """Why money was spent; replaces "good / bad" (arch 4.5)."""

    ESSENTIAL_LIVING = "essential_living"
    HOUSEHOLD_CARE = "household_care"
    WORK_TOOL = "work_tool"
    SELF_INVESTMENT = "self_investment"
    IDENTITY_JOY = "identity_joy"
    SOCIAL_CONNECTION = "social_connection"
    PLANNED_EVENT = "planned_event"
    ON_BEHALF_OF_OTHERS = "on_behalf_of_others"
    UNPLANNED_DISCRETIONARY = "unplanned_discretionary"
    EMERGENCY = "emergency"
    UNKNOWN = "unknown"


@unique
class Beneficiary(StrEnum):
    """Who a transaction was for (arch 4.4 `transactions.beneficiary`)."""

    SELF = "self"
    HOUSEHOLD = "household"
    SHARED = "shared"
    OTHERS = "others"
    EMPLOYER = "employer"


@unique
class Decision(StrEnum):
    """What evaluating a transaction decided (arch 4.4 `transactions.decision`, 5.3.4, 5.3.6)."""

    IGNORE = "ignore"
    AUTO = "auto"
    INFORM = "inform"
    ASK = "ask"
    ASK_LATER = "ask_later"


@unique
class Direction(StrEnum):
    """Money out or in (arch 4.4 `transactions.direction`)."""

    DEBIT = "debit"
    CREDIT = "credit"


@unique
class AnnotationSource(StrEnum):
    """Where a transaction's reading came from (arch 4.4 `transactions.annotation_source`)."""

    AUTO = "auto"
    RULE = "rule"
    FACT = "fact"
    POT = "pot"
    ANSWER = "answer"
    USER_EDIT = "user_edit"
    DEFAULT = "default"


@unique
class Language(StrEnum):
    """The user's language (arch 4.2 `users.language`, D15)."""

    RO = "ro"
    EN = "en"


@unique
class CoachStyle(StrEnum):
    """Wording only, never the judgment (arch 4.4 `users.coach_style`, D33)."""

    WARM = "warm"
    DIRECT = "direct"


@unique
class ProductKind(StrEnum):
    """Mock savings products (arch 4.4 `products.kind`)."""

    FLEXIBLE_POT = "flexible_pot"
    SAVINGS_ACCOUNT = "savings_account"
    TERM_DEPOSIT = "term_deposit"


@unique
class Liquidity(StrEnum):
    """How fast a product's money can be reached (arch 4.4 `products.liquidity`)."""

    INSTANT = "instant"
    NOTICE = "notice"
    LOCKED = "locked"


# ── life context (arch 4.4) ──────────────────────────────────────────────────────────────────


@unique
class FactType(StrEnum):
    """What a life fact is about (arch 4.4 `life_facts.type`). No sensitive type exists (4.5)."""

    OCCUPATION = "occupation"
    EMPLOYMENT = "employment"
    INCOME_PATTERN = "income_pattern"
    HOUSEHOLD_MEMBER = "household_member"
    PET = "pet"
    HOUSING = "housing"
    CITY = "city"
    VEHICLE = "vehicle"
    COMMUTE = "commute"
    ACTIVITY = "activity"
    SOCIAL_PATTERN = "social_pattern"
    LIFE_EVENT = "life_event"
    RHYTHM = "rhythm"
    PRIORITY = "priority"
    CUSTOM = "custom"


@unique
class FactSource(StrEnum):
    """Where a life fact came from (arch 4.4 `life_facts.source`, 5.3.2).

    Also the values of `life_events.source` (arch 4.1 lists none of its own).
    """

    ONBOARDING = "onboarding"
    CHAT = "chat"
    VOICE = "voice"
    USER_EDIT = "user_edit"
    INFERRED = "inferred"
    SEED = "seed"


@unique
class FactStatus(StrEnum):
    """A life fact's state (arch 4.4 `life_facts.status`)."""

    HYPOTHESIS = "hypothesis"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"


@unique
class Persistence(StrEnum):
    """How long a life fact holds (arch 4.4 `life_facts.persistence`)."""

    PERMANENT = "permanent"
    TEMPORARY = "temporary"
    RECURRING = "recurring"


@unique
class HouseholdRole(StrEnum):
    """A household member's role (work-breakdown F2 rule; arch 4.4 `life_facts.value`)."""

    ADULT = "adult"
    CHILD = "child"


@unique
class PriorityLevel(StrEnum):
    """A priority fact's level: a deliberate closed set (David G.'s design).

    Derived from the two arch 4.4 `life_facts.value` examples: protected = never cut (E9 never
    suggests it), reduce = the user wants to cut it.
    """

    PROTECTED = "protected"
    REDUCE = "reduce"


@unique
class SignatureEffect(StrEnum):
    """What a fact predicts about spending (arch 4.4 `spending_signatures.effect`, 5.3.3)."""

    EXPLAINS = "explains"
    SCALES_BASELINE = "scales_baseline"
    EXPECTS_EVENT = "expects_event"
    PROTECTS = "protects"


@unique
class SignatureOrigin(StrEnum):
    """Who wrote a signature (arch 4.4 `spending_signatures.origin`): the library wins (5.3.3)."""

    LIBRARY = "library"
    LLM = "llm"


@unique
class RuleKind(StrEnum):
    """A learned rule's kind (arch 4.4 `pattern_rules.kind`): suppress = "nu mai întreba"."""

    CLASSIFY = "classify"
    SUPPRESS = "suppress"


@unique
class RuleSource(StrEnum):
    """Where a learned rule came from (arch 4.4 `pattern_rules.source`, 5.3.7)."""

    ANSWER = "answer"
    EXPLICIT = "explicit"
    LEARNED = "learned"


# ── money & plan (arch 4.1 / 4.2 / 4.4, 6.2) ────────────────────────────────────────────────


@unique
class TxStatus(StrEnum):
    """A transaction's place in the processing queue (arch 4.1 `transactions.status`, D4)."""

    UNRESOLVED = "unresolved"
    PROCESSING = "processing"
    RESOLVED = "resolved"
    FAILED = "failed"


@unique
class TxSource(StrEnum):
    """Seeded history or a live simulator transaction (arch 4.2 `transactions.source`)."""

    SEED = "seed"
    SIM = "sim"


TransactionStatus = TxStatus
"""bomboe's name for `TxStatus` (compat alias: the same enum)."""
TransactionSource = TxSource
"""bomboe's name for `TxSource` (compat alias: the same enum)."""


@unique
class LedgerStatus(StrEnum):
    """A day's spending against its budget (arch 4.1 `day_ledger.status`)."""

    OK = "ok"
    WARNING = "warning"
    OVERSPENT = "overspent"
    UNDER = "under"


@unique
class ReceivableStatus(StrEnum):
    """Money others owe the user (arch 4.4 `receivables.status`)."""

    OPEN = "open"
    REQUESTED = "requested"
    PAID = "paid"
    CANCELLED = "cancelled"


@unique
class PotKind(StrEnum):
    """A named savings pot's kind (arch 4.4 `pots.kind`)."""

    GOAL = "goal"
    EVENT = "event"
    EMERGENCY = "emergency"
    CUSTOM = "custom"


@unique
class PotStatus(StrEnum):
    """A pot's state (arch 4.4 `pots.status`)."""

    ACTIVE = "active"
    COMPLETED = "completed"
    CLOSED = "closed"


@unique
class GoalStatus(StrEnum):
    """One active goal per user; finished ones stay completed (arch 4.2 `goals.status`, D17)."""

    ACTIVE = "active"
    COMPLETED = "completed"


@unique
class LifeEventType(StrEnum):
    """A planned event's type (arch 6.2 `add_life_event` schema)."""

    TRIP = "trip"
    GIFT = "gift"
    SOCIAL = "social"
    PURCHASE = "purchase"
    EDUCATION = "education"
    OTHER = "other"


@unique
class LifeEventStatus(StrEnum):
    """A planned event's state (arch 4.2 `life_events.status`)."""

    PLANNED = "planned"
    DONE = "done"
    CANCELLED = "cancelled"


@unique
class TransferKind(StrEnum):
    """A move to savings (arch 4.2 `transfers.kind`); auto_save on payday (D37)."""

    MANUAL = "manual"
    AUTO_SAVE = "auto_save"


# ── agent & chat (arch 4.1 / 4.4, 9.3) ──────────────────────────────────────────────────────


@unique
class AgentEventType(StrEnum):
    """Why the agent should speak up (arch 4.1 `agent_events` types + the 4.4 new types)."""

    OVERSPEND = "overspend"
    WARNING = "warning"
    UNDERSPEND_WEEK = "underspend_week"
    LIFE_CHANGE = "life_change"
    INFEASIBLE_PLAN = "infeasible_plan"
    WEEKLY_REFLECTION = "weekly_reflection"
    PREEMPTIVE_CHECKIN = "preemptive_checkin"
    GOAL_COMPLETED = "goal_completed"
    CATEGORY_CAP = "category_cap"
    TRANSACTION_QUESTION = "transaction_question"
    HYPOTHESIS_CHECK = "hypothesis_check"
    RECEIVABLE_REMINDER = "receivable_reminder"


@unique
class AgentEventStatus(StrEnum):
    """An agent event's lifecycle: pending → asked → answered / handled / expired (arch 4.4)."""

    PENDING = "pending"
    ASKED = "asked"
    ANSWERED = "answered"
    HANDLED = "handled"
    EXPIRED = "expired"


@unique
class InputMode(StrEnum):
    """How a chat message was entered (arch 4.4 `messages.input_mode`, 9.1 Voice)."""

    TEXT = "text"
    VOICE = "voice"
    QUICK_REPLY = "quick_reply"


@unique
class MessageRole(StrEnum):
    """Who wrote a chat message (arch 4.1 `messages.role`, 9.3).

    The `messages` table stores only these two roles: tool calls live in `tool_calls`, and the
    agent loop's tool_result turns are never persisted (decided 2026-10-29).
    """

    USER = "user"
    ASSISTANT = "assistant"


@unique
class AgentTrigger(StrEnum):
    """What started an agent run (arch 4.1 `agent_runs.trigger`; bomboe's B2 CHECK)."""

    CHAT = "chat"
    PROACTIVE = "proactive"


@unique
class AgentRunStatus(StrEnum):
    """An agent run's state (arch 4.1 `agent_runs.status`; bomboe's B2 pick)."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@unique
class ToolCallStatus(StrEnum):
    """A logged tool call's outcome (arch 4.1 `tool_calls.status`)."""

    OK = "ok"
    ERROR = "error"


# ── fixed sets ───────────────────────────────────────────────────────────────────────────────


HOUSEHOLD_SCALED_CATEGORIES: Final[tuple[Category, ...]] = (
    Category.GROCERIES,
    Category.HOUSEHOLD_GOODS,
    Category.HEALTH_PHARMACY,
    Category.UTILITIES,
    Category.KIDS,
    Category.CLOTHING,
    Category.PERSONAL_CARE,
)
"""Categories whose expected spending scales with the household size (arch 4.5, 5.3.5)."""

NEVER_ASKED_CATEGORIES: Final[tuple[Category, ...]] = (Category.HEALTH_PHARMACY,)
"""Categories the agent never asks about (arch 4.5): health is private."""

QUESTION_EVENT_TYPES: Final[tuple[AgentEventType, ...]] = (
    AgentEventType.TRANSACTION_QUESTION,
    AgentEventType.OVERSPEND,
    AgentEventType.WEEKLY_REFLECTION,
    AgentEventType.UNDERSPEND_WEEK,
    AgentEventType.PREEMPTIVE_CHECKIN,
)
"""The event types that use the one question a day (D25; B3, C7 and A7 rely on this list).

- D25 names transaction questions, overspend, the weekly reflection and preemptive check-ins.
- underspend_week counts too (David G., 2026-10-29): it replaces that Sunday's weekly
  reflection and asks "what changed?".
- **Never** counted: receivable_reminder (a statement + a tap card that must never ask, David G.,
  2026-10-29), hypothesis_check (5.3.8), inform cards and goal_completed (WB A7).
"""
