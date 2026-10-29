from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest

pytest.importorskip("app.domain", reason="needs F2 app.domain (David G.)")

from app.domain.models import LifeEvent
from app.errors import DomainError

from app.engine.budget import compute_plan, plan_inputs
from app.engine.simulate import apply_changes, simulate, solve
from app.engine.stats import stable_seed
from tests.unit.test_forecast import TODAY
from tests.unit.test_options import goal_ctx

D = Decimal
SEED = stable_seed(1, TODAY, 1)
CONCERT = LifeEvent(id=42, name="Concert", date=date(2026, 7, 4), est_cost=D("400"))


def base() -> Any:
    return goal_ctx("17000", life_events=[CONCERT])


def today_budget(c: object, **changes: object) -> Decimal:
    plan = compute_plan(plan_inputs(apply_changes(c, changes), TODAY, D("0")), TODAY)
    assert plan is not None
    return plan.today_budget


# ── what-if ──────────────────────────────────────────────────────────────────


def test_no_changes_gives_the_current_numbers() -> None:
    result = simulate(base(), TODAY, {}, seed=SEED)
    assert result.diff_vs_current == {"today_budget": D("0.00"), "probability": 0.0}


@pytest.mark.parametrize(
    ("changes", "budget_up"),
    [
        ({"income_delta": 500}, True),
        ({"income_delta": -500}, False),
        ({"fixed_cost_delta": 300}, False),
        ({"remove_event_ids": [42]}, True),
        ({"add_events": [{"name": "PS5", "date": "2026-07-20", "est_cost": 2500}]}, False),
        ({"goal_amount": 15000}, True),
        ({"deadline": "2027-03-31"}, True),
        ({"buffer_pct": 0}, True),
    ],
)
def test_each_change_moves_the_daily_budget_the_right_way(changes: dict[str, Any], budget_up: bool) -> None:
    diff = simulate(base(), TODAY, changes, seed=SEED).diff_vs_current["today_budget"]
    assert (diff > 0) is budget_up


def test_a_ps5_lowers_the_probability() -> None:
    result = simulate(
        base(), TODAY, {"add_events": [{"name": "PS5", "date": "2026-07-20", "est_cost": 2500}]}, seed=SEED
    )
    assert result.diff_vs_current["probability"] < 0


def test_diff_vs_current_is_the_difference_of_the_two_runs() -> None:
    c = base()
    current = simulate(c, TODAY, {}, seed=SEED)
    changed = simulate(c, TODAY, {"income_delta": 500}, seed=SEED)
    assert changed.diff_vs_current["today_budget"] == changed.today_budget - current.today_budget
    assert changed.diff_vs_current["probability"] == pytest.approx(changed.probability - current.probability)


def test_pins_and_weights_are_applied_to_a_copy() -> None:
    c = base()
    pinned = apply_changes(
        c, {"pin_days": [{"date": "2026-06-20", "amount": 150}], "weekday_weights": {"Sat": 2}}
    )
    assert pinned.plan_preferences.pinned_days == {date(2026, 6, 20): D("150")}
    assert pinned.plan_preferences.weekday_weights["Sat"] == D("2")
    assert c.plan_preferences.pinned_days == {}  # the original is untouched


@pytest.mark.parametrize(
    "changes",
    [
        {"add_events": [{"name": "x", "date": "2026-07-01", "est_cost": -5}]},
        {"buffer_pct": 0.5},
        {"surprise": 1},
    ],
)
def test_invalid_changes_raise(changes: dict[str, Any]) -> None:
    with pytest.raises(DomainError) as err:
        simulate(base(), TODAY, changes, seed=SEED)
    assert err.value.code == "invalid_change"


# ── solve mode ───────────────────────────────────────────────────────────────


def test_solve_earliest_deadline_works_and_the_day_before_does_not() -> None:
    c = base()
    target = today_budget(c) + D("10")
    result = solve(c, TODAY, target, essentials_floor=D("0"))
    needed = result["deadline_needed"]
    assert isinstance(needed, date)
    assert today_budget(c, deadline=needed.isoformat()) >= target
    assert today_budget(c, deadline=(needed - timedelta(1)).isoformat()) < target


def test_solve_target_already_met_keeps_the_current_deadline() -> None:
    c = base()
    result = solve(c, TODAY, today_budget(c) - D("1"), essentials_floor=D("0"))
    assert result["deadline_needed"] == c.goal.deadline


def test_solve_largest_goal_for_the_same_deadline() -> None:
    c = base()
    target = today_budget(c) + D("10")
    amount = solve(c, TODAY, target, essentials_floor=D("0"))["goal_amount_possible"]
    assert isinstance(amount, Decimal)
    assert today_budget(c, goal_amount=str(amount)) >= target
    assert today_budget(c, goal_amount=str(amount + D("1"))) < target


def test_solve_impossible_target_returns_none_with_a_reason() -> None:
    result = solve(base(), TODAY, D("100000"), essentials_floor=D("0"))
    assert result["deadline_needed"] is None and result["goal_amount_possible"] is None
    assert result["reason"] == "target_not_reachable"


def test_simulate_with_target_includes_solve() -> None:
    result = simulate(base(), TODAY, {"target_daily_budget": 40}, seed=SEED)
    assert result.solve is not None and "deadline_needed" in result.solve
