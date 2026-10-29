"""D1: the seeded persona life facts and Matei's rule (arch 16.1, 5.3.2; work-breakdown D1)."""

from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.context.library import signatures_for_fact
from app.domain.enums import (
    Category,
    FactSource,
    FactStatus,
    Purpose,
    RuleKind,
    SignatureEffect,
)
from app.domain.models import LifeFact, LifeFactDraft, PatternRule, Signature
from app.domain.money import parse_json
from app.engine.baselines import household_scale
from app.i18n.text import fold
from tests.unit.datafiles import DATA_DIR

PERSONAS_DIR = DATA_DIR / "personas"
PERSONAS = ("matei", "andrei", "bianca", "ioana", "alex")
AS_OF = date(2026, 6, 15)
# Folded words that would make a fact sensitive (arch 4.5: never stored or inferred).
SENSITIVE = (
    "boala", "bolnav", "diagnostic", "medicament", "tratament", "sarcina", "religie", "biserica",
    "credinta", "etnie", "orientare", "gay", "politic", "partid", "health", "illness", "religion",
)  # fmt: skip


def _load(path: Path) -> Any:
    return parse_json(path.read_bytes())


def _drafts(persona: str) -> list[LifeFactDraft]:
    data = _load(PERSONAS_DIR / persona / "facts.json")
    assert set(data) == {"facts"}
    return [LifeFactDraft.model_validate(raw) for raw in data["facts"]]


def _saved(persona: str) -> list[LifeFact]:
    created = datetime(2026, 1, 1, 9, tzinfo=ZoneInfo("Europe/Bucharest"))
    return [
        LifeFact.model_validate({**draft.model_dump(), "id": i, "created_at": created})
        for i, draft in enumerate(_drafts(persona), start=1)
    ]


def _signatures(persona: str) -> set[tuple[SignatureEffect, Category | None, Purpose]]:
    found: list[Signature] = []
    for fact in _saved(persona):
        found += signatures_for_fact(fact)
    return {(s.effect, s.category, s.purpose) for s in found}


@pytest.mark.parametrize("persona", PERSONAS)
def test_every_facts_file_validates_as_confirmed_seed_facts(persona: str) -> None:
    for draft in _drafts(persona):
        assert (draft.source, draft.status) == (FactSource.SEED, FactStatus.CONFIRMED)
        assert 0.9 <= draft.confidence <= 1.0
        assert draft.active_on(AS_OF)


def test_alex_has_no_facts() -> None:
    assert _drafts("alex") == []


@pytest.mark.parametrize("persona", PERSONAS)
def test_no_sensitive_fact_anywhere(persona: str) -> None:
    text = fold((PERSONAS_DIR / persona / "facts.json").read_text(encoding="utf-8"))
    assert [word for word in SENSITIVE if word in text] == []


def test_matei_signatures() -> None:
    assert _signatures("matei") == {
        (SignatureEffect.EXPLAINS, Category.ELECTRONICS, Purpose.WORK_TOOL),
        (SignatureEffect.EXPLAINS, Category.SUBSCRIPTIONS, Purpose.WORK_TOOL),
        (SignatureEffect.PROTECTS, Category.ENTERTAINMENT, Purpose.IDENTITY_JOY),  # concerts
    }  # food delivery is "reduce": nothing protects or explains it


def test_andrei_signatures_are_the_tv_and_streaming_work_tools() -> None:
    assert _signatures("andrei") == {
        (SignatureEffect.EXPLAINS, Category.ELECTRONICS, Purpose.WORK_TOOL),
        (SignatureEffect.EXPLAINS, Category.SUBSCRIPTIONS, Purpose.WORK_TOOL),
    }


def test_bianca_has_student_signatures_and_nothing_for_a_tv() -> None:
    signatures = _signatures("bianca")
    assert signatures == {
        (SignatureEffect.EXPLAINS, Category.BOOKS, Purpose.SELF_INVESTMENT),
        (SignatureEffect.EXPLAINS, Category.EDUCATION, Purpose.SELF_INVESTMENT),
    }
    assert all(category is not Category.ELECTRONICS for _, category, _ in signatures)


def test_ioana_kids_expect_school_supplies_and_1_iunie() -> None:
    assert _signatures("ioana") == {
        (SignatureEffect.EXPLAINS, Category.KIDS, Purpose.HOUSEHOLD_CARE),
        (SignatureEffect.EXPLAINS, Category.CLOTHING, Purpose.HOUSEHOLD_CARE),
        (SignatureEffect.EXPECTS_EVENT, Category.BOOKS, Purpose.HOUSEHOLD_CARE),
        (SignatureEffect.EXPECTS_EVENT, Category.KIDS, Purpose.HOUSEHOLD_CARE),
    }


@pytest.mark.parametrize(
    ("persona", "scale"),
    [("matei", "1"), ("andrei", "1.5"), ("bianca", "1"), ("ioana", "2.1"), ("alex", "1")],
)
def test_household_scale_with_e6(persona: str, scale: str) -> None:
    assert household_scale(_saved(persona), AS_OF) == Decimal(scale)


def test_mateis_seeded_friday_lunch_rule() -> None:
    data = _load(PERSONAS_DIR / "matei" / "rules.json")
    (rule,) = (PatternRule.model_validate(raw) for raw in data["rules"])
    assert rule.kind is RuleKind.CLASSIFY
    assert (rule.match.category, rule.match.weekdays) == (Category.RESTAURANTS, (5,))
    assert (rule.match.from_, rule.match.to) == (time(12, 0), time(15, 0))
    assert (rule.match.amount_min, rule.match.amount_max) == (Decimal(60), Decimal(130))
    assert (rule.outcome.purpose, rule.outcome.label) == (
        Purpose.SOCIAL_CONNECTION,
        "Prânz cu echipa",
    )
    assert (rule.confidence, rule.hits) == (0.7, 2)


def test_only_matei_has_seeded_rules() -> None:
    assert sorted(path.parent.name for path in PERSONAS_DIR.glob("*/rules.json")) == ["matei"]
