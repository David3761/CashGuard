"""The doc parsers behind test_enums.py fail loudly (review of F2.1b, R3 to R6, R8).

A parser that silently skipped a value it couldn't read (`p2p_transfers`), kept only a prefix of
it (`re-sent` → `re`) or stopped at a line break would let the enum and the doc drift apart while
the tests stay green. Every case here is a small synthetic doc fragment.
"""

import pytest

from tests.unit.domain.doc_lists import (
    DocParseError,
    agent_event_statuses,
    agent_event_types,
    code_list,
    household_roles,
    life_event_types,
    line_starting,
    message_roles,
    never_asked,
    pipe_list,
    priority_levels,
    purposes,
    section,
    slash_list,
    sql_column,
)

# ── code_list (R3) ───────────────────────────────────────────────────────────────────────────


def test_code_list_reads_a_comma_separated_list_of_code_values() -> None:
    assert code_list(" `groceries`, `food_delivery`.", "t") == ["groceries", "food_delivery"]


@pytest.mark.parametrize(
    "fragment",
    [
        pytest.param("`groceries`, `p2p_transfers`", id="digit"),
        pytest.param("`groceries`, `goal_80pct`", id="digits inside"),
        pytest.param("`groceries`, `Other`", id="uppercase"),
        pytest.param("`groceries`, `goal-80`", id="hyphen"),
        pytest.param("`groceries`, restaurants", id="value without backticks"),
        pytest.param("`groceries`, `restaurants` `fuel`", id="two spans in one item"),
        pytest.param("`groceries`,", id="dangling comma"),
    ],
)
def test_code_list_rejects_what_it_cannot_read(fragment: str) -> None:
    with pytest.raises(DocParseError, match="t:"):
        code_list(fragment, "t")


# ── pipe_list (R4) ───────────────────────────────────────────────────────────────────────────


def test_pipe_list_reads_values_and_drops_only_a_trailing_note() -> None:
    comment = ' classify | suppress   (suppress = "nu mai întreba de asta")'

    assert pipe_list(comment, "t") == ["classify", "suppress"]


@pytest.mark.parametrize(
    "comment",
    [
        pytest.param(" pending | re-sent", id="hyphen (was kept as 're')"),
        pytest.param(" pending | 2nd_try", id="leading digit (was dropped)"),
        pytest.param(" pending || sent", id="empty part"),
        pytest.param(" pending | Sent", id="uppercase"),
        pytest.param(" pending sent | paid", id="two words in one part"),
        pytest.param("", id="no values at all"),
    ],
)
def test_pipe_list_rejects_what_it_cannot_read(comment: str) -> None:
    with pytest.raises(DocParseError, match="t:"):
        pipe_list(comment, "t")


# ── sql_column (R5) ──────────────────────────────────────────────────────────────────────────


def sql_doc(body: str) -> str:
    return f"### 4.4 Tables\n```sql\n{body}\n```\n### 4.5 Next\n"


def test_sql_column_joins_any_comment_continuation() -> None:
    # The arch doc starts its continuation lines with `-- |`; a trailing `|` wraps just as well.
    doc = sql_doc("things (\n  id,\n  kind,   -- a | b |\n           -- c | d\n  note TEXT)")

    assert sql_column("### 4.4", "things", "kind")(doc) == ["a", "b", "c", "d"]


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            "things (\n  kind,   -- a | b\n           -- c | d\n  note)", id="rewrap without a pipe"
        ),
        pytest.param("things (\n  kind,   -- a | b\n  -- see 5.3.7\n  note)", id="a prose note"),
        pytest.param("things (\n  kind,\n  note)", id="no value comment"),
        pytest.param("things (\n  kind,   -- a | b\n  note,", id="the table never closes"),
        pytest.param("stuff (\n  kind,   -- a | b\n  note)", id="no such table"),
        pytest.param("things (\n  id,\n  note)", id="no such column"),
        pytest.param("things (\n  kind, -- a\n  kind, -- b\n  x)", id="the column twice"),
    ],
)
def test_sql_column_errors_instead_of_truncating(body: str) -> None:
    with pytest.raises(DocParseError):
        sql_column("### 4.4", "things", "kind")(sql_doc(body))


# ── agent_events (R6) ───────────────────────────────────────────────────────────────────────


def agent_events_doc(row_cell: str, types: str = "overspend, warning,\n  --  category_cap") -> str:
    return (
        "### 4.1 Tables\n```sql\nagent_events (id,\n  status,  -- pending | expired\n  x)\n"
        f"  -- types: {types}\n```\n### 4.4 More\n| `agent_events` | {row_cell} |\n"
    )


GOOD_CELL = "`ref_transaction_id NULL`; status `pending → asked / expired`; new types `a`, `b`; x y"


def test_agent_event_parsers_read_both_lists_of_a_well_formed_doc() -> None:
    doc = agent_events_doc(GOOD_CELL.replace("x y", "uniqueness by date"))

    assert agent_event_types(doc) == ["overspend", "warning", "category_cap", "a", "b"]
    assert agent_event_statuses(doc) == ["pending", "asked", "expired"]


NO_NEW_TYPES_CELL = "`ref_transaction_id NULL`; status `pending`; uniqueness z"
BAD_VALUE_CELL = GOOD_CELL.replace("`a`, `b`", "`a`, `b-c`").replace("x y", "uniqueness z")


@pytest.mark.parametrize(
    "cell",
    [
        pytest.param(GOOD_CELL.replace("x y", "also `c`; uniqueness z"), id="a clause after"),
        pytest.param(GOOD_CELL.replace("x y", "new types `c`; uniqueness z"), id="new types twice"),
        pytest.param(BAD_VALUE_CELL, id="bad value"),
        pytest.param(NO_NEW_TYPES_CELL, id="no new types"),
    ],
)
def test_agent_event_types_errors_on_a_row_it_does_not_fully_understand(cell: str) -> None:
    with pytest.raises(DocParseError):
        agent_event_types(agent_events_doc(cell))


def test_agent_event_types_errors_on_a_bad_4_1_type() -> None:
    doc = agent_events_doc(GOOD_CELL.replace("x y", "uniqueness z"), types="over-spend, warning")

    with pytest.raises(DocParseError):
        agent_event_types(doc)


# ── the other parsers ────────────────────────────────────────────────────────────────────────


def life_facts_doc(value_comment: str) -> str:
    return sql_doc(f"life_facts (\n  id,\n  value JSONB,  -- {value_comment}\n  x)")


def test_priority_levels_tolerate_json_spacing() -> None:
    doc = life_facts_doc(
        '{"category": "concerts", "priority": "protected"} / {"priority":"reduce"}'
    )

    assert priority_levels(doc) == ["protected", "reduce"]


@pytest.mark.parametrize(
    "comment",
    [
        pytest.param('{"category":"concerts","priority":"Protected"}', id="uppercase"),
        pytest.param('{"category":"concerts"}', id="no priority at all"),
    ],
)
def test_priority_levels_reject_what_they_cannot_read(comment: str) -> None:
    with pytest.raises(DocParseError):
        priority_levels(life_facts_doc(comment))


@pytest.mark.parametrize(
    "sentence",
    [
        pytest.param("Only `user`, `assistant` and `tool` messages are returned.", id="3 roles"),
        pytest.param("Only `user` and `Assistant` messages are returned.", id="uppercase"),
        pytest.param("We return `user` and `assistant` messages.", id="reworded"),
    ],
)
def test_message_roles_error_when_the_sentence_changes(sentence: str) -> None:
    with pytest.raises(DocParseError):
        message_roles(f"### 9.3 Shapes\n{sentence}\n### 9.4 Next\n")


def test_household_roles_reject_an_unreadable_role() -> None:
    with pytest.raises(DocParseError):
        household_roles("`household_member` needs `role ∈ {adult, child, pet-owner}`")


def test_life_event_types_reject_an_unreadable_type() -> None:
    doc = '### 6.2 Tool\n"type":     {"type": "string", "enum": ["trip", "Gift"]}\n### 6.3 Next\n'

    with pytest.raises(DocParseError):
        life_event_types(doc)


def test_slash_list_rejects_an_unreadable_value_and_a_repeated_column() -> None:
    with pytest.raises(DocParseError):
        slash_list("| `transfers` | `kind` (`manual / auto-save`) |", "kind", "t")
    with pytest.raises(DocParseError):
        slash_list("| x | `kind` (`a / b`), `kind` (`c / d`) |", "kind", "t")


def test_purposes_reject_a_row_without_a_code_value() -> None:
    doc = (
        "### 4.5 Fixed lists\n**Purposes**:\n\n| Purpose | Meaning |\n|---|---|\n"
        "| `essential_living` | food |\n| household care | kids |\n\nMore text.\n"
    )

    with pytest.raises(DocParseError):
        purposes(doc)


def test_never_asked_errors_when_the_sentence_changes() -> None:
    doc = "### 4.5 Fixed lists\n**Never asked about:** `health_pharmacy`, sensitive facts.\n"

    with pytest.raises(DocParseError):
        never_asked(doc)


def test_section_and_line_lookups_require_exactly_one_match() -> None:
    with pytest.raises(DocParseError):
        section("### 4.1 A\nx\n### 4.1 B\ny\n", "### 4.1")
    with pytest.raises(DocParseError):
        section("### 4.2 A\nx\n", "### 4.1")
    with pytest.raises(DocParseError):
        line_starting("| `users` | a\n| `users` | b\n", "| `users` |")
