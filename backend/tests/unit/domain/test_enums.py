"""F2 step 1a: the fixed value lists (arch 4.4 / 4.5) and the shared category sets.

The expected lists below are copied from the architecture doc. The values are stored in the DB and
sent in JSON, so renaming, reordering or dropping one must break loudly (work-breakdown 0.3 rule 7).
"""

import inspect
import json
import re
from enum import StrEnum

import pytest

from app.domain import enums
from app.domain.enums import (
    HOUSEHOLD_SCALED_CATEGORIES,
    NEVER_ASKED_CATEGORIES,
    AnnotationSource,
    Beneficiary,
    Category,
    CoachStyle,
    Decision,
    Direction,
    Language,
    Liquidity,
    ProductKind,
    Purpose,
)

# (enum, values in the doc's order, where the doc lists them)
GOLDEN: list[tuple[type[StrEnum], list[str], str]] = [
    (
        Category,
        [
            "groceries",
            "restaurants",
            "food_delivery",
            "transport",
            "fuel",
            "electronics",
            "clothing",
            "sport",
            "health_pharmacy",
            "kids",
            "education",
            "books",
            "entertainment",
            "subscriptions",
            "travel",
            "housing_rent",
            "utilities",
            "telecom",
            "gifts",
            "pets",
            "household_goods",
            "personal_care",
            "transfers",
            "income",
            "savings",
            "other",
        ],
        "arch 4.5 Categories",
    ),
    (
        Purpose,
        [
            "essential_living",
            "household_care",
            "work_tool",
            "self_investment",
            "identity_joy",
            "social_connection",
            "planned_event",
            "on_behalf_of_others",
            "unplanned_discretionary",
            "emergency",
            "unknown",
        ],
        "arch 4.5 Purposes",
    ),
    (
        Beneficiary,
        ["self", "household", "shared", "others", "employer"],
        "arch 4.4 transactions.beneficiary",
    ),
    (
        Decision,
        ["ignore", "auto", "inform", "ask", "ask_later"],
        "arch 4.4 transactions.decision",
    ),
    (Direction, ["debit", "credit"], "arch 4.4 transactions.direction"),
    (
        AnnotationSource,
        ["auto", "rule", "fact", "pot", "answer", "user_edit", "default"],
        "arch 4.4 transactions.annotation_source",
    ),
    (Language, ["ro", "en"], "arch 4.2 users.language"),
    (CoachStyle, ["warm", "direct"], "arch 4.4 users.coach_style"),
    (
        ProductKind,
        ["flexible_pot", "savings_account", "term_deposit"],
        "arch 4.4 products.kind",
    ),
    (Liquidity, ["instant", "notice", "locked"], "arch 4.4 products.liquidity"),
]

ENUMS = [pytest.param(enum, id=enum.__name__) for enum, _, _ in GOLDEN]
SNAKE_CASE_ASCII = re.compile(r"[a-z][a-z0-9_]*")


@pytest.mark.parametrize(
    ("enum", "expected"),
    [
        pytest.param(enum, values, id=f"{enum.__name__} ({source})")
        for enum, values, source in GOLDEN
    ],
)
def test_enum_values_match_the_architecture_doc(enum: type[StrEnum], expected: list[str]) -> None:
    assert [member.value for member in enum] == expected


def test_every_enum_in_the_module_has_a_golden_list() -> None:
    # A new enum without a golden list here would escape the rename check above.
    defined = {
        obj
        for _, obj in inspect.getmembers(enums, inspect.isclass)
        if issubclass(obj, StrEnum) and obj is not StrEnum and obj.__module__ == enums.__name__
    }

    assert defined == {enum for enum, _, _ in GOLDEN}


def test_enum_lookup_by_value_returns_the_member() -> None:
    # B3 rebuilds enums from the strings stored in the DB.
    assert Category("groceries") is Category.GROCERIES
    assert Decision("ask_later") is Decision.ASK_LATER
    assert Beneficiary("self") is Beneficiary.SELF
    assert AnnotationSource("user_edit") is AnnotationSource.USER_EDIT


@pytest.mark.parametrize("enum", ENUMS)
def test_enum_values_are_snake_case_ascii_and_member_names_match(enum: type[StrEnum]) -> None:
    # __members__ includes aliases, so an alias with another name is caught here too.
    for name, member in enum.__members__.items():
        assert SNAKE_CASE_ASCII.fullmatch(member.value), member.value
        assert name == member.value.upper()


@pytest.mark.parametrize(
    ("enum", "value"),
    [
        (Category, "Groceries"),
        (Category, "food"),
        (Category, "health pharmacy"),
        (Language, "fr"),
        (Language, "RO"),
        (Purpose, "good_purchase"),
        (Decision, "ASK"),
        (Beneficiary, ""),
    ],
)
def test_enum_rejects_unknown_or_miscased_values(enum: type[StrEnum], value: str) -> None:
    # Case-sensitive on purpose: PATCH /me with language "fr" must be a 422 (B6a), and C4 drops
    # Claude's signatures with an invalid purpose such as "good_purchase".
    with pytest.raises(ValueError, match="is not a valid"):
        enum(value)


@pytest.mark.parametrize("enum", ENUMS)
def test_enum_is_a_str_enum_without_aliases(enum: type[StrEnum]) -> None:
    # A duplicate value silently becomes an alias, and list(enum) then hides it.
    assert issubclass(enum, StrEnum)
    assert len(enum.__members__) == len(list(enum))


@pytest.mark.parametrize("enum", ENUMS)
def test_enum_members_format_and_serialise_as_their_value(enum: type[StrEnum]) -> None:
    # A `(str, Enum)` would print "Category.GROCERIES" in f-strings, logs and SQL.
    for member in enum:
        assert f"{member}" == str(member) == member.value
        assert json.dumps(member) == f'"{member.value}"'


def test_household_scaled_categories_match_the_doc() -> None:
    # arch 4.5: these scale with the household; the activity-driven ones don't.
    assert set(HOUSEHOLD_SCALED_CATEGORIES) == {
        Category.GROCERIES,
        Category.HOUSEHOLD_GOODS,
        Category.HEALTH_PHARMACY,
        Category.UTILITIES,
        Category.KIDS,
        Category.CLOTHING,
        Category.PERSONAL_CARE,
    }
    not_scaled = {
        Category.ELECTRONICS,
        Category.SUBSCRIPTIONS,
        Category.SPORT,
        Category.ENTERTAINMENT,
    }
    assert not_scaled.isdisjoint(HOUSEHOLD_SCALED_CATEGORIES)


def test_never_asked_categories_is_only_health_pharmacy() -> None:
    # arch 4.5: health spending is never asked about (privacy, never judgmental).
    assert set(NEVER_ASKED_CATEGORIES) == {Category.HEALTH_PHARMACY}


@pytest.mark.parametrize(
    "fixed_set",
    [
        pytest.param(HOUSEHOLD_SCALED_CATEGORIES, id="HOUSEHOLD_SCALED_CATEGORIES"),
        pytest.param(NEVER_ASKED_CATEGORIES, id="NEVER_ASKED_CATEGORIES"),
    ],
)
def test_fixed_sets_are_frozen_sets_of_category_members(fixed_set: frozenset[Category]) -> None:
    assert isinstance(fixed_set, frozenset)
    assert all(isinstance(category, Category) for category in fixed_set)
