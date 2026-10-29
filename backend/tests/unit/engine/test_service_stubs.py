"""S0: the engine's §15 shells are importable and return the documented types (danutu's, D42)."""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.clock import FixedClock, use_clock
from app.domain.enums import Direction
from app.domain.models import TxView
from app.domain.results import Forecast, PlanSummary, SimResult
from app.engine import service


def _tx(direction: Direction, amount: str, effective: str) -> TxView:
    return TxView(
        id=1, occurred_at=datetime(2026, 6, 15, 10, 5, tzinfo=UTC), merchant_raw="MEGA IMAGE 0451",
        direction=direction, amount=Decimal(amount), effective_amount=Decimal(effective),
    )  # fmt: skip


def test_ledger_delta_debit_and_credit() -> None:
    assert service.ledger_delta(_tx(Direction.DEBIT, "500", "100")) == (
        Decimal("-500.00"),
        Decimal("100.00"),
    )
    assert service.ledger_delta(_tx(Direction.CREDIT, "7000", "7000")) == (
        Decimal("7000.00"),
        Decimal("0.00"),
    )


def test_recompute_plan_fixed_summary() -> None:
    with use_clock(FixedClock(datetime(2026, 6, 15, 9, 0, tzinfo=UTC))):
        plan = service.recompute_plan(None, 1, "new transactions")
    assert isinstance(plan, PlanSummary)
    assert plan.version == 1
    assert plan.feasible is True
    assert plan.today_budget == Decimal("150.00")
    assert plan.next_7_days[0].date == date(2026, 6, 15)
    assert plan.reason == "new transactions"


def test_forecast_goal_is_078() -> None:
    forecast = service.forecast_goal(None, 1, 1)
    assert isinstance(forecast, Forecast)
    assert forecast.probability == 0.78
    assert forecast.p10 <= forecast.p50 <= forecast.p90


def test_simulate_plan_saves_nothing_and_has_a_probability() -> None:
    result = service.simulate_plan(None, 1, {"goal_amount": 12000})
    assert isinstance(result, SimResult)
    assert result.probability == 0.78
    assert result.diff_vs_current.today_budget == Decimal("0.00")


def test_the_other_shells() -> None:
    tx = _tx(Direction.DEBIT, "500", "500")
    service.apply_transaction(None, 1, 1)  # returns None (a no-op until B3)
    service.on_annotation_changed(None, 1, 1, tx, tx.replace(effective_amount="100"))
    assert service.recompute_baselines(None, 1) == {}
    assert service.own_share_estimate(None, 1, tx) == Decimal("500.00")
    assert service.auto_save(None, 1, 9) is None
