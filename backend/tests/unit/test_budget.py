import time
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

pytest.importorskip("app.domain", reason="needs F2 app.domain (David G.)")

from app.domain.enums import PotKind, ReceivableStatus
from app.domain.models import FixedCost, Goal, IncomeSource, LifeEvent, PlanPreferences, Pot, Receivable
from app.errors import DomainError

from app.engine.budget import (
    PlanInputs,
    available,
    compute_plan,
    events_remaining,
    expected_income,
    fixed_remaining,
    plan_inputs,
    pot_contributions_remaining,
    still_to_save,
)
from tests.builders import ctx, tx

D = Decimal
TODAY = date(2026, 6, 15)  # Monday
DEADLINE = date(2026, 12, 31)
SALARY = IncomeSource(id=1, source="Salariu", amount=D("7000"), day_of_month=10)
RENT = FixedCost(id=1, name="Chirie", amount=D("2000"), day_of_month=1)
PHONE = FixedCost(id=2, name="Telefon", amount=D("60"), day_of_month=20)
GOAL = Goal(id=1, amount=D("10000"), deadline=DEADLINE)


def matei(**over: object) -> PlanInputs:
    base = PlanInputs(
        goal=GOAL,
        goal_saved=D("5200"),
        balance=D("5000"),
        spent_today=D("0"),
        income_sources=(SALARY,),
        fixed_costs=(RENT, PHONE),
        events=(),
        pots=(),
        receivables=(),
        preferences=PlanPreferences(),
        essentials_floor=D("30"),
    )
    return replace(base, **over)  # type: ignore[arg-type]


# ── the money terms (arch 6.7 definitions) ───────────────────────────────────


def test_expected_income_counts_paydays_from_tomorrow() -> None:
    assert expected_income([SALARY], TODAY, DEADLINE) == D("42000")  # 10 Jul … 10 Dec
    assert expected_income([SALARY], date(2026, 7, 10), date(2026, 7, 31)) == D("0")  # today's salary is in


def test_fixed_remaining_counts_rent_due_later_not_earlier() -> None:
    # phone on 20 Jun is still to pay this month; rent on 1 Jun is paid
    assert fixed_remaining([RENT, PHONE], TODAY, date(2026, 6, 30)) == D("60")
    assert fixed_remaining([RENT, PHONE], TODAY, date(2026, 7, 1)) == D("2060")


def test_fixed_cost_due_today_counts_as_paid() -> None:
    assert fixed_remaining([PHONE], date(2026, 6, 20), date(2026, 6, 30)) == D("0")


def test_events_covered_by_a_pot_are_not_subtracted_twice() -> None:
    trip = LifeEvent(id=7, name="Vacanță", date=date(2026, 8, 15), est_cost=D("3000"))
    concert = LifeEvent(id=8, name="Concert", date=date(2026, 7, 1), est_cost=D("100"))
    pot = Pot(
        id=3,
        name="Vacanță august",
        kind=PotKind.EVENT,
        target=D("3000"),
        saved=D("0"),
        deadline=date(2026, 8, 15),
        life_event_id=7,
    )
    assert events_remaining([trip, concert], [pot], TODAY, DEADLINE) == D("100")
    assert pot_contributions_remaining([pot], [SALARY], TODAY, DEADLINE) == D("3000")


def test_events_outside_the_horizon_or_cancelled_are_ignored() -> None:
    past = LifeEvent(id=1, name="x", date=date(2026, 6, 1), est_cost=D("50"))
    later = LifeEvent(id=2, name="y", date=date(2027, 2, 1), est_cost=D("50"))
    cancelled = LifeEvent(id=3, name="z", date=date(2026, 7, 1), est_cost=D("50"), status="cancelled")
    assert events_remaining([past, later, cancelled], [], TODAY, DEADLINE) == D("0")


def test_pot_ending_after_the_goal_deadline_counts_only_paydays_inside() -> None:
    pot = Pot(
        id=4, name="Mașină", kind=PotKind.CUSTOM, target=D("8000"), saved=D("0"), deadline=date(2027, 4, 30)
    )
    # 10 paydays to 30 Apr 2027 → 800 each; 6 of them before 31 Dec
    assert pot_contributions_remaining([pot], [SALARY], TODAY, DEADLINE) == D("4800")


def test_still_to_save_is_zero_when_the_goal_is_reached() -> None:
    assert still_to_save(D("10000"), D("5200")) == D("4800")
    assert still_to_save(D("10000"), D("12000")) == D("0")


def test_available_adds_receivables_and_spent_today() -> None:
    r = Receivable(
        id=1,
        amount=D("400"),
        debtor_label="colegi",
        expected_by=TODAY + timedelta(14),
        status=ReceivableStatus.OPEN,
    )
    base = available(matei(), TODAY)
    assert available(matei(receivables=(r,)), TODAY) == base + D("360")
    # what was spent today is still part of today's budget (start-of-day view)
    assert available(matei(balance=D("4900"), spent_today=D("100")), TODAY) == base


# ── the daily split ──────────────────────────────────────────────────────────


def total(plan: object) -> Decimal:
    return sum((d.budget for d in plan.days), D("0"))  # type: ignore[attr-defined]


def test_horizon_runs_from_today_to_the_deadline() -> None:
    plan = compute_plan(matei(), TODAY)
    assert plan is not None
    assert (plan.days[0].date, plan.days[-1].date, len(plan.days)) == (TODAY, DEADLINE, 200)
    assert plan.today_budget == plan.days[0].budget
    assert [d.date for d in plan.next_7_days] == [TODAY + timedelta(i) for i in range(1, 8)]


def test_budgets_add_up_exactly_to_free_money() -> None:
    plan = compute_plan(matei(), TODAY)
    assert plan is not None
    assert total(plan) == plan.free_money


def test_pinned_day_gets_exactly_its_amount_and_the_rest_is_shared() -> None:
    pins = {date(2026, 6, 20): D("150.00")}
    plan = compute_plan(matei(preferences=PlanPreferences(pinned_days=pins)), TODAY)
    assert plan is not None
    day = next(d for d in plan.days if d.date == date(2026, 6, 20))
    assert (day.budget, day.pinned) == (D("150.00"), True)
    assert sum(d.budget for d in plan.days if not d.pinned) == plan.free_money - D("150.00")


def test_pinned_total_above_free_money_is_infeasible() -> None:
    pins = {TODAY + timedelta(1): D("50000")}
    plan = compute_plan(matei(preferences=PlanPreferences(pinned_days=pins)), TODAY)
    assert plan is not None and not plan.feasible


def test_day_below_the_essentials_floor_is_infeasible_and_listed() -> None:
    plan = compute_plan(matei(essentials_floor=D("1000")), TODAY)
    assert plan is not None
    assert not plan.feasible
    assert plan.infeasible_days == [d.date for d in plan.days]


def test_weights_move_money_between_days_without_changing_the_total() -> None:
    weekend = PlanPreferences(weekday_weights={"Sat": D("1.5"), "Sun": D("1.5")})
    flat, shaped = compute_plan(matei(), TODAY), compute_plan(matei(preferences=weekend), TODAY)
    assert flat is not None and shaped is not None
    assert total(flat) == total(shaped)
    saturday = date(2026, 6, 20)
    sat = next(d for d in shaped.days if d.date == saturday)
    mon = next(d for d in shaped.days if d.date == date(2026, 6, 22))
    assert sat.weight == D("1.5") and sat.budget > mon.budget


def test_buffer_changes_free_money_by_exactly_its_share_of_available() -> None:
    none, ten = (
        compute_plan(matei(preferences=PlanPreferences(buffer_pct=D(p))), TODAY) for p in ("0", "0.10")
    )
    assert none is not None and ten is not None
    assert none.free_money - ten.free_money == D("0.10") * none.available


def test_receivable_raises_the_daily_budget() -> None:
    r = Receivable(
        id=1,
        amount=D("400"),
        debtor_label="colegi",
        expected_by=TODAY + timedelta(14),
        status=ReceivableStatus.OPEN,
    )
    without, with_r = compute_plan(matei(), TODAY), compute_plan(matei(receivables=(r,)), TODAY)
    assert without is not None and with_r is not None
    assert with_r.today_budget > without.today_budget


@settings(max_examples=40, deadline=None)
@given(weights=st.lists(st.decimals(min_value="0.5", max_value="3", places=2), min_size=7, max_size=7))
def test_any_weights_keep_the_sum_exact(weights: list[Decimal]) -> None:
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    plan = compute_plan(matei(preferences=PlanPreferences(weekday_weights=dict(zip(names, weights)))), TODAY)
    assert plan is not None
    assert total(plan) == plan.free_money


# ── outputs and edge cases ───────────────────────────────────────────────────


def test_golden_matei_plan() -> None:
    # recorded after the first run (E2 step 3); an engine change that moves these must be reviewed
    plan = compute_plan(matei(), TODAY)
    assert plan is not None
    assert (plan.available, plan.free_money, plan.today_budget, plan.feasible) == (
        D("34580.00"),
        D("26322.00"),
        D("131.61"),
        True,
    )


def test_deadline_today_is_a_one_day_horizon() -> None:
    plan = compute_plan(matei(goal=replace(GOAL, deadline=TODAY)), TODAY)
    assert plan is not None and len(plan.days) == 1


def test_deadline_passed_raises() -> None:
    with pytest.raises(DomainError) as err:
        compute_plan(matei(goal=replace(GOAL, deadline=TODAY - timedelta(1))), TODAY)
    assert err.value.code == "deadline_passed"


def test_negative_balance_is_infeasible_without_crashing() -> None:
    plan = compute_plan(matei(balance=D("-90000")), TODAY)
    assert plan is not None and not plan.feasible


def test_no_goal_gives_no_plan() -> None:
    assert compute_plan(matei(goal=None), TODAY) is None


def test_plan_is_deterministic_and_in_cents() -> None:
    first, second = compute_plan(matei(), TODAY), compute_plan(matei(), TODAY)
    assert first == second and first is not None
    assert all(d.budget == d.budget.quantize(D("0.01")) for d in first.days)


def test_two_hundred_day_horizon_under_five_ms() -> None:
    compute_plan(matei(), TODAY)  # warm-up
    start = time.perf_counter()
    for _ in range(10):
        compute_plan(matei(), TODAY)
    assert (time.perf_counter() - start) / 10 < 0.005 * 3  # 5 ms budget, ×3 margin for slow CI


# ── plan_inputs(ctx) ─────────────────────────────────────────────────────────


def test_plan_inputs_reads_the_context_and_today_spending() -> None:
    from app.domain.models import Account
    from app.domain.models import Pot as PotModel

    goal_pot = PotModel(id=9, name="Fond", kind=PotKind.GOAL, target=D("10000"), saved=D("5200"), goal_id=1)
    today_tx = tx(
        effective_amount=D("100"), amount=D("500"), occurred_at=datetime(2026, 6, 15, 10, 5, tzinfo=UTC)
    )
    yesterday_tx = tx(effective_amount=D("40"), occurred_at=datetime(2026, 6, 14, 10, 0, tzinfo=UTC))
    c = ctx(
        account=Account(current_balance=D("4900")),
        goal=GOAL,
        goal_pot=goal_pot,
        income_sources=[SALARY],
        fixed_costs=[RENT],
        pots=[goal_pot],
        transactions=[today_tx, yesterday_tx],
    )
    inputs = plan_inputs(c, TODAY, D("30"))
    assert (inputs.balance, inputs.goal_saved, inputs.spent_today) == (D("4900"), D("5200"), D("100"))
    assert inputs.pots == ()  # the goal pot is the goal, not an event pot
