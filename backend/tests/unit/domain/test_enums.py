"""F2 step 1a: the fixed value lists (arch 4.4 / 4.5) and the shared category sets.

The expected values are parsed from the architecture doc itself, so the doc is the single source
of truth (work-breakdown 0.3 rule 7) and there is no second hand-typed copy that could carry the
same typo. The values are stored in the DB and sent in JSON: renaming, reordering or dropping one
must break loudly. If a doc edit changes the format a parser expects, the test fails and the parser
gets updated together with the doc.
"""

import inspect
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from collections.abc import Callable
from enum import StrEnum
from functools import cache
from pathlib import Path

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

BACKEND = Path(__file__).resolve().parents[3]
ARCH_DOC = BACKEND / "docs" / "savings-coach-backend-architecture.md"
SNAKE_CASE = re.compile(r"[a-z]+(_[a-z]+)*")


# ── parsers: pure functions of the doc text ─────────────────────────────────────────────────


@cache
def arch_doc() -> str:
    return ARCH_DOC.read_text(encoding="utf-8")


def section(text: str, heading: str) -> str:
    """The lines under the heading that starts with `heading`, up to the next ##/### heading."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(heading))
    rest = lines[start + 1 :]
    end = next((i for i, line in enumerate(rest) if line.startswith(("## ", "### "))), len(rest))
    return "\n".join(rest[:end])


def line_starting(text: str, prefix: str) -> str:
    return next(line for line in text.splitlines() if line.startswith(prefix))


def code_words(fragment: str) -> list[str]:
    """Every `snake_case` code span, in order (spans with spaces or symbols are skipped)."""
    return re.findall(r"`([a-z_]+)`", fragment)


def slash_list(row: str, column: str) -> list[str]:
    """`column` (`a / b / c`) or `column` values `a / b`, as in the arch 4.2 / 4.4 tables."""
    match = re.search(rf"`{re.escape(column)}`(?: values)? \(?`([^`]+)`", row)
    assert match, f"no `{column}` value list in: {row[:80]}…"
    return [value.strip() for value in match.group(1).split("/")]


def fixed_lists(text: str) -> str:
    return section(text, "### 4.5")


def categories(text: str) -> list[str]:
    return code_words(line_starting(fixed_lists(text), "**Categories:**"))


def purposes(text: str) -> list[str]:
    return re.findall(r"^\| `([a-z_]+)` \|", fixed_lists(text), flags=re.MULTILINE)


def household_scaled(text: str) -> list[str]:
    line = line_starting(fixed_lists(text), "**Household-scaled categories:**")
    return code_words(line.split("Not scaled")[0])


def not_household_scaled(text: str) -> list[str]:
    line = line_starting(fixed_lists(text), "**Household-scaled categories:**")
    return code_words(line.split("Not scaled")[1])


def never_asked(text: str) -> list[str]:
    return code_words(line_starting(fixed_lists(text), "**Never asked about:**"))


def column(table_row_prefix: str, name: str) -> Callable[[str], list[str]]:
    def parse(text: str) -> list[str]:
        return slash_list(line_starting(text, table_row_prefix), name)

    return parse


# (enum, parser of its list in the doc, where the doc lists it). Every 1a enum has a parseable list.
DOC_LISTS: list[tuple[type[StrEnum], Callable[[str], list[str]], str]] = [
    (Category, categories, "arch 4.5 Categories"),
    (Purpose, purposes, "arch 4.5 Purposes table"),
    (Beneficiary, column("| `transactions` |", "beneficiary"), "arch 4.4 transactions"),
    (Decision, column("| `transactions` |", "decision"), "arch 4.4 transactions"),
    (Direction, column("| `transactions` |", "direction"), "arch 4.4 transactions"),
    (
        AnnotationSource,
        column("| `transactions` |", "annotation_source"),
        "arch 4.4 transactions",
    ),
    (Language, column("| `users.language`", "users.language"), "arch 4.2 users.language"),
    (CoachStyle, column("| `users` |", "coach_style"), "arch 4.4 users"),
    (ProductKind, column("| `products` |", "kind"), "arch 4.4 products"),
    (Liquidity, column("| `products` |", "liquidity"), "arch 4.4 products"),
]

# (module constant name, parser of its list in the doc)
DOC_SETS: dict[str, Callable[[str], list[str]]] = {
    "HOUSEHOLD_SCALED_CATEGORIES": household_scaled,
    "NEVER_ASKED_CATEGORIES": never_asked,
}

# Values shared by two enums. Equal values are equal dict / set keys (StrEnum == str), so a map
# that mixes these enums must key by (type, member). A new overlap must be added here on purpose.
KNOWN_OVERLAPS: dict[str, set[str]] = {
    "auto": {"Decision", "AnnotationSource"},
}

ENUMS = [pytest.param(enum, id=enum.__name__) for enum, _, _ in DOC_LISTS]
FIXED_SETS = [pytest.param(getattr(enums, name), id=name) for name in DOC_SETS]


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


# ── the values ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("enum", "parse"),
    [
        pytest.param(enum, parse, id=f"{enum.__name__} ({source})")
        for enum, parse, source in DOC_LISTS
    ],
)
def test_enum_values_match_the_architecture_doc(
    enum: type[StrEnum], parse: Callable[[str], list[str]]
) -> None:
    assert [member.value for member in enum] == parse(arch_doc())


def test_every_enum_in_the_module_is_checked_against_the_doc() -> None:
    # A new enum without an entry in DOC_LISTS would escape the rename check above.
    assert module_enums() == {enum for enum, _, _ in DOC_LISTS}


def test_enum_lookup_by_value_returns_the_member() -> None:
    # B3 rebuilds enums from the strings stored in the DB.
    assert Category("groceries") is Category.GROCERIES
    assert Decision("ask_later") is Decision.ASK_LATER
    assert Beneficiary("self") is Beneficiary.SELF
    assert AnnotationSource("user_edit") is AnnotationSource.USER_EDIT


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


# ── the fixed sets ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("name", "parse"), list(DOC_SETS.items()), ids=list(DOC_SETS))
def test_fixed_set_lists_the_doc_values_in_the_doc_order(
    name: str, parse: Callable[[str], list[str]]
) -> None:
    assert [category.value for category in getattr(enums, name)] == parse(arch_doc())


def test_every_fixed_set_in_the_module_is_checked_against_the_doc() -> None:
    # A new module-level collection without an entry in DOC_SETS would escape the check above.
    assert module_fixed_sets() == set(DOC_SETS)


def test_household_scaled_categories_exclude_the_activity_driven_ones() -> None:
    # arch 4.5: electronics, subscriptions, sport, entertainment follow activity facts instead.
    not_scaled = not_household_scaled(arch_doc())

    assert not_scaled == ["electronics", "subscriptions", "sport", "entertainment"]
    assert not set(not_scaled) & set(HOUSEHOLD_SCALED_CATEGORIES)


@pytest.mark.parametrize("fixed_set", FIXED_SETS)
def test_fixed_sets_are_tuples_of_unique_category_members(fixed_set: tuple[Category, ...]) -> None:
    # A tuple iterates in its written order in every process (R1); a frozenset doesn't.
    assert isinstance(fixed_set, tuple)
    assert all(isinstance(category, Category) for category in fixed_set)
    assert len(set(fixed_set)) == len(fixed_set)


def test_fixed_sets_iterate_in_the_same_order_in_every_process() -> None:
    # str hashes are salted per process (PYTHONHASHSEED), so a frozenset's iteration order changes
    # between runs. Snapshots, prompt caching and generated lists need the same order every time.
    script = (
        "import json; from app.domain import enums; "
        f"print(json.dumps({{n: list(getattr(enums, n)) for n in {sorted(DOC_SETS)!r}}}))"
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

    in_process = json.dumps({name: list(getattr(enums, name)) for name in sorted(DOC_SETS)})
    assert outputs == {in_process + "\n"}


def test_fixed_sets_contain_the_plain_strings_read_from_the_db() -> None:
    # C6 / C7 check a category string straight from the DB: the privacy rule must hold for it.
    assert "health_pharmacy" in NEVER_ASKED_CATEGORIES
    assert "Health_Pharmacy" not in NEVER_ASKED_CATEGORIES
    assert "groceries" in HOUSEHOLD_SCALED_CATEGORIES
    assert "electronics" not in HOUSEHOLD_SCALED_CATEGORIES
