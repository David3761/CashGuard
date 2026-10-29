"""What the tool handlers need from the DB services and the engine (A3; D42).

bomboe's B3 services don't exist yet, so the handlers depend on these small Protocols instead.
bomboe implements them with Postgres (`app/services/*`); the tests use the in-memory
`tests/fakes/fake_services.py`. The rules every implementation keeps:

- Every method takes the backend's `user_id` first. A row of another user is **invisible**: the
  method raises `DomainError("not_found", …, 404)` exactly as for a missing id, so ids can't be
  probed.
- The handlers compute every amount (effective amounts, splits, receivables); a service only
  stores what it is given.
- Rows the F2 models don't cover yet are plain `Row` dicts with the arch 4.x column names. They
  become the F2 models (`Receivable`, `Pot`, `Goal`, …) once F2 step 6 lands.

The engine (danutu, arch 15.1) and the context layer (C4, C8, C9) are behind ports too, with lazy
adapters that call the real functions: their modules are landing in parallel, so nothing here
imports them at import time.
"""

import importlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from app.domain.enums import AnnotationSource, Beneficiary, Purpose
from app.domain.models import TxView

Row = dict[str, Any]
"""A DB row as a dict (arch 4.x column names); replaced by the F2 models as they land."""


@dataclass(frozen=True, slots=True)
class Annotation:
    """What `apply_annotation` writes on a transaction (arch 4.4 annotation columns)."""

    purpose: Purpose
    beneficiary: Beneficiary
    effective_amount: Decimal
    source: AnnotationSource
    estimated: bool = False
    confidence: float = 1.0
    receivable_id: int | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ReceivableDraft:
    """A new receivable (arch 4.4 `receivables`); the code computed every amount."""

    debtor_label: str
    amount: Decimal
    transaction_id: int | None = None
    people_count: int | None = None
    amount_each: Decimal | None = None
    expected_by: date | None = None


# ── bomboe's services (arch 15.1 `services/`) ─────────────────────────────────────────────────


class TransactionsPort(Protocol):
    def get(self, user_id: int, tx_id: int) -> TxView: ...
    def list(
        self, user_id: int, since: date, until: date, category: str | None = None
    ) -> list[TxView]: ...
    def annotate(self, user_id: int, tx_id: int, annotation: Annotation) -> TxView: ...
    def set_pot(self, user_id: int, tx_id: int, pot_id: int) -> TxView: ...


class ReceivablesPort(Protocol):
    def create(self, user_id: int, draft: ReceivableDraft) -> Row: ...
    def get(self, user_id: int, receivable_id: int) -> Row: ...
    def cancel(self, user_id: int, receivable_id: int) -> Row: ...
    def mark_paid(self, user_id: int, receivable_id: int) -> Row: ...
    def list_open(self, user_id: int) -> list[Row]: ...
    def open_for_transaction(self, user_id: int, tx_id: int) -> Row | None: ...


class LifeFactsPort(Protocol):
    def create(self, user_id: int, data: Mapping[str, Any]) -> Row: ...
    def get(self, user_id: int, fact_id: int) -> Row: ...
    def update(self, user_id: int, fact_id: int, changes: Mapping[str, Any]) -> Row: ...
    def expire(self, user_id: int, fact_id: int, valid_to: date) -> Row: ...
    def confirm(self, user_id: int, fact_id: int) -> Row: ...
    def reject(self, user_id: int, fact_id: int) -> Row: ...
    def list_active(self, user_id: int) -> list[Row]: ...


class SignaturesPort(Protocol):
    def replace_for_fact(self, user_id: int, fact_id: int, signatures: Sequence[Any]) -> None: ...


class PatternRulesPort(Protocol):
    def create(self, user_id: int, data: Mapping[str, Any]) -> Row: ...


class RecordsPort(Protocol):
    """Plain per-user CRUD: pots, goals, income sources, fixed costs, life events, slips, …"""

    def create(self, user_id: int, data: Mapping[str, Any]) -> Row: ...
    def get(self, user_id: int, record_id: int) -> Row: ...
    def update(self, user_id: int, record_id: int, changes: Mapping[str, Any]) -> Row: ...
    def list(self, user_id: int) -> list[Row]: ...


class GoalsPort(Protocol):
    def active(self, user_id: int) -> Row | None: ...
    def create(self, user_id: int, data: Mapping[str, Any]) -> Row: ...
    def update(self, user_id: int, goal_id: int, changes: Mapping[str, Any]) -> Row: ...


class PlanPreferencesPort(Protocol):
    def get(self, user_id: int) -> Row: ...
    def update(self, user_id: int, changes: Mapping[str, Any]) -> Row: ...


class LifeProfilePort(Protocol):
    def set_note(self, user_id: int, key: str, value: str) -> Row: ...


class AgentEventsPort(Protocol):
    def get(self, user_id: int, event_id: int) -> Row: ...
    def open_question_for(self, user_id: int, tx_id: int) -> Row | None: ...
    def mark_answered(self, user_id: int, event_id: int) -> Row: ...
    def mark_handled(self, user_id: int, event_id: int) -> Row: ...


class TransfersPort(Protocol):
    def to_savings(self, user_id: int, amount: Decimal) -> Row: ...


class UsersPort(Protocol):
    def mark_onboarded(self, user_id: int) -> Row: ...


class PlansPort(Protocol):
    def latest(self, user_id: int) -> Row | None: ...


class ForecastsPort(Protocol):
    def latest(self, user_id: int) -> Row | None: ...


class ProductsPort(Protocol):
    def list(self) -> list[Row]: ...


class ToolCallsPort(Protocol):
    def log(
        self,
        user_id: int,
        run_id: int | None,
        tool_use_id: str,
        tool_name: str,
        tool_input: Mapping[str, Any],
        output: str,
        status: str,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class Services:
    """Every service port the handlers use, bundled per unit of work (one DB session)."""

    transactions: TransactionsPort
    receivables: ReceivablesPort
    life_facts: LifeFactsPort
    signatures: SignaturesPort
    pattern_rules: PatternRulesPort
    pots: RecordsPort
    goals: GoalsPort
    income_sources: RecordsPort
    fixed_costs: RecordsPort
    life_events: RecordsPort
    slips: RecordsPort
    reflections: RecordsPort
    plan_preferences: PlanPreferencesPort
    life_profile: LifeProfilePort
    agent_events: AgentEventsPort
    transfers: TransfersPort
    users: UsersPort
    plans: PlansPort
    forecasts: ForecastsPort
    products: ProductsPort
    tool_calls: ToolCallsPort


# ── danutu's engine (arch 15.1 `engine/`) ─────────────────────────────────────────────────────


class EnginePort(Protocol):
    def recompute_plan(
        self, db: Any, user_id: int, reason: str, trigger_ref: dict[str, Any] | None = None
    ) -> Any: ...
    def forecast_goal(self, db: Any, user_id: int, plan_version: int) -> Any: ...
    def own_share_estimate(self, db: Any, user_id: int, tx: TxView) -> Decimal: ...
    def on_annotation_changed(
        self, db: Any, user_id: int, tx_id: int, old: Decimal, new: Decimal
    ) -> None: ...
    def simulate_plan(self, db: Any, user_id: int, changes: dict[str, Any]) -> Any: ...


class LazyEngine:
    """`EnginePort` over `app.engine.service` (danutu's S0 stubs, then the real engine)."""

    def _fn(self, name: str) -> Any:
        return getattr(importlib.import_module("app.engine.service"), name)

    def recompute_plan(
        self, db: Any, user_id: int, reason: str, trigger_ref: dict[str, Any] | None = None
    ) -> Any:
        return self._fn("recompute_plan")(db, user_id, reason, trigger_ref)

    def forecast_goal(self, db: Any, user_id: int, plan_version: int) -> Any:
        return self._fn("forecast_goal")(db, user_id, plan_version)

    def own_share_estimate(self, db: Any, user_id: int, tx: TxView) -> Decimal:
        value: Decimal = self._fn("own_share_estimate")(db, user_id, tx)
        return value

    def on_annotation_changed(
        self, db: Any, user_id: int, tx_id: int, old: Decimal, new: Decimal
    ) -> None:
        self._fn("on_annotation_changed")(db, user_id, tx_id, old, new)

    def simulate_plan(self, db: Any, user_id: int, changes: dict[str, Any]) -> Any:
        return self._fn("simulate_plan")(db, user_id, changes)


# ── the context layer (C4 signatures, C8 learning, C9 propagation) ────────────────────────────


class ContextPort(Protocol):
    def signatures_for_fact(
        self, fact: Row, llm_signatures: list[dict[str, Any]] | None
    ) -> list[Any]: ...
    def on_fact_changed(self, db: Any, user_id: int, fact_id: int) -> Any: ...
    def learn_from_annotation(self, db: Any, user_id: int, tx_id: int) -> Any: ...


def _optional(module: str, name: str) -> Any | None:
    """`module.name`, or None while that module hasn't landed yet (C4/C8/C9 are in progress)."""
    try:
        return getattr(importlib.import_module(module), name, None)
    except ModuleNotFoundError:
        return None


class LazyContext:
    """`ContextPort` over `app.context.*`; a no-op for each function not written yet."""

    def signatures_for_fact(
        self, fact: Row, llm_signatures: list[dict[str, Any]] | None
    ) -> list[Any]:
        fn = _optional("app.context.library", "signatures_for_fact")
        return [] if fn is None else list(fn(fact, llm_signatures))

    def on_fact_changed(self, db: Any, user_id: int, fact_id: int) -> Any:
        fn = _optional("app.context.propagate", "on_fact_changed") or _optional(
            "app.context.service", "on_fact_changed"
        )
        return None if fn is None else fn(db, user_id, fact_id)

    def learn_from_annotation(self, db: Any, user_id: int, tx_id: int) -> Any:
        fn = _optional("app.context.rules", "learn_from_annotation") or _optional(
            "app.context.service", "learn_from_annotation"
        )
        return None if fn is None else fn(db, user_id, tx_id)
