"""Fixed value lists (arch 4.4 / 4.5).

The values are stored in the DB (B2 builds its CHECK constraints from these enums) and sent in JSON,
so they are part of the contract: never rename one. `StrEnum` makes `str()`, f-strings and
`json.dumps` give the value; `@unique` makes a duplicate value an import error instead of an alias.
"""

from enum import StrEnum, unique
from typing import Final


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


HOUSEHOLD_SCALED_CATEGORIES: Final[frozenset[Category]] = frozenset(
    {
        Category.GROCERIES,
        Category.HOUSEHOLD_GOODS,
        Category.HEALTH_PHARMACY,
        Category.UTILITIES,
        Category.KIDS,
        Category.CLOTHING,
        Category.PERSONAL_CARE,
    }
)
"""Categories whose expected spending scales with the household size (arch 4.5, 5.3.5)."""

NEVER_ASKED_CATEGORIES: Final[frozenset[Category]] = frozenset({Category.HEALTH_PHARMACY})
"""Categories the agent never asks about (arch 4.5): health is private."""
