"""Engine DB shells (arch 15.1) with bomboe's services faked: what they read, write and return."""

import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

pytest.importorskip("app.services.context_loader", reason="needs bomboe's services (B3/B4)")

from app.domain.enums import Category, Direction, PotKind
from app.domain.models import LifeEvent, Pot, Transfer
from app.domain.results import Forecast, PlanSummary
from app.errors import DomainError

from app.engine import service
from tests.builders import tx
from tests.unit.test_forecast import GOAL_POT, TODAY, matei_ctx

D = Decimal
SALARY_DAY = date(2026, 7, 10)


class FakeDB:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, statement: Any, params: Any = None) -> None:
        self.statements.append(str(statement))


class Fakes:
    """Records every service call; `ctx` and `tx` are what the loader / transactions.get return."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, ctx: Any, today: date = TODAY) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.ctx, self.tx, self.today = ctx, None, today
        self.version = 0
        self.transfer: Transfer | None = None
        self.ledger_spent: dict[date, Decimal] = {}

        async def load(db: Any, user_id: int, today: date) -> Any:
            return self.ctx

        async def get_tx(db: Any, user_id: int, tx_id: int) -> Any:
            return self.tx

        async def next_version(db: Any, user_id: int) -> int:
            self.version += 1
            return self.version

        async def get_or_create(db: Any, user_id: int, day: date) -> Any:
            return type("Day", (), {"spent": self.ledger_spent.get(day, D("0"))})()

        async def by_income_tx(db: Any, user_id: int, tx_id: int) -> Any:
            return self.transfer

        async def create_transfer(db: Any, user_id: int, **kw: Any) -> Transfer:
            self._record("transfers.create", (), kw)
            self.transfer = Transfer(
                id=1,
                amount=kw["amount"],
                kind=kw["kind"],
                pot_id=kw["pot_id"],
                income_transaction_id=kw["income_transaction_id"],
            )
            return self.transfer

        async def list_fixed(db: Any, user_id: int) -> Any:
            return self.ctx.fixed_costs

        patches = {
            "load_user_context": load,
            "transactions_service.get": get_tx,
            "plans_service.next_version": next_version,
            "ledger_service.get_or_create": get_or_create,
            "transfers_service.get_by_income_transaction": by_income_tx,
            "transfers_service.create": create_transfer,
            "fixed_costs_service.list": list_fixed,
            "clock.today": lambda: self.today,
        }
        for name in (
            "accounts_service.adjust_balance",
            "ledger_service.update",
            "pots_service.add_saved",
            "pots_service.update",
            "plans_service.create",
            "forecasts_service.save",
            "notifications_service.notify",
            "baselines_service.replace_all",
            "users_service.update_household_scale",
        ):
            patches[name] = self._recorder(name.replace("_service", ""))
        for target, fn in patches.items():
            monkeypatch.setattr(f"app.engine.service.{target}", fn)

    def _record(self, name: str, args: tuple[Any, ...], kw: dict[str, Any]) -> None:
        self.calls.append((name, args, kw))

    def _recorder(self, name: str) -> Any:
        async def record(db: Any, user_id: int, *args: Any, **kw: Any) -> None:
            self._record(name, args, kw)

        return record

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]

    def args(self, name: str) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
        return [(a, k) for n, a, k in self.calls if n == name]


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def at(d: date, hour: int = 12) -> datetime:
    return datetime(d.year, d.month, d.day, hour - 3, 0, tzinfo=UTC)


# ── apply_transaction / on_annotation_changed ────────────────────────────────


def test_apply_transaction_moves_balance_and_day_spent(monkeypatch: pytest.MonkeyPatch) -> None:
    fakes = Fakes(monkeypatch, matei_ctx())
    fakes.tx = tx(amount=D("500"), effective_amount=D("500"), occurred_at=at(TODAY), status="processing")
    run(service.apply_transaction(FakeDB(), 1, 918))
    assert fakes.args("accounts.adjust_balance") == [((D("-500"),), {})]
    assert fakes.args("ledger.update") == [((TODAY,), {"spent": D("500")})]


def test_apply_transaction_twice_is_a_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    fakes = Fakes(monkeypatch, matei_ctx())
    fakes.tx = tx(amount=D("500"), effective_amount=D("500"), status="resolved")
    run(service.apply_transaction(FakeDB(), 1, 918))
    assert fakes.calls == []


def test_on_annotation_changed_moves_only_the_day_spent(monkeypatch: pytest.MonkeyPatch) -> None:
    fakes = Fakes(monkeypatch, matei_ctx())
    fakes.ledger_spent[TODAY] = D("500")
    old = tx(amount=D("500"), effective_amount=D("500"), occurred_at=at(TODAY))
    new = replace(old, effective_amount=D("100"))
    run(service.on_annotation_changed(FakeDB(), 1, old.id, old, new))
    assert fakes.names() == ["ledger.update"]
    assert fakes.args("ledger.update") == [((TODAY,), {"spent": D("100")})]
    fakes.calls.clear()
    run(service.on_annotation_changed(FakeDB(), 1, old.id, new, new))
    assert fakes.calls == []


def test_own_share_estimate_uses_the_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.domain.models import Baseline

    groceries = Baseline(
        category=Category.groceries,
        personal_median=D("85"),
        personal_mad=D("25"),
        n=40,
        prior_median=D("70"),
        household_multiplier=D("1"),
        expected_median=D("85"),
        monthly_expected=D("1400"),
    )
    Fakes(monkeypatch, matei_ctx(baselines={Category.groceries: groceries}))
    assert run(service.own_share_estimate(FakeDB(), 1, tx(amount=D("500")))) == D("85.00")


# ── recompute_plan ───────────────────────────────────────────────────────────


def test_recompute_plan_saves_increasing_versions_with_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    previous = PlanSummary(
        version=0, feasible=True, today_budget=D("50.00"), previous_today_budget=None, next_7_days=[]
    )
    fakes = Fakes(monkeypatch, matei_ctx(latest_plan=previous))
    db = FakeDB()
    summaries = [
        run(service.recompute_plan(db, 1, "new transactions", {"transaction_id": 918})) for _ in range(3)
    ]
    assert [s.version for s in summaries] == [1, 2, 3]
    assert summaries[0].previous_today_budget == D("50.00")
    _, kw = fakes.args("plans.create")[0]
    assert (kw["reason"], kw["trigger_ref"], kw["version"]) == (
        "new transactions",
        {"transaction_id": 918},
        1,
    )
    assert all("pg_advisory_xact_lock" in s for s in db.statements) and len(db.statements) == 3


def test_recompute_plan_without_a_goal_saves_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    fakes = Fakes(monkeypatch, matei_ctx(goal=None))
    assert run(service.recompute_plan(FakeDB(), 1, "seed")) is None
    assert "plans.create" not in fakes.names()


def test_recompute_plan_sets_event_pot_contributions(monkeypatch: pytest.MonkeyPatch) -> None:
    trip = LifeEvent(id=7, name="Vacanță", date=date(2026, 8, 15), est_cost=D("3000"))
    pot = Pot(
        id=3,
        name="Vacanță august",
        kind=PotKind.event,
        target=D("3000"),
        saved=D("0"),
        deadline=date(2026, 8, 15),
        life_event_id=7,
    )
    fakes = Fakes(monkeypatch, matei_ctx(life_events=[trip], pots=[GOAL_POT, pot]))
    run(service.recompute_plan(FakeDB(), 1, "pot"))
    assert fakes.args("pots.update") == [((3,), {"monthly_contribution": D("1500.00")})]


# ── forecast_goal / simulate_plan ────────────────────────────────────────────


def test_forecast_goal_saves_a_weekly_snapshot_on_monday(monkeypatch: pytest.MonkeyPatch) -> None:
    last_week = Forecast(
        probability=0.72,
        p10=D("0"),
        p50=D("0"),
        p90=D("0"),
        expected_reach_date=None,
        sim_date=TODAY - timedelta(7),
    )
    fakes = Fakes(monkeypatch, matei_ctx(last_weekly_snapshot=last_week))
    first = run(service.forecast_goal(FakeDB(), 1, plan_version=4))
    assert first.is_weekly_snapshot and first.last_week_probability == 0.72
    _, kw = fakes.args("forecasts.save")[0]
    assert (kw["plan_version"], kw["sim_date"], kw["forecast"]) == (4, TODAY, first)
    assert run(service.forecast_goal(FakeDB(), 1, plan_version=4)).probability == first.probability


def test_forecast_goal_without_a_goal_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    Fakes(monkeypatch, matei_ctx(goal=None))
    with pytest.raises(DomainError):
        run(service.forecast_goal(FakeDB(), 1, plan_version=1))


def test_simulate_plan_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    fakes = Fakes(monkeypatch, matei_ctx())
    result = run(service.simulate_plan(FakeDB(), 1, {"income_delta": 500}))
    assert result.diff_vs_current["today_budget"] > 0
    assert fakes.calls == []


# ── auto_save ────────────────────────────────────────────────────────────────


def salary_ctx(balance: str = "12000") -> Any:
    from app.domain.models import Account

    return matei_ctx(account=Account(current_balance=D(balance)))


def salary() -> Any:
    return tx(
        amount=D("7000"),
        effective_amount=D("7000"),
        direction=Direction.credit,
        category=Category.income,
        occurred_at=at(SALARY_DAY, 9),
    )


def test_auto_save_moves_the_planned_saving_to_the_goal_pot(monkeypatch: pytest.MonkeyPatch) -> None:
    fakes = Fakes(monkeypatch, salary_ctx(), today=SALARY_DAY)
    fakes.tx = salary()
    transfer = run(service.auto_save(FakeDB(), 1, 501))
    assert transfer is not None and transfer.amount == D("800.00")  # 4 800 left / 6 paydays (10 Jul … 10 Dec)
    assert fakes.args("accounts.adjust_balance") == [((D("-800.00"),), {})]
    assert fakes.args("pots.add_saved") == [((GOAL_POT.id, D("800.00")), {})]
    assert fakes.names().count("notifications.notify") == 1


def test_auto_save_twice_for_the_same_salary_moves_money_once(monkeypatch: pytest.MonkeyPatch) -> None:
    fakes = Fakes(monkeypatch, salary_ctx(), today=SALARY_DAY)
    fakes.tx = salary()
    first = run(service.auto_save(FakeDB(), 1, 501))
    second = run(service.auto_save(FakeDB(), 1, 501))
    assert second == first
    assert fakes.names().count("transfers.create") == 1


def test_auto_save_ignores_credits_that_are_not_a_salary(monkeypatch: pytest.MonkeyPatch) -> None:
    fakes = Fakes(monkeypatch, salary_ctx(), today=SALARY_DAY)
    fakes.tx = replace(salary(), amount=D("150"))  # a refund, not the salary
    assert run(service.auto_save(FakeDB(), 1, 501)) is None
    assert fakes.calls == []


def test_auto_save_with_nothing_to_spare_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    fakes = Fakes(monkeypatch, salary_ctx(balance="1500"), today=SALARY_DAY)
    fakes.tx = salary()
    assert run(service.auto_save(FakeDB(), 1, 501)) is None
    assert "transfers.create" not in fakes.names()
