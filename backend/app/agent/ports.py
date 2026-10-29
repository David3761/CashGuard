"""What the tool handlers need from the DB services and the engine (A3; D42).

bomboe's B3 services don't exist yet, so the handlers depend on these small Protocols instead.
bomboe implements them with Postgres (`app/services/*`); the tests use the in-memory
`tests/fakes/fake_services.py`. The rules every implementation keeps:

- Every method takes the backend's `user_id` first. A row of another user is **invisible**: the
  method raises `DomainError("not_found", …, 404)` exactly as for a missing id, so ids can't be
  probed.
- The handlers compute every amount (effective amounts, splits, receivables); a service only
  stores what it is given.
- The rows the handlers reason about are the F2 models (`TxView`, `Receivable`, `LifeFact`,
  `PatternRule`, `Pot`, `Goal`, `PlanPreferences`); the plain records (income sources, fixed
  costs, life events, slips, reflections, …) are `Row` dicts with the arch 4.x column names.

Every port method is `async` (bomboe's services run on SQLAlchemy's `AsyncSession`, danutu's
engine is async too), so the handlers and the executor `await` them.

The engine (danutu, arch 15.1) and the context layer (C4, C8, C9) are behind ports too, with lazy
adapters that call the real functions: their modules are landing in parallel, so nothing here
imports them at import time.
"""

import importlib
import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from app.domain.enums import AnnotationSource, Beneficiary, Purpose
from app.domain.models import (
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
from app.domain.results import Forecast, PlanSummary, PropagationResult, SimResult

Row = dict[str, Any]
"""A plain record as a dict (arch 4.x column names)."""


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
    expected_by: date
    transaction_id: int | None = None
    people_count: int | None = None
    amount_each: Decimal | None = None


# ── bomboe's services (arch 15.1 `services/`) ─────────────────────────────────────────────────


class TransactionsPort(Protocol):
    async def get(self, user_id: int, tx_id: int) -> TxView: ...
    async def list(
        self, user_id: int, since: date, until: date, category: str | None = None
    ) -> list[TxView]: ...
    async def annotate(self, user_id: int, tx_id: int, annotation: Annotation) -> TxView: ...
    async def set_pot(self, user_id: int, tx_id: int, pot_id: int) -> TxView: ...


class ReceivablesPort(Protocol):
    async def create(self, user_id: int, draft: ReceivableDraft) -> Receivable: ...
    async def get(self, user_id: int, receivable_id: int) -> Receivable: ...
    async def cancel(self, user_id: int, receivable_id: int) -> Receivable: ...
    async def mark_paid(self, user_id: int, receivable_id: int) -> Receivable: ...
    async def list_open(self, user_id: int) -> list[Receivable]: ...  # open + requested
    async def open_for_transaction(self, user_id: int, tx_id: int) -> Receivable | None: ...


class LifeFactsPort(Protocol):
    async def create(self, user_id: int, draft: LifeFactDraft) -> LifeFact: ...
    async def get(self, user_id: int, fact_id: int) -> LifeFact: ...
    async def update(self, user_id: int, fact_id: int, draft: LifeFactDraft) -> LifeFact: ...
    async def expire(self, user_id: int, fact_id: int, valid_to: date) -> LifeFact: ...
    async def confirm(self, user_id: int, fact_id: int) -> LifeFact: ...
    async def reject(self, user_id: int, fact_id: int) -> LifeFact: ...
    async def list_active(self, user_id: int) -> list[LifeFact]: ...  # confirmed, valid today


class SignaturesPort(Protocol):
    async def replace_for_fact(
        self, user_id: int, fact_id: int, signatures: Sequence[Signature]
    ) -> None: ...


class PatternRulesPort(Protocol):
    async def create(self, user_id: int, rule: PatternRule) -> PatternRule: ...


class PotsPort(Protocol):
    async def create(self, user_id: int, data: Mapping[str, Any]) -> Pot: ...
    async def get(self, user_id: int, pot_id: int) -> Pot: ...
    async def update(self, user_id: int, pot_id: int, changes: Mapping[str, Any]) -> Pot: ...
    async def close(self, user_id: int, pot_id: int) -> Pot: ...


class RecordsPort(Protocol):
    """Plain per-user CRUD: income sources, fixed costs, life events, slips, reflections."""

    async def create(self, user_id: int, data: Mapping[str, Any]) -> Row: ...
    async def get(self, user_id: int, record_id: int) -> Row: ...
    async def update(self, user_id: int, record_id: int, changes: Mapping[str, Any]) -> Row: ...
    async def list(self, user_id: int) -> list[Row]: ...
    async def remove(self, user_id: int, record_id: int) -> None: ...


class GoalsPort(Protocol):
    async def active(self, user_id: int) -> Goal | None: ...
    async def create(self, user_id: int, data: Mapping[str, Any]) -> Goal: ...
    async def update(self, user_id: int, goal_id: int, changes: Mapping[str, Any]) -> Goal: ...


class PlanPreferencesPort(Protocol):
    async def get(self, user_id: int) -> PlanPreferences: ...
    async def save(self, user_id: int, preferences: PlanPreferences) -> PlanPreferences: ...


class LifeProfilePort(Protocol):
    async def set_note(self, user_id: int, key: str, value: str) -> Row: ...


class AgentEventsPort(Protocol):
    async def get(self, user_id: int, event_id: int) -> Row: ...
    async def open_question_for(self, user_id: int, tx_id: int) -> Row | None: ...
    async def mark_answered(self, user_id: int, event_id: int) -> Row: ...
    async def mark_handled(self, user_id: int, event_id: int) -> Row: ...


class TransfersPort(Protocol):
    async def to_savings(self, user_id: int, amount: Decimal) -> Row: ...


class UsersPort(Protocol):
    async def mark_onboarded(self, user_id: int) -> Row: ...


class PlansPort(Protocol):
    async def latest(self, user_id: int) -> Row | None: ...


class ForecastsPort(Protocol):
    async def latest(self, user_id: int) -> Row | None: ...


class ProductsPort(Protocol):
    async def list(self) -> list[Row]: ...


class ToolCallsPort(Protocol):
    async def log(
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
    pots: PotsPort
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
    async def recompute_plan(
        self, db: Any, user_id: int, reason: str, trigger_ref: dict[str, Any] | None = None
    ) -> PlanSummary | None: ...  # None: no goal yet, so no plan (danutu's E4)
    async def forecast_goal(self, db: Any, user_id: int, plan_version: int) -> Forecast: ...
    async def own_share_estimate(self, db: Any, user_id: int, tx: TxView) -> Decimal: ...
    async def on_annotation_changed(
        self,
        db: Any,
        user_id: int,
        tx_id: int,
        old: Decimal,
        new: Decimal,
        *,
        before: TxView | None = None,
        after: TxView | None = None,
    ) -> None: ...
    async def simulate_plan(self, db: Any, user_id: int, changes: dict[str, Any]) -> SimResult: ...


class LazyEngine:
    """`EnginePort` over `app.engine.service` (danutu's S0 stubs, then the real engine)."""

    def _fn(self, name: str) -> Any:
        return getattr(importlib.import_module("app.engine.service"), name)

    async def recompute_plan(
        self, db: Any, user_id: int, reason: str, trigger_ref: dict[str, Any] | None = None
    ) -> PlanSummary | None:
        plan: PlanSummary | None = await self._fn("recompute_plan")(
            db, user_id, reason, trigger_ref
        )
        return plan

    async def forecast_goal(self, db: Any, user_id: int, plan_version: int) -> Forecast:
        forecast: Forecast = await self._fn("forecast_goal")(db, user_id, plan_version)
        return forecast

    async def own_share_estimate(self, db: Any, user_id: int, tx: TxView) -> Decimal:
        value: Decimal = await self._fn("own_share_estimate")(db, user_id, tx)
        return value

    async def on_annotation_changed(
        self,
        db: Any,
        user_id: int,
        tx_id: int,
        old: Decimal,
        new: Decimal,
        *,
        before: TxView | None = None,
        after: TxView | None = None,
    ) -> None:
        """danutu's E3 takes the transaction as it was and as it is now, not two amounts
        (`ledger.reannotate_delta` also reads the purpose and the pot). The port keeps the two
        effective amounts; the caller passes the views when it has them (`apply_annotation`
        does). A missing `after` comes from bomboe's `transactions.get`, and a missing `before`
        is `after` with the old amount."""
        if after is None:
            transactions = importlib.import_module("app.services.transactions")
            after = await transactions.get(db, user_id, tx_id)
        after = after.replace(effective_amount=new)
        before = (before or after).replace(effective_amount=old)
        await self._fn("on_annotation_changed")(db, user_id, tx_id, before, after)

    async def simulate_plan(self, db: Any, user_id: int, changes: dict[str, Any]) -> SimResult:
        result: SimResult = await self._fn("simulate_plan")(db, user_id, changes)
        return result


# ── the context layer (C4 signatures, C8 learning, C9 propagation) ────────────────────────────


class ContextPort(Protocol):
    async def signatures_for_fact(
        self, fact: LifeFact, llm_signatures: list[dict[str, Any]] | None
    ) -> list[Signature]: ...
    async def on_fact_changed(
        self, db: Any, user_id: int, fact_id: int
    ) -> PropagationResult | None: ...
    async def learn_from_annotation(self, db: Any, user_id: int, tx_id: int) -> Any: ...


def _first(*candidates: tuple[str, str]) -> Any:
    """The first `module.name` that exists: the real C4/C8/C9 module, else S0's stub."""
    for module, name in candidates:
        try:
            fn = getattr(importlib.import_module(module), name, None)
        except ModuleNotFoundError:
            continue
        if fn is not None:
            return fn
    raise RuntimeError(f"none of {candidates} exists")


async def _settle(value: Any) -> Any:
    """`value`, awaited when it is awaitable: the §15 shells that load data are async, the pure
    cores (C4's library) sync, and a module landing in parallel may still be either."""
    return await value if inspect.isawaitable(value) else value


class LazyContext:
    """`ContextPort` over `app.context.*`: C4's library, C9's propagation and C8's rules once they
    land, S0's `app.context.service` stubs until then."""

    async def signatures_for_fact(
        self, fact: LifeFact, llm_signatures: list[dict[str, Any]] | None
    ) -> list[Signature]:
        fn = _first(
            ("app.context.library", "signatures_for_fact"),
            ("app.context.service", "signatures_for_fact"),
        )
        return list(await _settle(fn(fact, llm_signatures)))

    async def on_fact_changed(
        self, db: Any, user_id: int, fact_id: int
    ) -> PropagationResult | None:
        # C9's tool-path shell: no plan recompute inside, the executor does it once (D18).
        fn = _first(
            ("app.context.propagate", "reevaluate_after_fact"),
            ("app.context.service", "on_fact_changed"),
        )
        result: PropagationResult | None = await _settle(fn(db, user_id, fact_id))
        return result

    async def learn_from_annotation(self, db: Any, user_id: int, tx_id: int) -> Any:
        fn = _first(
            ("app.context.rules", "learn_from_annotation"),
            ("app.context.service", "learn_from_annotation"),
        )
        return await _settle(fn(db, user_id, tx_id))


# ── where the services come from outside a tool call (bomboe's PATCH /transactions) ──────────

_services_factory: list[Any] = []


def set_services_factory(factory: Any) -> None:
    """bomboe registers `factory(db) -> Services` (his Postgres ports) once at startup."""
    _services_factory[:] = [factory]


def services_for(db: Any) -> Services:
    if not _services_factory:
        raise RuntimeError("no services factory: B3 must call set_services_factory at startup")
    services: Services = _services_factory[0](db)
    return services
