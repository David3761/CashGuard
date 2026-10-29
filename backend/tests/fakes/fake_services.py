"""In-memory implementations of `app.agent.ports` (A3), the reference for bomboe's Postgres ones.

Each table keeps rows per user; a row of another user raises `not_found` exactly like a missing
id. `FakeEngine` and `FakeContext` record their calls and return small, plausible results.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app import clock
from app.agent.handlers.common import RunState, ToolContext
from app.agent.ports import Annotation, ReceivableDraft, Row, Services
from app.domain.enums import (
    Direction,
    FactStatus,
    GoalStatus,
    Language,
    PotStatus,
    ReceivableStatus,
)
from app.domain.models import (
    DomainModel,
    Goal,
    LifeFact,
    LifeFactDraft,
    PatternRule,
    PlanPreferences,
    Pot,
    Receivable,
    Signature,
    TxView,
)
from app.domain.results import Forecast, PlanSummary, SimDiff, SimResult
from app.errors import DomainError


def not_found(what: str) -> DomainError:
    return DomainError("not_found", f"No such {what} for this user.", 404)


class Table:
    """Rows keyed by id, each owned by one user."""

    def __init__(self, what: str) -> None:
        self.what = what
        self.rows: dict[int, tuple[int, Row]] = {}
        self._next = 1

    def insert(self, user_id: int, data: Mapping[str, Any]) -> Row:
        row = {**data, "id": self._next}
        self.rows[self._next] = (user_id, row)
        self._next += 1
        return dict(row)

    def get(self, user_id: int, record_id: int) -> Row:
        owner, row = self.rows.get(record_id, (None, None))
        if owner != user_id or row is None:
            raise not_found(self.what)
        return dict(row)

    def update(self, user_id: int, record_id: int, changes: Mapping[str, Any]) -> Row:
        self.get(user_id, record_id)
        self.rows[record_id][1].update(changes)
        return self.get(user_id, record_id)

    def list(self, user_id: int) -> list[Row]:
        return [dict(row) for owner, row in self.rows.values() if owner == user_id]

    def remove(self, user_id: int, record_id: int) -> None:
        self.get(user_id, record_id)
        del self.rows[record_id]

    def count(self) -> int:
        return len(self.rows)


class ModelTable[M: DomainModel]:
    """F2 models keyed by id, each owned by one user; `update` re-validates (`replace`)."""

    def __init__(self, what: str, model: type[M]) -> None:
        self.what, self.model = what, model
        self.rows: dict[int, tuple[int, M]] = {}
        self._next = 1

    def insert(self, user_id: int, data: Mapping[str, Any]) -> M:
        row = self.model.model_validate({**data, "id": self._next})
        self.rows[self._next] = (user_id, row)
        self._next += 1
        return row

    def get(self, user_id: int, record_id: int) -> M:
        owner, row = self.rows.get(record_id, (None, None))
        if owner != user_id or row is None:
            raise not_found(self.what)
        return row

    def update(self, user_id: int, record_id: int, changes: Mapping[str, Any]) -> M:
        row = self.get(user_id, record_id).replace(**changes)
        self.rows[record_id] = (user_id, row)
        return row

    def list(self, user_id: int) -> list[M]:
        return [row for owner, row in self.rows.values() if owner == user_id]


class FakeRecords:
    def __init__(self, what: str) -> None:
        self.table = Table(what)

    def create(self, user_id: int, data: Mapping[str, Any]) -> Row:
        return self.table.insert(user_id, data)

    def get(self, user_id: int, record_id: int) -> Row:
        return self.table.get(user_id, record_id)

    def update(self, user_id: int, record_id: int, changes: Mapping[str, Any]) -> Row:
        return self.table.update(user_id, record_id, changes)

    def list(self, user_id: int) -> list[Row]:
        return self.table.list(user_id)

    def remove(self, user_id: int, record_id: int) -> None:
        self.table.remove(user_id, record_id)


class FakeTransactions:
    def __init__(self) -> None:
        self.rows: dict[int, tuple[int, TxView]] = {}
        self.annotations: dict[int, Annotation] = {}

    def add(self, user_id: int, tx: TxView) -> TxView:
        self.rows[tx.id] = (user_id, tx)
        return tx

    def get(self, user_id: int, tx_id: int) -> TxView:
        owner, tx = self.rows.get(tx_id, (None, None))
        if owner != user_id or tx is None:
            raise not_found("transaction")
        return tx

    def list(
        self, user_id: int, since: date, until: date, category: str | None = None
    ) -> list[TxView]:
        return [
            tx
            for owner, tx in self.rows.values()
            if owner == user_id
            and since <= tx.occurred_at.date() <= until
            and (category is None or tx.category == category)
        ]

    def annotate(self, user_id: int, tx_id: int, annotation: Annotation) -> TxView:
        tx = self.get(user_id, tx_id).replace(
            purpose=annotation.purpose,
            beneficiary=annotation.beneficiary,
            effective_amount=annotation.effective_amount,
            annotation_source=annotation.source,
            annotation_confidence=annotation.confidence,
            receivable_id=annotation.receivable_id,
        )
        self.rows[tx_id] = (user_id, tx)
        self.annotations[tx_id] = annotation
        return tx

    def set_pot(self, user_id: int, tx_id: int, pot_id: int) -> TxView:
        tx = self.get(user_id, tx_id).replace(pot_id=pot_id)
        self.rows[tx_id] = (user_id, tx)
        return tx


class FakeReceivables:
    def __init__(self) -> None:
        self.table = ModelTable("receivable", Receivable)

    def create(self, user_id: int, draft: ReceivableDraft) -> Receivable:
        return self.table.insert(
            user_id,
            {
                "transaction_id": draft.transaction_id,
                "debtor_label": draft.debtor_label,
                "amount": draft.amount,
                "people_count": draft.people_count,
                "amount_each": draft.amount_each,
                "expected_by": draft.expected_by,
                "status": ReceivableStatus.OPEN,
                "created_at": clock.now(),
            },
        )

    def get(self, user_id: int, receivable_id: int) -> Receivable:
        return self.table.get(user_id, receivable_id)

    def cancel(self, user_id: int, receivable_id: int) -> Receivable:
        return self.table.update(user_id, receivable_id, {"status": ReceivableStatus.CANCELLED})

    def mark_paid(self, user_id: int, receivable_id: int) -> Receivable:
        return self.table.update(
            user_id, receivable_id, {"status": ReceivableStatus.PAID, "paid_at": clock.now()}
        )

    def list_open(self, user_id: int) -> list[Receivable]:
        live = (ReceivableStatus.OPEN, ReceivableStatus.REQUESTED)
        return [r for r in self.table.list(user_id) if r.status in live]

    def open_for_transaction(self, user_id: int, tx_id: int) -> Receivable | None:
        found = [r for r in self.list_open(user_id) if r.transaction_id == tx_id]
        return found[-1] if found else None


class FakeLifeFacts:
    def __init__(self) -> None:
        self.table = ModelTable("life fact", LifeFact)

    def create(self, user_id: int, draft: LifeFactDraft) -> LifeFact:
        return self.table.insert(user_id, {**draft.model_dump(), "created_at": clock.now()})

    def get(self, user_id: int, fact_id: int) -> LifeFact:
        return self.table.get(user_id, fact_id)

    def update(self, user_id: int, fact_id: int, draft: LifeFactDraft) -> LifeFact:
        return self.table.update(user_id, fact_id, draft.model_dump())

    def expire(self, user_id: int, fact_id: int, valid_to: date) -> LifeFact:
        return self.table.update(
            user_id, fact_id, {"status": FactStatus.EXPIRED, "valid_to": valid_to}
        )

    def confirm(self, user_id: int, fact_id: int) -> LifeFact:
        return self.table.update(user_id, fact_id, {"status": FactStatus.CONFIRMED})

    def reject(self, user_id: int, fact_id: int) -> LifeFact:
        return self.table.update(user_id, fact_id, {"status": FactStatus.REJECTED})

    def list_active(self, user_id: int) -> list[LifeFact]:
        today = clock.today()
        return [
            f
            for f in self.table.list(user_id)
            if f.status is FactStatus.CONFIRMED and f.active_on(today)
        ]


class FakeSignatures:
    def __init__(self) -> None:
        self.by_fact: dict[tuple[int, int], list[Signature]] = {}

    def replace_for_fact(self, user_id: int, fact_id: int, signatures: Sequence[Signature]) -> None:
        self.by_fact[(user_id, fact_id)] = list(signatures)


class FakePatternRules:
    def __init__(self) -> None:
        self.table = ModelTable("pattern rule", PatternRule)

    def create(self, user_id: int, rule: PatternRule) -> PatternRule:
        return self.table.insert(user_id, rule.model_dump(exclude={"id"}))


class FakePots:
    def __init__(self) -> None:
        self.table = ModelTable("pot", Pot)

    def create(self, user_id: int, data: Mapping[str, Any]) -> Pot:
        return self.table.insert(user_id, data)

    def get(self, user_id: int, pot_id: int) -> Pot:
        return self.table.get(user_id, pot_id)

    def update(self, user_id: int, pot_id: int, changes: Mapping[str, Any]) -> Pot:
        return self.table.update(user_id, pot_id, changes)

    def close(self, user_id: int, pot_id: int) -> Pot:
        return self.table.update(user_id, pot_id, {"status": PotStatus.CLOSED})


class FakeGoals:
    def __init__(self) -> None:
        self.table = ModelTable("goal", Goal)

    def active(self, user_id: int) -> Goal | None:
        found = [g for g in self.table.list(user_id) if g.status is GoalStatus.ACTIVE]
        return found[0] if found else None

    def create(self, user_id: int, data: Mapping[str, Any]) -> Goal:
        return self.table.insert(user_id, {**data, "created_at": clock.now()})

    def update(self, user_id: int, goal_id: int, changes: Mapping[str, Any]) -> Goal:
        return self.table.update(user_id, goal_id, changes)


class FakePlanPreferences:
    def __init__(self) -> None:
        self.rows: dict[int, PlanPreferences] = {}

    def get(self, user_id: int) -> PlanPreferences:
        return self.rows.get(user_id, PlanPreferences())

    def save(self, user_id: int, preferences: PlanPreferences) -> PlanPreferences:
        self.rows[user_id] = preferences
        return preferences


class FakeLifeProfile:
    def __init__(self) -> None:
        self.notes: dict[int, dict[str, str]] = {}

    def set_note(self, user_id: int, key: str, value: str) -> Row:
        self.notes.setdefault(user_id, {})[key] = value
        return dict(self.notes[user_id])


class FakeAgentEvents(FakeRecords):
    def __init__(self) -> None:
        super().__init__("agent event")

    def open_question_for(self, user_id: int, tx_id: int) -> Row | None:
        found = [
            r
            for r in self.list(user_id)
            if r.get("ref_transaction_id") == tx_id and r.get("status") == "asked"
        ]
        return found[-1] if found else None

    def mark_answered(self, user_id: int, event_id: int) -> Row:
        return self.update(user_id, event_id, {"status": "answered"})

    def mark_handled(self, user_id: int, event_id: int) -> Row:
        return self.update(user_id, event_id, {"status": "handled"})


class FakeTransfers(FakeRecords):
    def __init__(self) -> None:
        super().__init__("transfer")

    def to_savings(self, user_id: int, amount: Decimal) -> Row:
        return self.create(user_id, {"amount": amount, "kind": "manual"})


class FakeUsers:
    def __init__(self) -> None:
        self.onboarded: set[int] = set()

    def mark_onboarded(self, user_id: int) -> Row:
        self.onboarded.add(user_id)
        return {"id": user_id, "onboarded": True}


class FakeLatest:
    def __init__(self) -> None:
        self.rows: dict[int, Row] = {}

    def latest(self, user_id: int) -> Row | None:
        return self.rows.get(user_id)


class FakeProducts:
    def __init__(self, products: list[Row] | None = None) -> None:
        self.products = products or []

    def list(self) -> list[Row]:
        return [dict(p) for p in self.products]


class FakeToolCalls:
    def __init__(self) -> None:
        self.rows: list[Row] = []

    def log(
        self,
        user_id: int,
        run_id: int | None,
        tool_use_id: str,
        tool_name: str,
        tool_input: Mapping[str, Any],
        output: str,
        status: str,
    ) -> None:
        self.rows.append(
            {
                "user_id": user_id,
                "run_id": run_id,
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
                "input": dict(tool_input),
                "output": output,
                "status": status,
            }
        )


def fake_services() -> Services:
    return Services(
        transactions=FakeTransactions(),
        receivables=FakeReceivables(),
        life_facts=FakeLifeFacts(),
        signatures=FakeSignatures(),
        pattern_rules=FakePatternRules(),
        pots=FakePots(),
        goals=FakeGoals(),
        income_sources=FakeRecords("income source"),
        fixed_costs=FakeRecords("fixed cost"),
        life_events=FakeRecords("life event"),
        slips=FakeRecords("slip"),
        reflections=FakeRecords("reflection"),
        plan_preferences=FakePlanPreferences(),
        life_profile=FakeLifeProfile(),
        agent_events=FakeAgentEvents(),
        transfers=FakeTransfers(),
        users=FakeUsers(),
        plans=FakeLatest(),
        forecasts=FakeLatest(),
        products=FakeProducts(),
        tool_calls=FakeToolCalls(),
    )


@dataclass
class FakeEngine:
    """Records every call. The plan version goes up by one per recompute; the previous values
    are the last ones returned, like the real engine's `summary(compare_to_previous=True)`."""

    estimate: Decimal = Decimal("100.00")
    calls: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)
    version: int = 7
    today_budget: Decimal = Decimal("31.20")
    probability: float = 0.71

    def recompute_plan(
        self, db: Any, user_id: int, reason: str, trigger_ref: dict[str, Any] | None = None
    ) -> PlanSummary:
        self.calls.append(("recompute_plan", (user_id, reason, trigger_ref)))
        previous, self.version = self.today_budget, self.version + 1
        self.today_budget = previous - Decimal("1.40")
        return PlanSummary(
            version=self.version,
            feasible=True,
            today_budget=self.today_budget,
            previous_today_budget=previous,
            reason=reason[:300],
        )

    def forecast_goal(self, db: Any, user_id: int, plan_version: int) -> Forecast:
        self.calls.append(("forecast_goal", (user_id, plan_version)))
        previous, self.probability = self.probability, round(self.probability + 0.06, 2)
        return Forecast(
            probability=self.probability,
            previous_probability=previous,
            last_week_probability=0.72,
            p10=Decimal("8000"),
            p50=Decimal("10400"),
            p90=Decimal("12100"),
        )

    def own_share_estimate(self, db: Any, user_id: int, tx: TxView) -> Decimal:
        self.calls.append(("own_share_estimate", (user_id, tx.id)))
        return self.estimate

    def on_annotation_changed(
        self, db: Any, user_id: int, tx_id: int, old: Decimal, new: Decimal
    ) -> None:
        self.calls.append(("on_annotation_changed", (user_id, tx_id, old, new)))

    def simulate_plan(self, db: Any, user_id: int, changes: dict[str, Any]) -> SimResult:
        self.calls.append(("simulate_plan", (user_id, changes)))
        return SimResult(
            feasible=True,
            today_budget=Decimal("38.10"),
            avg_daily_budget=Decimal("36.40"),
            probability=0.79,
            diff_vs_current=SimDiff(today_budget=Decimal("6.90"), probability=0.08),
        )

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]


@dataclass
class FakeContext:
    signatures: list[Signature] = field(default_factory=list)
    calls: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)

    def signatures_for_fact(
        self, fact: LifeFact, llm_signatures: list[dict[str, Any]] | None
    ) -> list[Signature]:
        self.calls.append(("signatures_for_fact", (fact.id, llm_signatures)))
        return list(self.signatures)

    def on_fact_changed(self, db: Any, user_id: int, fact_id: int) -> None:
        self.calls.append(("on_fact_changed", (user_id, fact_id)))

    def learn_from_annotation(self, db: Any, user_id: int, tx_id: int) -> None:
        self.calls.append(("learn_from_annotation", (user_id, tx_id)))

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]


@dataclass
class Harness:
    """A ready `ToolContext` + `RunState` for user 1, with the fakes reachable for asserts."""

    user_id: int = 1
    trigger: str = "chat"
    language: Language = Language.RO
    services: Services = field(default_factory=fake_services)
    engine: FakeEngine = field(default_factory=FakeEngine)
    context: FakeContext = field(default_factory=FakeContext)
    run: RunState = field(init=False)
    ctx: ToolContext = field(init=False)

    def __post_init__(self) -> None:
        self.run = RunState(trigger=self.trigger, run_id=55)
        self.ctx = ToolContext(
            user_id=self.user_id,
            services=self.services,
            engine=self.engine,
            context=self.context,
            language=self.language,
        )

    def add_tx(
        self, tx_id: int, amount: str, *, user_id: int | None = None, **extra: Any
    ) -> TxView:
        tx = TxView.model_validate(
            {
                "id": tx_id,
                "occurred_at": datetime(2026, 10, 28, 13, 5, tzinfo=UTC),
                "merchant_raw": "MEGA IMAGE 0451 BUCURESTI",
                "merchant": "Mega Image",
                "category": "groceries",
                "direction": Direction.DEBIT,
                "amount": amount,
                "effective_amount": amount,
                **extra,
            }
        )
        txs = self.services.transactions
        assert isinstance(txs, FakeTransactions)
        return txs.add(self.user_id if user_id is None else user_id, tx)
