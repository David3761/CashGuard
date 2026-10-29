from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.domain.enums import AgentEventType, Category, PotKind
from app.domain.models import PlanPreferences
from app.domain.results import PlanResult, PlanSummary
from app.pipeline.signals import day_status, detect_signals
from tests.builders import (
    agent_event as make_agent_event,
)
from tests.builders import (
    ctx,
    replace,
    tx,
)
from tests.builders import (
    goal as make_goal,
)
from tests.builders import (
    pot as make_pot,
)

D = Decimal
TODAY = date(2026, 6, 17)  # Wednesday
SUNDAY = date(2026, 6, 21)
GOAL = make_goal(id=1, amount=D("10000"), deadline=date(2026, 12, 31))
GOAL_POT = make_pot(
    id=9, name="Fond", kind=PotKind.GOAL, target=D("10000"), saved=D("5200"), goal_id=1
)


@dataclass(frozen=True)
class Day:
    date: date
    budget: Decimal
    spent: Decimal


def plan(feasible: bool = True) -> PlanResult:
    return PlanResult(
        today_budget=D("100"),
        days=(),
        next_7_days=(),
        feasible=feasible,
        infeasible_days=(),
        available=D("0"),
        free_money=D("0"),
        still_to_save=D("0"),
    )


def signals(spent: str, budget: str = "100", **kw: Any) -> set[AgentEventType]:
    c = kw.pop("c", ctx(goal=GOAL, goal_pot=GOAL_POT))
    return {
        s.type
        for s in detect_signals(
            c, Day(kw.pop("on", TODAY), D(budget), D(spent)), kw.pop("p", plan()), None, None, **kw
        )
    }


# ── warning / overspend ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("spent", "expected"),
    [
        ("89.99", set()),
        ("90.00", set()),  # exactly 0.9 x budget is still fine
        ("90.01", {AgentEventType.WARNING}),
        ("100.00", {AgentEventType.WARNING}),  # exactly the budget is not over
        ("100.01", {AgentEventType.OVERSPEND}),
    ],
)
def test_warning_and_overspend_thresholds(spent: str, expected: set[AgentEventType]) -> None:
    assert signals(spent) == expected


@pytest.mark.parametrize(
    ("spent", "closed", "expected"),
    [
        ("49.99", True, "under"),
        ("50.00", True, "ok"),
        ("49.99", False, "ok"),  # "under" only when the day closes
        ("90.01", False, "warning"),
        ("100.01", True, "overspent"),
    ],
)
def test_day_status(spent: str, closed: bool, expected: str) -> None:
    assert day_status(D(spent), D("100"), closed=closed) == expected


# ── underspend week (at close, on Sunday) ────────────────────────────────────


def week(spent_share: str) -> list[Day]:
    monday = SUNDAY - timedelta(6)
    return [Day(monday + timedelta(i), D("100"), D("100") * D(spent_share)) for i in range(7)]


@pytest.mark.parametrize(("share", "fires"), [("0.80", True), ("0.81", False), ("0.50", True)])
def test_underspend_week_at_twenty_percent(share: str, fires: bool) -> None:
    got = signals("0", on=SUNDAY, week=week(share), at_close=True)
    assert (AgentEventType.UNDERSPEND_WEEK in got) is fires


def test_underspend_week_only_at_sunday_close() -> None:
    assert AgentEventType.UNDERSPEND_WEEK not in signals(
        "0", on=SUNDAY, week=week("0.5"), at_close=False
    )
    assert AgentEventType.UNDERSPEND_WEEK not in signals("0", week=week("0.5"), at_close=True)


# ── category caps ────────────────────────────────────────────────────────────


def glovo(amount: str, day: date) -> Any:
    return tx(
        category=Category.FOOD_DELIVERY,
        amount=D(amount),
        effective_amount=D(amount),
        occurred_at=datetime(day.year, day.month, day.day, 9, 0, tzinfo=UTC),
    )


def capped_ctx(*amounts: str) -> Any:
    monday = TODAY - timedelta(TODAY.weekday())
    prefs = PlanPreferences(category_caps={Category.FOOD_DELIVERY: D("100")})
    return ctx(
        goal=GOAL,
        goal_pot=GOAL_POT,
        plan_preferences=prefs,
        transactions=[glovo(a, monday + timedelta(i)) for i, a in enumerate(amounts)],
    )


@pytest.mark.parametrize(
    ("amounts", "level"),
    [
        (("79.99",), None),
        (("40", "40"), 80),
        (("60", "39.99"), 80),
        (("60", "40"), 100),
        (("150",), 100),
    ],
)
def test_category_cap_levels(amounts: tuple[str, ...], level: int | None) -> None:
    drafts = detect_signals(capped_ctx(*amounts), Day(TODAY, D("100"), D("0")), plan(), None, None)
    caps = [s for s in drafts if s.type == AgentEventType.CATEGORY_CAP]
    assert [s.payload["level"] for s in caps] == ([level] if level else [])


def test_last_weeks_spending_does_not_count_towards_this_weeks_cap() -> None:
    c = capped_ctx()
    c = c.model_copy(update={"transactions": [glovo("150", TODAY - timedelta(7))]})
    assert AgentEventType.CATEGORY_CAP not in signals("0", c=c)


# ── plan and goal ────────────────────────────────────────────────────────────


def test_infeasible_plan_fires_when_the_plan_turns_infeasible() -> None:
    was_ok = ctx(
        goal=GOAL,
        goal_pot=GOAL_POT,
        plan=PlanSummary(
            version=3,
            feasible=True,
            today_budget=D("100"),
            previous_today_budget=None,
            next_7_days=(),
        ),
    )
    assert AgentEventType.INFEASIBLE_PLAN in signals("0", c=was_ok, p=plan(feasible=False))
    already_bad = was_ok.model_copy(update={"plan": replace(was_ok.plan, feasible=False)})
    assert AgentEventType.INFEASIBLE_PLAN not in signals("0", c=already_bad, p=plan(feasible=False))


@pytest.mark.parametrize(("saved", "fires"), [("9999.99", False), ("10000", True), ("12000", True)])
def test_goal_completed_when_the_pot_reaches_the_goal(saved: str, fires: bool) -> None:
    c = ctx(goal=GOAL, goal_pot=replace(GOAL_POT, saved=D(saved)))
    assert (AgentEventType.GOAL_COMPLETED in signals("0", c=c)) is fires


def test_goal_completed_only_once() -> None:
    done = ctx(goal=replace(GOAL, status="completed"), goal_pot=replace(GOAL_POT, saved=D("10000")))
    assert AgentEventType.GOAL_COMPLETED not in signals("0", c=done)


def test_dedup_against_existing_events_of_the_same_day() -> None:
    existing = make_agent_event(
        id=1, type=AgentEventType.OVERSPEND, status="pending", event_date=TODAY
    )
    c = ctx(goal=GOAL, goal_pot=GOAL_POT, agent_events=[existing])
    assert AgentEventType.OVERSPEND not in signals("150", c=c)


def test_each_type_at_most_once_per_day() -> None:
    drafts = detect_signals(capped_ctx("150"), Day(TODAY, D("100"), D("150")), plan(), None, None)
    types = [s.type for s in drafts]
    assert len(types) == len(set(types))
