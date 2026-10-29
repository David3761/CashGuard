"""C4: the signature library and `signatures_for_fact` (work-breakdown C4, arch 5.3.3)."""

import logging
from typing import Any

import pytest

from app.context.library import load_library, signatures_for_fact
from app.domain.enums import (
    Category,
    FactType,
    Purpose,
    SignatureEffect,
    SignatureOrigin,
)
from app.domain.models import Signature
from tests.builders import fact

E, P = SignatureEffect, Purpose


def _summary(
    signatures: list[Signature],
) -> set[tuple[SignatureEffect, Category | None, Purpose]]:
    return {(s.effect, s.category, s.purpose) for s in signatures}


# ── the library file ─────────────────────────────────────────────────────────────────────────


def test_library_has_about_forty_valid_entries() -> None:
    entries = load_library()
    assert 35 <= len(entries) <= 60
    for entry in entries:
        for signature in entry.signatures:
            assert signature.origin is SignatureOrigin.LIBRARY
            assert signature.multiplier is None  # household scaling is E6's (D50)


def test_no_duplicate_keys_or_synonyms_within_a_type() -> None:
    entries = load_library()
    assert len({entry.key for entry in entries}) == len(entries)
    seen: dict[tuple[FactType, tuple[str, ...]], str] = {}
    for entry in entries:
        for fact_type in entry.types:
            for synonym in entry.synonym_tokens():
                assert seen.setdefault((fact_type, synonym), entry.key) == entry.key, synonym


def test_no_health_signature_in_the_library() -> None:
    for entry in load_library():
        assert all(s.category is not Category.HEALTH_PHARMACY for s in entry.signatures)


# ── lookup ───────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "title", ["analist sportiv", "Analist Sportiv", "analist sportiv la o televiziune"]
)
def test_andreis_occupation_gives_tv_and_streaming_as_work_tool(title: str) -> None:
    signatures = signatures_for_fact(
        fact(FactType.OCCUPATION, id=11, value={"title": title, "work_mode": "remote"})
    )
    assert _summary(signatures) == {
        (E.EXPLAINS, Category.ELECTRONICS, P.WORK_TOOL),
        (E.EXPLAINS, Category.SUBSCRIPTIONS, P.WORK_TOOL),
    }
    tv = next(s for s in signatures if s.category is Category.ELECTRONICS)
    assert "televizor" in tv.item_keywords
    assert tv.replacement_cycle_days == 900
    assert all(s.fact_id == 11 and s.origin is SignatureOrigin.LIBRARY for s in signatures)


def test_a_kid_of_seven_expects_school_supplies_and_1_iunie() -> None:
    signatures = signatures_for_fact(
        fact(FactType.HOUSEHOLD_MEMBER, value={"role": "child", "age": 7})
    )
    events = {
        (s.category, s.time_window.months if s.time_window else ())
        for s in signatures
        if s.effect is E.EXPECTS_EVENT
    }
    assert events == {(Category.BOOKS, (8, 9)), (Category.KIDS, (6,))}
    assert all(s.multiplier is None for s in signatures)


def test_a_kid_of_fifteen_has_no_1_iunie_and_an_adult_has_nothing() -> None:
    teen = signatures_for_fact(fact(FactType.HOUSEHOLD_MEMBER, value={"role": "child", "age": 15}))
    assert (Category.KIDS, (6,)) not in {
        (s.category, s.time_window.months) for s in teen if s.time_window
    }
    partner = fact(FactType.HOUSEHOLD_MEMBER, value={"role": "adult", "relation": "partner"})
    assert signatures_for_fact(partner) == []


def test_protected_concerts_give_a_protects_signature() -> None:
    signatures = signatures_for_fact(
        fact(FactType.PRIORITY, value={"category": "concerts", "priority": "protected"})
    )
    assert _summary(signatures) == {(E.PROTECTS, Category.ENTERTAINMENT, P.IDENTITY_JOY)}


def test_a_reduce_priority_protects_nothing() -> None:
    value = {"category": "food_delivery", "priority": "reduce"}
    assert signatures_for_fact(fact(FactType.PRIORITY, value=value)) == []


def test_a_protected_category_name_gets_a_generic_protects() -> None:
    value = {"category": "food delivery", "priority": "protected"}
    signatures = signatures_for_fact(fact(FactType.PRIORITY, value=value))
    assert _summary(signatures) == {(E.PROTECTS, Category.FOOD_DELIVERY, P.IDENTITY_JOY)}


def test_a_trip_takes_its_window_from_the_fact() -> None:
    value = {"name": "Vacanță august", "months": [8]}
    (signature,) = signatures_for_fact(fact(FactType.LIFE_EVENT, value=value))
    assert (signature.category, signature.purpose) == (Category.TRAVEL, P.PLANNED_EVENT)
    assert signature.time_window is not None
    assert signature.time_window.months == (8,)


@pytest.mark.parametrize(
    ("fact_type", "value"),
    [
        (FactType.CUSTOM, {"description": "fac cosplay"}),
        (FactType.OCCUPATION, {"title": "contabilă"}),
        (FactType.CITY, {"name": "Cluj"}),
    ],
)
def test_an_unknown_fact_with_no_llm_signatures_gives_nothing(
    fact_type: FactType, value: dict[str, Any]
) -> None:
    assert signatures_for_fact(fact(fact_type, value=value)) == []
    assert signatures_for_fact(fact(fact_type, value=value), []) == []


# ── Claude's signatures ──────────────────────────────────────────────────────────────────────

COSPLAY = fact(FactType.CUSTOM, id=9, value={"description": "fac cosplay"})
FABRIC = {
    "effect": "explains",
    "category": "household_goods",
    "item_keywords": ["material", "perucă"],
    "purpose": "identity_joy",
    "strength": 0.95,
}
TICKETS = {
    "effect": "explains",
    "category": "entertainment",
    "item_keywords": ["convenție", "bilet"],
    "purpose": "identity_joy",
    "strength": 0.7,
    "confidence_note": "an unknown field",
}


def test_valid_llm_signatures_are_kept_with_origin_llm_and_capped_strength() -> None:
    signatures = signatures_for_fact(COSPLAY, [FABRIC, TICKETS])
    assert [s.category for s in signatures] == [Category.HOUSEHOLD_GOODS, Category.ENTERTAINMENT]
    assert all(s.origin is SignatureOrigin.LLM and s.fact_id == 9 for s in signatures)
    assert [s.strength for s in signatures] == [0.9, 0.7]


@pytest.mark.parametrize(
    ("bad", "reason"),
    [
        ({**FABRIC, "purpose": "good_purchase"}, "invalid"),
        ({**FABRIC, "amount_min": 500, "amount_max": 100}, "invalid"),
        ({**FABRIC, "category": "health_pharmacy"}, "health (sensitive)"),
        ({**FABRIC, "merchant_hints": ["Dr.Max"]}, "health (sensitive)"),
        ({**FABRIC, "item_keywords": ["medicamente"]}, "health (sensitive)"),
        ({**FABRIC, "origin": "library"} | {"effect": "teleport"}, "invalid"),
        ("not an object", "not an object"),
    ],
)
def test_bad_llm_signatures_are_dropped_and_logged(
    bad: object, reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.context.library"):
        assert signatures_for_fact(COSPLAY, [bad]) == []
    assert [record.reason for record in caplog.records] == [reason]  # type: ignore[attr-defined]


def test_claude_cannot_claim_library_origin() -> None:
    (signature,) = signatures_for_fact(COSPLAY, [{**FABRIC, "origin": "library"}])
    assert signature.origin is SignatureOrigin.LLM


def test_the_library_wins_on_the_same_effect_and_category() -> None:
    andrei = fact(FactType.OCCUPATION, value={"title": "analist sportiv"})
    duplicate = {
        "effect": "explains",
        "category": "electronics",
        "purpose": "identity_joy",
        "strength": 0.5,
    }
    signatures = signatures_for_fact(andrei, [duplicate])
    tv = [s for s in signatures if s.category is Category.ELECTRONICS]
    assert len(tv) == 1
    assert (tv[0].origin, tv[0].purpose) == (SignatureOrigin.LIBRARY, P.WORK_TOOL)


@pytest.mark.parametrize("empty", [None, [], {}, "x"])
def test_empty_or_malformed_llm_input_does_not_crash(empty: Any) -> None:
    assert signatures_for_fact(COSPLAY, empty) == []
