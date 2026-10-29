"""C7: the question policy (arch 5.3.6), acceptance #12, quiet hours, caps, back-off."""

from datetime import date, datetime, timedelta
from typing import Any

import pytest

from app.context.questions import default_reading, pick_question, plan_questions
from app.domain.enums import AnnotationSource, Decision, Purpose
from app.domain.models import AgentEventView
from app.domain.results import QuestionCandidate, QuestionHint
from app.domain.user_context import UserContext
from tests.builders import TODAY, at, matei_ctx, rule, tx

NOON = at(TODAY, 14, 0)
HINT = QuestionHint(reason="basket_ratio", params={"ratio": 6})


def candidate(tx_id: int, unexplained: float, impact: float, when: datetime) -> QuestionCandidate:
    return QuestionCandidate(
        transaction_id=tx_id,
        occurred_at=when,
        unexplained=unexplained,
        goal_impact=impact,
        question_hint=HINT,
    )


def asked(event_id: int, when: datetime, type_: str = "transaction_question", **extra: Any) -> Any:
    data = {"status": "asked", "created_at": when, "asked_at": when} | extra
    return AgentEventView.model_validate({"id": event_id, "type": type_, **data})


def ctx_with(*events: AgentEventView, **overrides: Any) -> UserContext:
    return matei_ctx().replace(recent_questions=list(events), **overrides)


MEGA = candidate(101, 0.72, 0.10, at(TODAY, 13, 5))
SHOPGO = candidate(102, 0.74, 0.07, at(TODAY, 13, 30))


def test_12_two_candidates_one_question_the_other_later() -> None:
    plan = plan_questions([SHOPGO, MEGA], ctx_with(), NOON, sim_mode=False)
    assert plan.ask == MEGA  # 0.072 > 0.0518
    assert plan.ask_later == (SHOPGO,)


def test_today_used_by_an_overspend_question() -> None:
    ctx = ctx_with(asked(1, at(TODAY, 9, 0), "overspend"))
    assert pick_question([MEGA], ctx, NOON, sim_mode=False) is None


def test_a_receivable_reminder_never_uses_the_question() -> None:
    ctx = ctx_with(asked(1, at(TODAY, 9, 0), "receivable_reminder"))
    assert pick_question([MEGA], ctx, NOON, sim_mode=False) == MEGA


@pytest.mark.parametrize(
    ("hour", "minute", "quiet"), [(22, 0, True), (7, 59, True), (8, 0, False), (21, 59, False)]
)
def test_quiet_hours(hour: int, minute: int, quiet: bool) -> None:
    now = at(TODAY, hour, minute)
    early = candidate(101, 0.72, 0.10, at(TODAY, 0, 1))
    picked = pick_question([early], ctx_with(), now, sim_mode=False)
    assert (picked is None) is quiet
    assert pick_question([early], ctx_with(), now, sim_mode=True) == early


def test_weekly_soft_cap() -> None:
    week = [asked(i, at(TODAY + timedelta(days=i - 1), 10)) for i in range(1, 5)]  # Mon-Thu
    friday = TODAY + timedelta(days=4)
    late = candidate(110, 0.9, 0.2, at(friday, 12))
    assert pick_question([late], ctx_with(*week), at(friday, 14), sim_mode=False) is None
    three = week[:3]
    assert pick_question([late], ctx_with(*three), at(friday, 14), sim_mode=False) == late


def test_tie_break_older_first() -> None:
    older = candidate(201, 0.6, 0.1, at(TODAY, 9))
    newer = candidate(200, 0.6, 0.1, at(TODAY, 10))
    assert pick_question([newer, older], ctx_with(), NOON, sim_mode=False) == older


def test_back_off_after_two_ignored() -> None:
    first = asked(1, at(date(2026, 6, 10), 10), status="expired")
    second = asked(2, at(date(2026, 6, 13), 10), status="expired")
    ctx = ctx_with(first, second)
    tomorrow_of_second = at(date(2026, 6, 14), 14)
    late = candidate(300, 0.9, 0.2, at(date(2026, 6, 14), 12))
    assert pick_question([late], ctx, tomorrow_of_second, sim_mode=False) is None
    assert pick_question([MEGA], ctx, NOON, sim_mode=False) == MEGA  # 2 days later
    after_week = at(date(2026, 6, 20), 14)
    weekly = candidate(301, 0.9, 0.2, at(date(2026, 6, 20), 12))
    assert pick_question([weekly], ctx, after_week, sim_mode=False) == weekly


def test_expired_after_48h_and_answered_or_suppressed_skipped() -> None:
    old = candidate(400, 0.9, 0.5, NOON - timedelta(hours=49))
    plan = plan_questions([old], ctx_with(), NOON, sim_mode=False)
    assert (plan.ask, plan.expired) == (None, (old,))
    answered = tx(id=401, annotation_source=AnnotationSource.ANSWER)
    ctx = ctx_with(transactions=[answered])
    assert pick_question([candidate(401, 0.9, 0.5, NOON)], ctx, NOON, sim_mode=False) is None
    lunch = tx(id=402, category="restaurants", amount="20", effective_amount="20")
    suppress = rule(id=9, kind="suppress", match={"category": "restaurants", "amount_max": "30"})
    ctx = ctx_with(transactions=[lunch], rules=[suppress])
    assert pick_question([candidate(402, 0.9, 0.5, NOON)], ctx, NOON, sim_mode=False) is None


def test_default_reading() -> None:
    reading = default_reading(tx(amount="500", effective_amount="100"))
    assert reading.purpose is Purpose.UNPLANNED_DISCRETIONARY
    assert reading.confidence == 0.3
    assert reading.annotation_source is AnnotationSource.DEFAULT
    assert reading.effective_amount == 500
    assert reading.decision is Decision.AUTO
