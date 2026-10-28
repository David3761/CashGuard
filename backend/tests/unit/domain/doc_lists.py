"""Parsers for the value lists in the docs (test support for test_enums.py).

Every parser is a pure function of the doc text and **fails loudly**. If the text isn't in the
shape it expects, or a listed value isn't a snake_case word, it raises DocParseError instead of
skipping the value, keeping only a prefix of it or stopping at a line break (review of F2.1b,
R3 to R6). Then the parser is updated together with the doc edit.
"""

import json
import re
from collections.abc import Callable
from functools import cache
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
ARCH_DOC = BACKEND / "docs" / "savings-coach-backend-architecture.md"
WORK_BREAKDOWN = BACKEND / "docs" / "work-breakdown.md"
VALUE = re.compile(r"[a-z]+(?:_[a-z]+)*")
AGENT_EVENTS_CLAUSES = ("`ref_transaction_id NULL`", "status ", "new types ", "uniqueness ")

Parser = Callable[[str], list[str]]


class DocParseError(ValueError):
    """The doc text isn't in the shape a parser expects: fix the parser together with the doc."""


@cache
def read(doc: Path) -> str:
    return doc.read_text(encoding="utf-8")


# ── building blocks ──────────────────────────────────────────────────────────────────────────


def value(token: str, where: str) -> str:
    token = token.strip()
    if not VALUE.fullmatch(token):
        raise DocParseError(f"{where}: {token!r} is not a snake_case value")
    return token


def split_once(text: str, separator: str, where: str) -> tuple[str, str]:
    if text.count(separator) != 1:
        raise DocParseError(f"{where}: expected {separator!r} exactly once")
    head, tail = text.split(separator)
    return head, tail


def section(text: str, heading: str) -> str:
    """The lines under the one heading that starts with `heading`, up to the next ##/###."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(heading)]
    if len(starts) != 1:
        raise DocParseError(f"heading {heading!r}: found {len(starts)}, expected 1")
    rest = lines[starts[0] + 1 :]
    end = next((i for i, line in enumerate(rest) if line.startswith(("## ", "### "))), len(rest))
    return "\n".join(rest[:end])


def line_starting(text: str, prefix: str) -> str:
    lines = [line for line in text.splitlines() if line.startswith(prefix)]
    if len(lines) != 1:
        raise DocParseError(f"line {prefix!r}: found {len(lines)}, expected 1")
    return lines[0]


def code_list(fragment: str, where: str) -> list[str]:
    """`a`, `b`, `c` (an optional final "."): every item must be exactly one `code` value."""
    values = []
    for item in fragment.strip().removesuffix(".").split(","):
        match = re.fullmatch(r"\s*`([^`]*)`\s*", item)
        if not match:
            raise DocParseError(f"{where}: {item.strip()!r} is not a single `code` value")
        values.append(value(match.group(1), where))
    return values


def pipe_list(comment: str, where: str) -> list[str]:
    """`a | b | c` with an optional trailing `(note)`: every part must be one value."""
    body = re.sub(r"\s*\([^()]*\)\s*$", "", comment.strip())
    return [value(part, where) for part in body.split("|")]


def slash_list(row: str, column: str, where: str) -> list[str]:
    """`column` (`a / b / c`) or `column` values `a / b`, as in the arch 4.2 / 4.4 tables."""
    found = re.findall(rf"`{re.escape(column)}`(?: values)? \(?`([^`]+)`", row)
    if len(found) != 1:
        raise DocParseError(f"{where}: {len(found)} value lists for `{column}`, expected 1")
    return [value(part, where) for part in found[0].split("/")]


def sql_block(text: str, table: str, where: str) -> list[str]:
    """The lines of `table (…)` in an SQL listing, from its header to the line that closes it."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if re.match(rf"{table}\s*\(", line)]
    if len(starts) != 1:
        raise DocParseError(f"{where}: found `{table} (` {len(starts)} times, expected 1")
    for end in range(starts[0], len(lines)):
        if lines[end].split("--")[0].rstrip().endswith(")"):
            return lines[starts[0] : end + 1]
    raise DocParseError(f"{where}: `{table} (` never closes")


def sql_column(heading: str, table: str, column: str) -> Parser:
    """`column, -- a | b` plus every pure `-- …` line right after it, joined, all values."""

    def parse(text: str) -> list[str]:
        where = f"{heading} {table}.{column}"
        block = sql_block(section(text, heading), table, where)
        hits = [i for i, line in enumerate(block) if re.match(rf"\s*{column},", line)]
        if len(hits) != 1:
            raise DocParseError(f"{where}: found the column {len(hits)} times, expected 1")
        comment = [block[hits[0]].partition("--")[2]]
        for line in block[hits[0] + 1 :]:
            if not line.strip().startswith("--"):
                break
            comment.append(line.strip().removeprefix("--"))
        return pipe_list(" ".join(comment), where)

    return parse


def column(table_row_prefix: str, name: str) -> Parser:
    def parse(text: str) -> list[str]:
        return slash_list(line_starting(text, table_row_prefix), name, f"{table_row_prefix} {name}")

    return parse


# ── arch 4.5 fixed lists ─────────────────────────────────────────────────────────────────────


def fixed_lists(text: str) -> str:
    return section(text, "### 4.5")


def labelled(text: str, label: str) -> str:
    return split_once(line_starting(fixed_lists(text), label), label, label)[1]


def categories(text: str) -> list[str]:
    return code_list(labelled(text, "**Categories:**"), "4.5 Categories")


def purposes(text: str) -> list[str]:
    where = "4.5 Purposes table"
    lines = fixed_lists(text).splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("**Purposes**")]
    if len(starts) != 1:
        raise DocParseError(f"{where}: found {len(starts)} **Purposes** headings, expected 1")
    table: list[str] = []
    for line in lines[starts[0] + 1 :]:
        if line.startswith("|"):
            table.append(line)
        elif table:
            break
    if len(table) < 3 or not re.fullmatch(r"\|(-+\|)+", table[1]):
        raise DocParseError(f"{where}: no header + separator + rows")
    values = []
    for row in table[2:]:
        match = re.match(r"\| `([^`]*)` \|", row)
        if not match:
            raise DocParseError(f"{where}: row without a `value` first cell: {row[:40]!r}")
        values.append(value(match.group(1), where))
    return values


def household_line(text: str) -> tuple[str, str]:
    return split_once(labelled(text, "**Household-scaled categories:**"), " Not scaled", "4.5")


def household_scaled(text: str) -> list[str]:
    return code_list(household_line(text)[0], "4.5 household-scaled")


def not_household_scaled(text: str) -> list[str]:
    _, listed = split_once(household_line(text)[1], "):", "4.5 not scaled")
    return code_list(listed, "4.5 not scaled")


def never_asked(text: str) -> list[str]:
    listed, _ = split_once(
        labelled(text, "**Never asked about:**"), " and any sensitive fact", "4.5 never asked"
    )
    return code_list(listed, "4.5 never asked")


# ── other doc lists ──────────────────────────────────────────────────────────────────────────


def ledger_statuses(text: str) -> list[str]:
    # 4.1: `day_ledger (user_id, date, budget, spent, status)  -- ok | warning | overspent | under`
    where = "4.1 day_ledger"
    header = sql_block(section(text, "### 4.1"), "day_ledger", where)[0]
    return pipe_list(header.partition("--")[2], where)


def agent_events_clauses(text: str) -> dict[str, str]:
    """The 4.4 `agent_events` row, split at ";": every clause must be a known one."""
    where = "4.4 agent_events row"
    cell = line_starting(text, "| `agent_events` |").removeprefix("| `agent_events` |")
    clauses: dict[str, str] = {}
    for clause in (part.strip() for part in cell.removesuffix("|").split(";")):
        heads = [head for head in AGENT_EVENTS_CLAUSES if clause.startswith(head)]
        if len(heads) != 1 or heads[0] in clauses:
            raise DocParseError(f"{where}: unexpected or repeated clause {clause[:40]!r}")
        clauses[heads[0]] = clause
    if set(clauses) != set(AGENT_EVENTS_CLAUSES):
        raise DocParseError(f"{where}: missing {set(AGENT_EVENTS_CLAUSES) - set(clauses)}")
    return clauses


def agent_event_types(text: str) -> list[str]:
    # 4.1 `-- types: a, b,` + its `--  c, d` lines, then the 4.4 row's "new types `x`, `y`".
    where = "4.1 agent_events types"
    lines = section(text, "### 4.1").splitlines()
    hits = [i for i, line in enumerate(lines) if "-- types:" in line]
    if len(hits) != 1:
        raise DocParseError(f"{where}: found {len(hits)} `-- types:` comments, expected 1")
    words = [lines[hits[0]].partition("-- types:")[2]]
    for line in lines[hits[0] + 1 :]:
        if not line.strip().startswith("--"):
            break
        words.append(line.strip().removeprefix("--"))
    original = [value(word, where) for word in " ".join(words).split(",")]
    new = agent_events_clauses(text)["new types "].removeprefix("new types ")
    return original + code_list(new, "4.4 agent_events new types")


def agent_event_statuses(text: str) -> list[str]:
    # 4.4 row: status `pending → asked → answered / handled / expired`
    where = "4.4 agent_events status"
    match = re.fullmatch(r"status `([^`]+)`", agent_events_clauses(text)["status "])
    if not match:
        raise DocParseError(f"{where}: not a single `a → b / c` lifecycle")
    return [value(part, where) for part in re.split(r"→|/", match.group(1))]


def life_event_types(text: str) -> list[str]:
    # 6.2: the add_life_event schema, `"type": {"type": "string", "enum": [...]}`
    where = "6.2 add_life_event type"
    pattern = r'"type":\s*\{"type": "string", "enum": (\[[^\]]*\])'
    found = re.findall(pattern, section(text, "### 6.2"))
    if len(found) != 1:
        raise DocParseError(f"{where}: found {len(found)} enums, expected 1")
    items: list[object] = json.loads(found[0])
    if not all(isinstance(item, str) for item in items):
        raise DocParseError(f"{where}: every enum item must be a string")
    return [value(str(item), where) for item in items]


def message_roles(text: str) -> list[str]:
    # 9.3: "Only `user` and `assistant` messages are returned."
    where = "9.3 message roles"
    line = line_starting(section(text, "### 9.3"), "Only `")
    match = re.fullmatch(r"Only `([^`]*)` and `([^`]*)` messages are returned\..*", line)
    if not match:
        raise DocParseError(f"{where}: the sentence changed: {line[:60]!r}")
    return [value(role, where) for role in match.groups()]


def priority_levels(text: str) -> list[str]:
    # 4.4 life_facts.value examples: {"category":"concerts","priority":"protected"} / …"reduce"
    where = "4.4 life_facts.value priority"
    block = "\n".join(sql_block(section(text, "### 4.4"), "life_facts", where))
    found = re.findall(r'"priority"\s*:\s*"([^"]*)"', block)
    if not found:
        raise DocParseError(f'{where}: no "priority" example')
    return [value(level, where) for level in found]


def household_roles(text: str) -> list[str]:
    # work-breakdown F2 validation rules: `household_member` needs `role ∈ {adult, child}`
    where = "work-breakdown F2 role rule"
    found = re.findall(r"`role ∈ \{([^}]*)\}`", text)
    if len(found) != 1:
        raise DocParseError(f"{where}: found {len(found)} rules, expected 1")
    return [value(role, where) for role in found[0].split(",")]
