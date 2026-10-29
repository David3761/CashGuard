import subprocess
import sys
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.domain.enums import Category, Direction, FactType, HouseholdRole, PotKind, ReceivableStatus
from app.domain.models import (
    Account,
    FixedCost,
    HouseholdMemberValue,
    IncomeSource,
)
from app.engine.forecast import ForecastInputs, build_forecast_inputs, forecast, is_weekly_snapshot
from app.engine.stats import stable_seed
from tests.builders import (
    ctx,
    fact,
    replace,
    tx,
)
from tests.builders import (
    goal as make_goal,
)
from tests.builders import (
    pot as make_pot,
)
from tests.builders import (
    receivable as make_receivable,
)

BACKEND = Path(__file__).resolve().parents[2]


def test_stable_seed_is_the_same_in_two_separate_processes() -> None:
    # catches Python's hash(), which changes between processes (PYTHONHASHSEED)
    code = (
        "from datetime import date; from app.engine.stats import stable_seed; "
        "print(stable_seed(1, date(2026, 6, 15), 1))"
    )
    runs = {
        subprocess.run(  # noqa: S603 (our own interpreter, a fixed snippet)
            [sys.executable, "-c", code],
            cwd=BACKEND,
            capture_output=True,
            text=True,
            check=True,
            env={"PYTHONHASHSEED": seed},
        ).stdout.strip()
        for seed in ("1", "2")
    }
    assert runs == {str(stable_seed(1, date(2026, 6, 15), 1))}


def test_stable_seed_changes_with_any_part() -> None:
    base = stable_seed(1, date(2026, 6, 15), 1)
    assert base != stable_seed(2, date(2026, 6, 15), 1)
    assert base != stable_seed(1, date(2026, 6, 16), 1)
    assert base != stable_seed(1, date(2026, 6, 15), 2)


D = Decimal
TODAY = date(2026, 6, 15)
SEED = stable_seed(1, TODAY, 1)
SALARY = IncomeSource(id=1, source="Salariu", amount=D("7000"), day_of_month=10)
RENT = FixedCost(id=1, name="Chirie", amount=D("2000"), day_of_month=1)
GOAL = make_goal(id=1, amount=D("10000"), deadline=date(2026, 12, 31))
GOAL_POT = make_pot(
    id=9, name="Fond 10.000", kind=PotKind.GOAL, target=D("10000"), saved=D("5200"), goal_id=1
)


def at(d: date, hour: int = 12) -> datetime:
    return datetime(d.year, d.month, d.day, hour - 3, 0, tzinfo=UTC)


def history(monthly: dict[Category, int], months: int = 4) -> list[Any]:
    """One transaction per category per month (on the 15th), Feb … May, plus the salary and the
    rent."""
    txs: list[Any] = []
    for m in range(2, 2 + months):
        for cat, amount in monthly.items():
            txs.append(
                tx(
                    category=cat,
                    amount=D(amount),
                    effective_amount=D(amount),
                    occurred_at=at(date(2026, m, 15)),
                )
            )
        txs.append(
            tx(
                category=Category.INCOME,
                direction=Direction.CREDIT,
                amount=D("7000"),
                effective_amount=D("7000"),
                occurred_at=at(date(2026, m, 10)),
            )
        )
    return txs


def matei_ctx(**over: object) -> Any:
    base: dict[str, Any] = {
        "account": Account(current_balance=D("5000")),
        "goal": GOAL,
        "goal_pot": GOAL_POT,
        "income_sources": [SALARY],
        "fixed_costs": [RENT],
        "pots": [GOAL_POT],
        "transactions": history(
            {Category.GROCERIES: 1400, Category.RESTAURANTS: 600, Category.FOOD_DELIVERY: 400}
        ),
    }
    base.update(over)
    return ctx(**base)


def inputs(**over: object) -> ForecastInputs:
    return build_forecast_inputs(matei_ctx(**over), TODAY)


# ── build_forecast_inputs ────────────────────────────────────────────────────


def test_inputs_cover_every_month_to_the_deadline() -> None:
    fi = inputs()
    assert fi.months == tuple((2026, m) for m in range(6, 13))
    assert fi.income == (7000.0,) * 7  # June's salary (10 Jun) is part of June's cash flow
    assert fi.fixed == (2000.0,) * 7
    assert (fi.target, fi.saved) == (10000.0, 5200.0)


def test_inputs_bootstrap_from_full_months_only() -> None:
    # Feb starts on the 15th of history? No: the first transaction is 10 Feb, so Feb is partial →
    # Mar, Apr, May
    fi = inputs()
    assert fi.var_history[Category.GROCERIES] == (1400.0, 1400.0, 1400.0)


def test_inputs_current_month_counts_spending_so_far_and_the_others_share() -> None:
    today_mega = tx(
        category=Category.GROCERIES,
        amount=D("500"),
        effective_amount=D("100"),
        occurred_at=at(TODAY),
    )
    base = inputs()
    with_mega = build_forecast_inputs(
        matei_ctx(transactions=[*matei_ctx().transactions, today_mega]), TODAY
    )
    assert with_mega.var_actual - base.var_actual == pytest.approx(
        500.0
    )  # 100 own + 400 paid for others


def test_inputs_temporary_household_member_scales_groceries_only_in_that_month() -> None:
    kids = [
        fact(
            type=FactType.HOUSEHOLD_MEMBER,
            value=HouseholdMemberValue(role=HouseholdRole.CHILD, age=a),
        )
        for a in (7, 11)
    ]
    partner = fact(
        type=FactType.HOUSEHOLD_MEMBER, value=HouseholdMemberValue(role=HouseholdRole.ADULT)
    )
    mother = fact(
        type=FactType.HOUSEHOLD_MEMBER,
        value=HouseholdMemberValue(role=HouseholdRole.ADULT, age=64),
        persistence="temporary",
        # active today (UserContext holds the facts active on as_of, B4) and until the end of July
        valid_from=TODAY,
        valid_to=date(2026, 7, 31),
    )
    fi = inputs(facts=[partner, *kids, mother])
    july = fi.months.index((2026, 7))
    # the history (Mar … May) was spent without her: July costs more, August is back to normal
    assert fi.var_scale[Category.GROCERIES][july] == pytest.approx(2.6 / 2.1)
    assert fi.var_scale[Category.GROCERIES][july + 1] == pytest.approx(1.0)
    assert fi.var_scale[Category.RESTAURANTS][july] == pytest.approx(1.0)


def test_inputs_a_temporary_member_doesnt_lower_the_probability_after_they_leave() -> None:
    """D57: Elena's forecast went 19 % → 92 % the day her mother's two-week stay began."""
    family = [
        fact(type=FactType.HOUSEHOLD_MEMBER, value=HouseholdMemberValue(role=HouseholdRole.ADULT)),
        fact(
            type=FactType.HOUSEHOLD_MEMBER,
            value=HouseholdMemberValue(role=HouseholdRole.CHILD, age=7),
        ),
    ]
    guest = fact(
        type=FactType.HOUSEHOLD_MEMBER,
        value=HouseholdMemberValue(role=HouseholdRole.ADULT, age=64),
        persistence="temporary",
        valid_from=TODAY,
        valid_to=TODAY + timedelta(days=14),
    )
    alone = forecast(inputs(facts=family), n_paths=2000, seed=7)
    visited = forecast(inputs(facts=[*family, guest]), n_paths=2000, seed=7)
    assert visited.p50 < alone.p50  # her two weeks cost something; the months after, nothing


def test_inputs_receivable_lands_in_its_expected_month() -> None:
    r = make_receivable(
        id=1,
        amount=D("400"),
        debtor_label="colegi",
        expected_by=date(2026, 7, 1),
        status=ReceivableStatus.OPEN,
    )
    assert inputs(receivables=[r]).receivables == ((400.0, 0.9, 1),)


def test_inputs_emergency_pot_turns_shocks_off() -> None:
    emergency = make_pot(
        id=5, name="Urgențe", kind=PotKind.EMERGENCY, target=D("3000"), saved=D("1000")
    )
    assert inputs().shocks is True
    assert inputs(pots=[GOAL_POT, emergency]).shocks is False


# ── forecast ─────────────────────────────────────────────────────────────────


def test_probability_is_a_share_and_quantiles_are_ordered() -> None:
    f = forecast(inputs(), seed=SEED)
    assert 0.0 <= f.probability <= 1.0
    assert f.p10 <= f.p50 <= f.p90


def test_goal_already_saved_is_certain() -> None:
    f = forecast(replace(inputs(), saved=12000.0), seed=SEED)
    assert f.probability == 1.0
    assert f.expected_reach_date == TODAY


def test_impossible_target_is_about_zero() -> None:
    f = forecast(replace(inputs(), target=420_000.0), seed=SEED)
    assert f.probability < 0.01
    assert f.expected_reach_date is None


def test_same_seed_same_number() -> None:
    assert forecast(inputs(), seed=SEED) == forecast(inputs(), seed=SEED)


def test_more_income_never_lowers_the_probability() -> None:
    fi = inputs()
    richer = replace(fi, income=tuple(x + 500 for x in fi.income))
    assert forecast(richer, seed=SEED).probability >= forecast(fi, seed=SEED).probability


def test_a_receivable_never_lowers_the_probability() -> None:
    fi = inputs()
    with_r = replace(fi, receivables=((400.0, 0.9, 1),))
    assert forecast(with_r, seed=SEED).probability >= forecast(fi, seed=SEED).probability


def test_an_emergency_pot_never_lowers_the_probability() -> None:
    fi = inputs()
    assert (
        forecast(replace(fi, shocks=False), seed=SEED).probability
        >= forecast(fi, seed=SEED).probability
    )


def test_irregular_income_has_a_wider_band_than_a_salary_with_the_same_mean() -> None:
    fi = inputs()
    irregular = replace(
        fi, income=(0.0,) * 7, income_history=(4000.0, 10000.0, 7000.0, 3000.0, 11000.0)
    )
    salaried, tips = forecast(fi, seed=SEED), forecast(irregular, seed=SEED)
    assert tips.p90 - tips.p10 > salaried.p90 - salaried.p10


def test_reach_date_is_none_when_the_median_misses_the_target() -> None:
    f = forecast(replace(inputs(), target=60_000.0), seed=SEED)
    assert f.p50 < D("60000")
    assert f.expected_reach_date is None


def test_zero_history_uses_the_priors_without_crashing() -> None:
    fi = replace(inputs(), var_history={}, var_prior={Category.GROCERIES: 1400.0})
    assert 0.0 <= forecast(fi, seed=SEED).probability <= 1.0


def test_ten_thousand_paths_seven_months_is_fast() -> None:
    fi = inputs()
    forecast(fi, seed=SEED)  # warm-up
    start = time.perf_counter()
    forecast(fi, n_paths=10_000, seed=SEED)
    assert time.perf_counter() - start < 0.25  # budget 100 ms, margin for CI


# ── weekly snapshot rule ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("today", "last", "expected"),
    [
        (TODAY, None, True),  # Monday, never snapshotted
        (TODAY, TODAY - timedelta(7), True),  # last week's Monday
        (TODAY, TODAY, False),  # already today
        (TODAY + timedelta(3), TODAY, False),  # Thursday, Monday's snapshot exists
        (TODAY + timedelta(3), TODAY - timedelta(1), True),  # last one was on Sunday
    ],
)
def test_weekly_snapshot_once_per_week(today: date, last: date | None, expected: bool) -> None:
    assert is_weekly_snapshot(today, last) is expected
