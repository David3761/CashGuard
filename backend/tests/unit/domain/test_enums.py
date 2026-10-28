"""F2 step 1: every fixed value list (arch 4.1 / 4.2 / 4.4 / 4.5) and the shared sets.

The expected values are parsed from the docs themselves (the strict parsers in doc_lists.py), so
the doc is the single source of truth (work-breakdown 0.3 rule 7) and there is no second
hand-typed copy that could carry the same typo. Every enum has a parseable list. The one
hand-typed list is QUESTION_EVENT_TYPES, because D25 names its sources in prose. The values are
stored in the DB and sent in JSON: renaming, reordering or dropping one must break loudly. If a
doc edit changes the format a parser expects, the parser raises DocParseError and is updated
together with the doc.
"""

import inspect
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from enum import StrEnum
from pathlib import Path

import pytest

from app.domain import enums
from app.domain.enums import (
    HOUSEHOLD_SCALED_CATEGORIES,
    NEVER_ASKED_CATEGORIES,
    QUESTION_EVENT_TYPES,
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
from tests.unit.domain.doc_lists import (
    ARCH_DOC,
    BACKEND,
    WORK_BREAKDOWN,
    Parser,
    agent_event_statuses,
    agent_event_types,
    categories,
    column,
    household_roles,
    household_scaled,
    ledger_statuses,
    life_event_types,
    message_roles,
    never_asked,
    not_household_scaled,
    priority_levels,
    purposes,
    read,
    section,
    sql_block,
    sql_column,
)

SNAKE_CASE = re.compile(r"[a-z]+(_[a-z]+)*")


# (enum, parser, which doc, where the doc lists it). Every enum has a parseable list.
DOC_LISTS: list[tuple[type[StrEnum], Parser, Path, str]] = [
    (Category, categories, ARCH_DOC, "arch 4.5 Categories"),
    (Purpose, purposes, ARCH_DOC, "arch 4.5 Purposes table"),
    (
        Beneficiary,
        column("| `transactions` |", "beneficiary"),
        ARCH_DOC,
        "arch 4.4 transactions",
    ),
    (Decision, column("| `transactions` |", "decision"), ARCH_DOC, "arch 4.4 transactions"),
    (Direction, column("| `transactions` |", "direction"), ARCH_DOC, "arch 4.4 transactions"),
    (
        AnnotationSource,
        column("| `transactions` |", "annotation_source"),
        ARCH_DOC,
        "arch 4.4 transactions",
    ),
    (
        Language,
        column("| `users.language`", "users.language"),
        ARCH_DOC,
        "arch 4.2 users.language",
    ),
    (CoachStyle, column("| `users` |", "coach_style"), ARCH_DOC, "arch 4.4 users"),
    (ProductKind, column("| `products` |", "kind"), ARCH_DOC, "arch 4.4 products"),
    (Liquidity, column("| `products` |", "liquidity"), ARCH_DOC, "arch 4.4 products"),
    (FactType, sql_column("### 4.4", "life_facts", "type"), ARCH_DOC, "arch 4.4 life_facts"),
    (FactSource, sql_column("### 4.4", "life_facts", "source"), ARCH_DOC, "arch 4.4 life_facts"),
    (FactStatus, sql_column("### 4.4", "life_facts", "status"), ARCH_DOC, "arch 4.4 life_facts"),
    (
        Persistence,
        sql_column("### 4.4", "life_facts", "persistence"),
        ARCH_DOC,
        "arch 4.4 life_facts",
    ),
    (
        SignatureEffect,
        sql_column("### 4.4", "spending_signatures", "effect"),
        ARCH_DOC,
        "arch 4.4 spending_signatures",
    ),
    (
        SignatureOrigin,
        sql_column("### 4.4", "spending_signatures", "origin"),
        ARCH_DOC,
        "arch 4.4 spending_signatures",
    ),
    (RuleKind, sql_column("### 4.4", "pattern_rules", "kind"), ARCH_DOC, "arch 4.4 pattern_rules"),
    (
        RuleSource,
        sql_column("### 4.4", "pattern_rules", "source"),
        ARCH_DOC,
        "arch 4.4 pattern_rules",
    ),
    (
        ReceivableStatus,
        sql_column("### 4.4", "receivables", "status"),
        ARCH_DOC,
        "arch 4.4 receivables",
    ),
    (PotKind, sql_column("### 4.4", "pots", "kind"), ARCH_DOC, "arch 4.4 pots"),
    (PotStatus, sql_column("### 4.4", "pots", "status"), ARCH_DOC, "arch 4.4 pots"),
    (InputMode, column("| `messages` |", "input_mode"), ARCH_DOC, "arch 4.4 messages"),
    (AgentEventType, agent_event_types, ARCH_DOC, "arch 4.1 agent_events + 4.4 new types"),
    (AgentEventStatus, agent_event_statuses, ARCH_DOC, "arch 4.4 agent_events"),
    (
        TransferKind,
        column("| **New:** `transfers", "kind"),
        ARCH_DOC,
        "arch 4.2 transfers.kind",
    ),
    (
        TxStatus,
        sql_column("### 4.1", "transactions", "status"),
        ARCH_DOC,
        "arch 4.1 transactions",
    ),
    (
        TxSource,
        column("| `transactions.source`", "transactions.source"),
        ARCH_DOC,
        "arch 4.2 transactions.source",
    ),
    (GoalStatus, column("| `goals.status`", "goals.status"), ARCH_DOC, "arch 4.2 goals.status"),
    (
        LifeEventStatus,
        column("| `life_events.status`", "life_events.status"),
        ARCH_DOC,
        "arch 4.2 life_events.status",
    ),
    (LifeEventType, life_event_types, ARCH_DOC, "arch 6.2 add_life_event schema"),
    (LedgerStatus, ledger_statuses, ARCH_DOC, "arch 4.1 day_ledger"),
    (MessageRole, message_roles, ARCH_DOC, "arch 9.3 Message"),
    (HouseholdRole, household_roles, WORK_BREAKDOWN, "work-breakdown F2 validation rules"),
    (PriorityLevel, priority_levels, ARCH_DOC, "arch 4.4 life_facts.value examples"),
]

# (member enum, the doc's list: a parser of the arch doc, or a hand list when there is none, source)
FIXED_SETS: dict[str, tuple[type[StrEnum], Parser | list[str], str]] = {
    "HOUSEHOLD_SCALED_CATEGORIES": (Category, household_scaled, "arch 4.5"),
    "NEVER_ASKED_CATEGORIES": (Category, never_asked, "arch 4.5"),
    "QUESTION_EVENT_TYPES": (
        AgentEventType,
        # Hand list: D25 names the sources in prose ("transaction questions, overspend 'what
        # happened?', weekly reflection, preemptive check-ins"). David G. (2026-10-29) added
        # underspend_week: it replaces that Sunday's weekly reflection and asks, so it counts.
        [
            "transaction_question",
            "overspend",
            "weekly_reflection",
            "underspend_week",
            "preemptive_checkin",
        ],
        "arch D25 + David G. 2026-10-29 (hand list: prose, no value list)",
    ),
}

# 4.1 columns with no value list in the doc, each left without an enum on purpose (review R10).
# The test below fails if the doc ever gives one of them a list, so the decision gets revisited.
LEFT_OUT_COLUMNS: dict[tuple[str, str], str] = {
    ("life_events", "source"): "reuses the FactSource values (onboarding … seed)",
    ("slips", "reason"): "free text: the user's own words",
    ("notifications", "type"): "B13's notification templates define it",
}

# Values shared by two enums. Equal values are equal dict / set keys (StrEnum == str), so a map
# that mixes these enums must key by (type, member). A new overlap must be added here on purpose.
# All of these live in different columns, so none of them is a problem today.
KNOWN_OVERLAPS: dict[str, set[str]] = {
    "auto": {"Decision", "AnnotationSource"},
    "answer": {"AnnotationSource", "RuleSource"},
    "user_edit": {"AnnotationSource", "FactSource"},
    "custom": {"FactType", "PotKind"},
    "emergency": {"Purpose", "PotKind"},
    "expired": {"FactStatus", "AgentEventStatus"},
    "active": {"PotStatus", "GoalStatus"},
    "completed": {"PotStatus", "GoalStatus"},
    "cancelled": {"ReceivableStatus", "LifeEventStatus"},
    "voice": {"FactSource", "InputMode"},
    "warning": {"AgentEventType", "LedgerStatus"},
    "other": {"Category", "LifeEventType"},
    "education": {"Category", "LifeEventType"},
    "seed": {"FactSource", "TxSource"},
}

# Belt and braces behind the FactType allow-list: stems of the special categories (arch 4.5 + the
# GDPR art. 9 list). A fact type containing any of them must never exist.
SENSITIVE_STEMS = (
    "health", "medic", "diagnos", "disab", "illness", "disease", "therap", "mental", "pregnan",
    "religio", "faith", "belief", "church", "ethnic", "racial", "race", "sexual", "orientation",
    "gender", "politic", "union", "genetic", "biometric", "criminal",
)  # fmt: skip


def is_sensitive(word: str) -> bool:
    return any(stem in word for stem in SENSITIVE_STEMS)


ENUMS = [pytest.param(enum, id=enum.__name__) for enum, _, _, _ in DOC_LISTS]
SETS = [pytest.param(name, id=name) for name in FIXED_SETS]


def module_enums() -> set[type[StrEnum]]:
    return {
        obj
        for _, obj in inspect.getmembers(enums, inspect.isclass)
        if issubclass(obj, StrEnum) and obj is not StrEnum and obj.__module__ == enums.__name__
    }


def module_fixed_sets() -> set[str]:
    return {
        name
        for name, value in vars(enums).items()
        if not name.startswith("_") and isinstance(value, tuple | frozenset | set | list)
    }


def doc_list(name: str) -> list[str]:
    _, listed, _ = FIXED_SETS[name]
    return listed if isinstance(listed, list) else listed(read(ARCH_DOC))


# ── the values ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("enum", "parse", "doc"),
    [
        pytest.param(enum, parse, doc, id=f"{enum.__name__} ({source})")
        for enum, parse, doc, source in DOC_LISTS
    ],
)
def test_enum_values_match_the_docs(enum: type[StrEnum], parse: Parser, doc: Path) -> None:
    assert [member.value for member in enum] == parse(read(doc))


def test_every_enum_in_the_module_is_checked_against_the_docs() -> None:
    # A new enum without an entry in DOC_LISTS would escape the rename check above.
    assert module_enums() == {enum for enum, _, _, _ in DOC_LISTS}


def test_agent_event_statuses_include_the_original_4_1_ones() -> None:
    # 4.1 listed pending | handled | expired; 4.4 extends that lifecycle (the list parsed above).
    original = sql_column("### 4.1", "agent_events", "status")(read(ARCH_DOC))

    assert original == ["pending", "handled", "expired"]
    assert set(original) <= {status.value for status in AgentEventStatus}


def test_enum_lookup_by_value_returns_the_member() -> None:
    # B3 rebuilds enums from the strings stored in the DB.
    assert Category("groceries") is Category.GROCERIES
    assert Decision("ask_later") is Decision.ASK_LATER
    assert Beneficiary("self") is Beneficiary.SELF
    assert AnnotationSource("user_edit") is AnnotationSource.USER_EDIT
    assert AgentEventType("transaction_question") is AgentEventType.TRANSACTION_QUESTION
    assert TransferKind("auto_save") is TransferKind.AUTO_SAVE


@pytest.mark.parametrize("enum", ENUMS)
def test_enum_values_are_snake_case_and_member_names_match(enum: type[StrEnum]) -> None:
    # __members__ includes aliases. An alias always has a name other than value.upper(), so this
    # also catches a duplicate value that @unique would otherwise have to stop.
    for name, member in enum.__members__.items():
        assert SNAKE_CASE.fullmatch(member.value), member.value
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
        (FactType, "health"),
        (AgentEventStatus, "done"),
        (InputMode, "speech"),
        (HouseholdRole, "parent"),
    ],
)
def test_enum_rejects_unknown_or_miscased_values(enum: type[StrEnum], value: str) -> None:
    # Case-sensitive on purpose: PATCH /me with language "fr" must be a 422 (B6a), and C4 drops
    # Claude's signatures with an invalid purpose such as "good_purchase".
    with pytest.raises(ValueError, match="is not a valid"):
        enum(value)


@pytest.mark.parametrize("enum", ENUMS)
def test_enum_members_are_str_enums_that_format_and_serialise_as_their_value(
    enum: type[StrEnum],
) -> None:
    # A `(str, Enum)` would print "Category.GROCERIES" in f-strings, logs and SQL.
    assert issubclass(enum, StrEnum)
    for member in enum:
        assert f"{member}" == str(member) == member.value
        assert json.dumps(member) == f'"{member.value}"'


def test_cross_enum_value_overlaps_are_the_known_ones() -> None:
    owners: defaultdict[str, set[str]] = defaultdict(set)
    for enum in module_enums():
        for member in enum:
            owners[member.value].add(enum.__name__)

    assert {value: names for value, names in owners.items() if len(names) > 1} == KNOWN_OVERLAPS


def test_fact_types_are_exactly_the_documented_allow_list() -> None:
    # arch 4.5: sensitive facts (health, religion, ethnicity, sexual orientation, politics) are
    # never stored or inferred. The allow-list is the arch 4.4 type list: nothing else may exist.
    allowed = sql_column("### 4.4", "life_facts", "type")(read(ARCH_DOC))

    sensitive = [fact_type.value for fact_type in FactType if is_sensitive(fact_type.value)]

    assert {fact_type.value for fact_type in FactType} == set(allowed)
    assert not sensitive, f"sensitive fact types: {sensitive}"


@pytest.mark.parametrize(
    "word",
    [
        "health", "diagnosis", "disability", "medication", "mental_health", "chronic_illness",
        "pregnancy", "religion", "faith", "ethnicity", "race", "sexual_orientation",
        "gender_identity", "political_party", "trade_union", "genetic_test", "biometric_id",
        "criminal_record",
    ],
)  # fmt: skip
def test_the_sensitive_blocklist_catches_the_special_categories(word: str) -> None:
    assert is_sensitive(word)


@pytest.mark.parametrize(
    ("table", "column"),
    [pytest.param(table, column, id=f"{table}.{column}") for table, column in LEFT_OUT_COLUMNS],
)
def test_left_out_columns_still_have_no_value_list_in_the_doc(table: str, column: str) -> None:
    (line,) = sql_block(section(read(ARCH_DOC), "### 4.1"), table, f"4.1 {table}")
    code, _, comment = line.partition("--")

    assert re.search(rf"\b{column}\b", code), f"{table}.{column} isn't in the 4.1 listing"
    assert not comment, f"4.1 now lists values for {table}.{column}: revisit LEFT_OUT_COLUMNS"


# ── the fixed sets ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", SETS)
def test_fixed_set_lists_the_doc_values_in_the_doc_order(name: str) -> None:
    assert [member.value for member in getattr(enums, name)] == doc_list(name)


def test_every_fixed_set_in_the_module_is_checked_against_the_docs() -> None:
    # A new module-level collection without an entry in FIXED_SETS would escape the check above.
    assert module_fixed_sets() == set(FIXED_SETS)


@pytest.mark.parametrize("name", SETS)
def test_fixed_sets_are_tuples_of_unique_members_of_one_enum(name: str) -> None:
    # A tuple iterates in its written order in every process (R1); a frozenset doesn't.
    member_enum, _, _ = FIXED_SETS[name]
    fixed_set = getattr(enums, name)

    assert isinstance(fixed_set, tuple)
    assert all(type(member) is member_enum for member in fixed_set)
    assert len(set(fixed_set)) == len(fixed_set)


def test_household_scaled_categories_exclude_the_activity_driven_ones() -> None:
    # arch 4.5: electronics, subscriptions, sport, entertainment follow activity facts instead.
    not_scaled = not_household_scaled(read(ARCH_DOC))

    assert not_scaled == ["electronics", "subscriptions", "sport", "entertainment"]
    assert not set(not_scaled) & set(HOUSEHOLD_SCALED_CATEGORIES)


def test_question_event_types_leave_out_what_never_uses_the_daily_question() -> None:
    # 5.3.6 / 5.3.8: hypotheses never use the daily question; WB A7: goal_completed doesn't.
    # David G. (2026-10-29): a receivable reminder is a statement + a tap card and never asks.
    assert AgentEventType.HYPOTHESIS_CHECK not in QUESTION_EVENT_TYPES
    assert AgentEventType.GOAL_COMPLETED not in QUESTION_EVENT_TYPES
    assert AgentEventType.RECEIVABLE_REMINDER not in QUESTION_EVENT_TYPES


def test_fixed_sets_iterate_in_the_same_order_in_every_process() -> None:
    # str hashes are salted per process (PYTHONHASHSEED), so a frozenset's iteration order changes
    # between runs. Snapshots, prompt caching and generated lists need the same order every time.
    names = sorted(FIXED_SETS)
    script = (
        "import json; from app.domain import enums; "
        f"print(json.dumps({{n: list(getattr(enums, n)) for n in {names!r}}}))"
    )
    outputs = set()
    for seed in ("1", "2", "3"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(BACKEND)}
        result = subprocess.run(  # noqa: S603 (fixed argv: this interpreter + a literal script)
            [sys.executable, "-c", script],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        outputs.add(result.stdout)

    in_process = json.dumps({name: list(getattr(enums, name)) for name in names})
    assert outputs == {in_process + "\n"}


def test_fixed_sets_contain_the_plain_strings_read_from_the_db() -> None:
    # C6 / C7 / B3 check a string straight from the DB: the rules must hold for it.
    assert "health_pharmacy" in NEVER_ASKED_CATEGORIES
    assert "Health_Pharmacy" not in NEVER_ASKED_CATEGORIES
    assert "groceries" in HOUSEHOLD_SCALED_CATEGORIES
    assert "electronics" not in HOUSEHOLD_SCALED_CATEGORIES
    assert "transaction_question" in QUESTION_EVENT_TYPES
    assert "underspend_week" in QUESTION_EVENT_TYPES
    assert "hypothesis_check" not in QUESTION_EVENT_TYPES
    assert "receivable_reminder" not in QUESTION_EVENT_TYPES
