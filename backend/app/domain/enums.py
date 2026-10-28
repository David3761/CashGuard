"""Every fixed list, with values exactly as in arch 4.4 / 4.5.

These strings are stored in the DB (CHECK constraints are generated from them) and sent in JSON,
so adding a value here is the one-line change that updates both.
"""

from enum import StrEnum


class Category(StrEnum):
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


class Purpose(StrEnum):
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


class Beneficiary(StrEnum):
    SELF = "self"
    HOUSEHOLD = "household"
    SHARED = "shared"
    OTHERS = "others"
    EMPLOYER = "employer"


class Decision(StrEnum):
    IGNORE = "ignore"
    AUTO = "auto"
    INFORM = "inform"
    ASK = "ask"
    ASK_LATER = "ask_later"


class Direction(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class FactType(StrEnum):
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


class FactStatus(StrEnum):
    HYPOTHESIS = "hypothesis"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"


class FactSource(StrEnum):
    ONBOARDING = "onboarding"
    CHAT = "chat"
    VOICE = "voice"
    USER_EDIT = "user_edit"
    INFERRED = "inferred"
    SEED = "seed"


class Persistence(StrEnum):
    PERMANENT = "permanent"
    TEMPORARY = "temporary"
    RECURRING = "recurring"


class SignatureEffect(StrEnum):
    EXPLAINS = "explains"
    SCALES_BASELINE = "scales_baseline"
    EXPECTS_EVENT = "expects_event"
    PROTECTS = "protects"


class SignatureOrigin(StrEnum):
    LIBRARY = "library"
    LLM = "llm"


class RuleKind(StrEnum):
    CLASSIFY = "classify"
    SUPPRESS = "suppress"


class RuleSource(StrEnum):
    ANSWER = "answer"
    EXPLICIT = "explicit"
    LEARNED = "learned"


class ReceivableStatus(StrEnum):
    OPEN = "open"
    REQUESTED = "requested"
    PAID = "paid"
    CANCELLED = "cancelled"


class PotKind(StrEnum):
    GOAL = "goal"
    EVENT = "event"
    EMERGENCY = "emergency"
    CUSTOM = "custom"


class PotStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CLOSED = "closed"


class AnnotationSource(StrEnum):
    AUTO = "auto"
    RULE = "rule"
    FACT = "fact"
    POT = "pot"
    ANSWER = "answer"
    USER_EDIT = "user_edit"
    DEFAULT = "default"


class InputMode(StrEnum):
    TEXT = "text"
    VOICE = "voice"
    QUICK_REPLY = "quick_reply"


class AgentEventType(StrEnum):
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


class AgentEventStatus(StrEnum):
    PENDING = "pending"
    ASKED = "asked"
    ANSWERED = "answered"
    HANDLED = "handled"
    EXPIRED = "expired"


class Language(StrEnum):
    RO = "ro"
    EN = "en"


class CoachStyle(StrEnum):
    WARM = "warm"
    DIRECT = "direct"


class TransferKind(StrEnum):
    MANUAL = "manual"
    AUTO_SAVE = "auto_save"


class ProductKind(StrEnum):
    FLEXIBLE_POT = "flexible_pot"
    SAVINGS_ACCOUNT = "savings_account"
    TERM_DEPOSIT = "term_deposit"


class Liquidity(StrEnum):
    INSTANT = "instant"
    NOTICE = "notice"
    LOCKED = "locked"


# ── Lists the F2 spec doesn't name but the schema (arch 4.1 / 4.2) needs ──────────────────


class TransactionStatus(StrEnum):
    UNRESOLVED = "unresolved"
    PROCESSING = "processing"
    RESOLVED = "resolved"
    FAILED = "failed"


class TransactionSource(StrEnum):
    SEED = "seed"
    SIM = "sim"


class GoalStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"


class LifeEventType(StrEnum):
    TRIP = "trip"
    GIFT = "gift"
    SOCIAL = "social"
    PURCHASE = "purchase"
    EDUCATION = "education"
    OTHER = "other"


class LifeEventStatus(StrEnum):
    PLANNED = "planned"
    DONE = "done"
    CANCELLED = "cancelled"


class LedgerStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
    OVERSPENT = "overspent"
    UNDER = "under"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class AgentTrigger(StrEnum):
    CHAT = "chat"
    PROACTIVE = "proactive"


class AgentRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ToolCallStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
