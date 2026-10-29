"""C8: learning rules (arch 5.3.7): matching, learning, corrections, decay, acceptance #9."""

from datetime import date, time, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app import clock
from app.context import rules as learning
from app.context import service
from app.context.evaluate import evaluate
from app.context.rules import best_rule, decay, explicit_rule, learn, rule_matches
from app.domain.enums import AnnotationSource, Decision, Purpose, RuleKind, RuleSource
from app.domain.models import PatternRule, RuleMatch, RuleOutcome, TxView
from app.domain.results import RuleChange
from tests.builders import at, matei_ctx, returning, rule, tx

FRIDAY = date(2026, 6, 12)  # the Friday before the demo Monday


def lunch(
    day: date = FRIDAY, hour: int = 13, minute: int = 10, amount: str = "95", **extra: Any
) -> TxView:
    """A team lunch at the Trattoria, explained by the user (social_connection)."""
    fields: dict[str, Any] = {
        "id": 900 + day.toordinal() % 97,
        "occurred_at": at(day, hour, minute),
        "merchant_raw": "TRATTORIA BUONGUSTO",
        "merchant": None,
        "merchant_id": None,
        "mcc": "5812",
        "category": "restaurants",
        "amount": amount,
        "effective_amount": amount,
        "purpose": "social_connection",
        "annotation_source": "answer",
    }
    return tx(**{**fields, **extra})


# ── rule_matches ─────────────────────────────────────────────────────────────────────────────


def test_matei_friday_lunch_matches_his_rule() -> None:
    assert rule_matches(rule(), lunch())


@pytest.mark.parametrize(
    ("change", "matches"),
    [
        ({"category": "groceries"}, False),
        ({"occurred_at": at(date(2026, 6, 11), 13, 10)}, False),  # Thursday
        ({"occurred_at": at(FRIDAY, 12, 0)}, True),  # window start, inclusive
        ({"occurred_at": at(FRIDAY, 15, 0)}, True),  # window end, inclusive
        ({"occurred_at": at(FRIDAY, 11, 59)}, False),
        ({"occurred_at": at(FRIDAY, 15, 1)}, False),
        ({"amount": "60", "effective_amount": "60"}, True),  # amount_min, inclusive
        ({"amount": "59.99", "effective_amount": "59.99"}, False),
        ({"amount": "260", "effective_amount": "260"}, True),  # exactly 2x the max
        ({"amount": "260.01", "effective_amount": "260.01"}, False),  # a new situation
    ],
)
def test_each_condition_and_its_boundary(change: dict[str, Any], matches: bool) -> None:
    assert rule_matches(rule(), lunch(**change)) is matches


def test_merchant_condition_and_inactive_rule() -> None:
    at_mega = rule(match={"merchant_id": "mega_image"})
    assert rule_matches(at_mega, tx())
    assert not rule_matches(at_mega, tx(merchant_id="kaufland"))
    assert not rule_matches(rule(active=False), lunch())


def test_a_suppress_rule_matches_but_never_classifies() -> None:
    quiet = rule(id=7, kind="suppress", outcome={}, confidence=0.9,
                 match={"category": "restaurants", "weekdays": [5]})  # fmt: skip
    assert rule_matches(quiet, lunch())
    assert best_rule([quiet], lunch(), RuleKind.CLASSIFY) is None
    ctx = matei_ctx().replace(rules=[quiet])
    reading = evaluate(ctx, lunch(id=999, purpose=None, annotation_source=None, amount="500",
                                  effective_amount="500"))  # fmt: skip
    assert reading.decision is Decision.AUTO  # would have been asked: suppressed
    assert reading.annotation_source is not AnnotationSource.RULE
    assert reading.matched_rule_id is None


# ── learn ────────────────────────────────────────────────────────────────────────────────────


def test_two_similar_explanations_create_a_rule_at_0_7() -> None:
    first = lunch(day=FRIDAY - timedelta(days=7), minute=40, amount="100")
    change = learn(lunch(), [first], [])
    assert change is not None
    assert change.action == "created"
    new = change.rule
    assert (new.kind, new.source, new.confidence, new.hits) == (
        RuleKind.CLASSIFY, RuleSource.LEARNED, 0.7, 2
    )  # fmt: skip
    assert new.outcome.purpose is Purpose.SOCIAL_CONNECTION
    assert new.match.category == "restaurants"
    assert new.match.weekdays == (5,)
    assert (new.match.from_, new.match.to) == (time(12), time(15))
    assert (new.match.amount_min, new.match.amount_max) == (Decimal(57), Decimal(140))
    assert rule_matches(new, lunch(day=FRIDAY + timedelta(days=7)))


def test_the_third_similar_explanation_creates_it_at_0_9() -> None:
    history = [lunch(day=FRIDAY - timedelta(days=14)), lunch(day=FRIDAY - timedelta(days=7))]
    change = learn(lunch(), history, [])
    assert change is not None
    assert (change.rule.confidence, change.rule.hits) == (0.9, 3)


@pytest.mark.parametrize(
    ("earlier", "learns"),
    [
        ({"amount": "100", "effective_amount": "100"}, False),  # 141 is +41% of 100
        ({"amount": "100.72", "effective_amount": "100.72"}, True),  # 141 is +39.99%
        ({"day": FRIDAY - timedelta(days=6)}, False),  # a Saturday
        ({"minute": 9, "hour": 12}, False),  # 61 minutes earlier
        ({"minute": 10, "hour": 12}, True),  # exactly 1 h earlier
        ({"category": "groceries"}, False),
        ({"purpose": "work_tool"}, False),  # explained differently
        ({"annotation_source": "auto"}, False),  # not the user's words
    ],
)
def test_what_counts_as_similar(earlier: dict[str, Any], learns: bool) -> None:
    fields = {"day": FRIDAY - timedelta(days=7), "amount": "141", "effective_amount": "141",
              **earlier}  # fmt: skip
    change = learn(lunch(amount="141"), [lunch(**fields)], [])
    assert (change is not None) is learns


def test_one_explanation_or_a_non_answer_teaches_nothing() -> None:
    assert learn(lunch(), [], []) is None
    history = [lunch(day=FRIDAY - timedelta(days=7))]
    assert learn(lunch(annotation_source="auto"), history, []) is None
    assert learn(lunch(purpose="unknown"), history, []) is None


def test_a_confirmation_lifts_the_rule_to_0_9_on_the_third() -> None:
    change = learn(lunch(), [], [rule()])  # Matei's rule: 2 hits at 0.7
    assert change is not None
    assert change.action == "updated"
    assert (change.rule.hits, change.rule.confidence, change.previous_confidence) == (3, 0.9, 0.7)
    assert change.rule.last_hit_at == lunch().occurred_at
    assert learn(lunch(), [], [change.rule]) is None  # the same transaction counts once


def test_an_explicit_recurrence_is_0_9_at_once() -> None:
    stated = explicit_rule(
        RuleKind.CLASSIFY,
        RuleMatch.model_validate({"category": "restaurants", "weekdays": [5]}),
        RuleOutcome(purpose=Purpose.SOCIAL_CONNECTION, label="Prânz cu echipa"),
        at(FRIDAY, 9),
    )
    assert (stated.confidence, stated.source, stated.hits) == (0.9, RuleSource.EXPLICIT, 0)
    change = learn(lunch(), [], [stated.replace(id=3)])
    assert change is not None
    assert change.rule.confidence == 0.9
    assert change.rule.hits == 1


def test_a_correction_counts_a_miss_and_two_deactivate() -> None:
    first = learn(lunch(purpose="on_behalf_of_others"), [], [rule()])
    assert first is not None
    assert first.action == "updated"
    assert (first.rule.misses, first.rule.active, first.rule.confidence) == (1, True, 0.7)
    second = learn(lunch(purpose="on_behalf_of_others", amount="90"), [], [first.rule])
    assert second is not None
    assert second.action == "deactivated"
    assert (second.rule.misses, second.rule.active) == (2, False)


def test_a_correction_of_a_rule_reading_counts_even_outside_its_window() -> None:
    edited = lunch(occurred_at=at(FRIDAY, 16), purpose="work_tool", matched_rule_id=1,
                   annotation_source="user_edit")  # fmt: skip
    change = learn(edited, [], [rule()])
    assert change is not None
    assert change.rule.misses == 1


# ── decay ────────────────────────────────────────────────────────────────────────────────────


def _hit(days_ago: int, **extra: Any) -> PatternRule:
    return rule(last_hit_at=at(FRIDAY - timedelta(days=days_ago), 13), **extra)


def test_no_hit_in_60_days_costs_0_2() -> None:
    assert decay([_hit(59)], FRIDAY) == []
    [change] = decay([_hit(60, hits=3, confidence=0.9)], FRIDAY)
    assert (change.action, change.rule.confidence, change.previous_confidence) == (
        "updated", 0.7, 0.9
    )  # fmt: skip
    assert decay([change.rule], FRIDAY) == []  # idempotent on the same day


def test_below_0_5_deactivates() -> None:
    [at_half] = decay([_hit(60)], FRIDAY)  # 0.7 → 0.5: still active
    assert (at_half.rule.confidence, at_half.rule.active) == (0.5, True)
    [gone] = decay([_hit(120)], FRIDAY)  # 0.7 → 0.3
    assert (gone.action, gone.rule.active) == ("deactivated", False)
    assert decay([_hit(200, active=False)], FRIDAY) == []


def test_decay_counts_from_creation_without_a_hit() -> None:
    created = rule(created_at=at(FRIDAY - timedelta(days=61)), last_hit_at=None)
    [change] = decay([created], FRIDAY)
    assert change.rule.confidence == 0.5


# ── acceptance #9 and the shell ──────────────────────────────────────────────────────────────


def test_9_matei_third_friday_lunch_is_auto_prinz_cu_echipa() -> None:
    ctx = matei_ctx()  # two Friday lunches explained (May 29, Jun 5) → his rule at 0.7
    third = lunch(id=950, purpose=None, annotation_source=None, decision=None)
    reading = evaluate(ctx, third)
    assert reading.decision is Decision.AUTO
    assert reading.purpose is Purpose.SOCIAL_CONNECTION
    assert reading.explanation is not None
    assert "Prânz cu echipa" in reading.explanation
    confirmed = learn(third.replace(purpose=Purpose.SOCIAL_CONNECTION,
                                    annotation_source=AnnotationSource.ANSWER),
                      ctx.transactions, ctx.rules)  # fmt: skip
    assert confirmed is not None
    assert confirmed.rule.confidence == 0.9
    fourth = lunch(day=FRIDAY + timedelta(days=7), id=951, purpose=None, annotation_source=None)
    later = evaluate(ctx.replace(rules=[confirmed.rule]), fourth)
    assert (later.decision, later.annotation_source, later.matched_rule_id) == (
        Decision.AUTO, AnnotationSource.RULE, 1
    )  # fmt: skip
    assert later.explanation == "Prânz cu echipa, nu te mai întreb de asta."


def test_a_learned_rule_without_a_label_reads_its_category() -> None:
    ctx = matei_ctx().replace(rules=[rule(outcome={"purpose": "social_connection"})])
    reading = evaluate(ctx, lunch(id=950, purpose=None, annotation_source=None))
    assert reading.explanation == "Restaurante, ca de obicei."


class _Rules:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def create(self, db: Any, user_id: int, new: PatternRule) -> PatternRule:
        self.calls.append(("create", user_id))
        return new.replace(id=42)

    async def record_hit(self, db: Any, user_id: int, rule_id: int) -> PatternRule:
        self.calls.append(("record_hit", rule_id))
        return rule(hits=3)

    async def record_miss(self, db: Any, user_id: int, rule_id: int) -> PatternRule:
        self.calls.append(("record_miss", rule_id))
        return rule(misses=1)

    async def set_confidence(
        self, db: Any, user_id: int, rule_id: int, value: float
    ) -> PatternRule:
        self.calls.append(("set_confidence", value))
        return rule(confidence=value)

    async def deactivate(self, db: Any, user_id: int, rule_id: int) -> PatternRule:
        self.calls.append(("deactivate", rule_id))
        return rule(active=False)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> _Rules:
    fake = _Rules()
    monkeypatch.setattr(service, "_service", lambda name: {"pattern_rules": fake}[name])
    return fake


async def test_learn_from_annotation_stores_the_confirmation(
    monkeypatch: pytest.MonkeyPatch, store: _Rules
) -> None:
    third = lunch(id=950)
    monkeypatch.setattr(service, "_transaction", returning(third))
    monkeypatch.setattr(service, "_context", returning(matei_ctx()))
    with clock.use_clock(clock.FixedClock(at(FRIDAY, 14))):
        change = await service.learn_from_annotation(None, 1, 950)
    assert change is not None
    assert change.rule.confidence == 0.9
    assert store.calls == [("record_hit", 1), ("set_confidence", 0.9)]


async def test_learn_from_annotation_stores_a_new_rule_or_nothing(
    monkeypatch: pytest.MonkeyPatch, store: _Rules
) -> None:
    ctx = matei_ctx().replace(rules=[])
    monkeypatch.setattr(service, "_context", returning(ctx))
    monkeypatch.setattr(service, "_transaction", returning(lunch(id=950)))
    with clock.use_clock(clock.FixedClock(at(FRIDAY, 14))):
        change = await service.learn_from_annotation(None, 1, 950)
        assert change is not None
        assert change.rule.id == 42
        assert store.calls == [("create", 1)]
        monkeypatch.setattr(service, "_transaction", returning(tx(annotation_source="auto")))
        assert await service.learn_from_annotation(None, 1, 1) is None


async def test_save_rule_change_deactivates_after_decay(store: _Rules) -> None:
    [change] = decay([_hit(120)], FRIDAY)
    saved = await service.save_rule_change(None, 1, _hit(120), change)
    assert store.calls == [("set_confidence", 0.3), ("deactivate", 1)]
    assert isinstance(saved, RuleChange)
    assert saved.rule.active is False


def test_the_constants_follow_the_architecture() -> None:
    assert (learning.LEARNED_CONFIDENCE, learning.CONFIRMED_CONFIDENCE) == (0.7, 0.9)
    assert (learning.DECAY_DAYS, learning.DECAY_STEP, learning.MIN_CONFIDENCE) == (60, 0.2, 0.5)
    assert learning.AMOUNT_LIMIT == 2
