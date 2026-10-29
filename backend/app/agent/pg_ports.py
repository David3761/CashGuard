"""The tool handlers' `Services` (A3 ports, `app/agent/ports.py`) over bomboe's Postgres services.

`pg_services(db)` bundles one adapter per port, all on the same `AsyncSession`: the unit of work
of one tool call (`platform.PlatformServices.execute_tool` opens it, commits on success and rolls
back on an error result). Every method maps to `app/services/*`; where bomboe has no function
(slips, reflections, some lookups) the adapter works on the ORM rows, always scoped by `user_id`:
another user's row is `not_found`, exactly like a missing id.

The tool-call log is the one exception: `tool_calls.log` writes in its own short unit of work,
so an error result (whose tool transaction is rolled back) is still recorded, and a failing log
never poisons the tool's session.
"""

import json
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.agent.ports import Annotation, ReceivableDraft, Row, Services
from app.db import models as m
from app.db.models import Base
from app.db.session import unit_of_work
from app.domain import models as dm
from app.domain.enums import (
    AgentEventStatus,
    LifeEventStatus,
    PotKind,
    ReceivableStatus,
    ToolCallStatus,
    TransferKind,
)
from app.domain.results import Forecast, PlanSummary
from app.services import (
    accounts,
    agent_events,
    agent_runs,
    fixed_costs,
    forecasts,
    goals,
    income_sources,
    life_events,
    life_facts,
    life_profile,
    pattern_rules,
    plan_preferences,
    plans,
    pots,
    products,
    receivables,
    signatures,
    tool_calls,
    transactions,
    transfers,
    users,
)
from app.services._common import invalid, owned

_TOOL_STATUS = {"ok": ToolCallStatus.OK, "error": ToolCallStatus.ERROR}


def _dict(row: Base) -> Row:
    """An ORM row as a plain record (every column but `user_id`)."""
    return {c.key: getattr(row, c.key) for c in row.__table__.columns if c.key != "user_id"}


def _plain(data: Mapping[str, Any]) -> dict[str, Any]:
    """`data` as JSON-safe values (dates, Decimals → strings) for a JSONB column."""
    plain: dict[str, Any] = json.loads(json.dumps(dict(data), default=str))
    return plain


def _only(data: Mapping[str, Any], *names: str) -> dict[str, Any]:
    return {k: data[k] for k in names if k in data}


class _Base:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db


class PgTransactions(_Base):
    async def get(self, user_id: int, tx_id: int) -> dm.TxView:
        return await transactions.get(self.db, user_id, tx_id)

    async def annotate(self, user_id: int, tx_id: int, annotation: Annotation) -> dm.TxView:
        await transactions.annotate(
            self.db,
            user_id,
            tx_id,
            purpose=annotation.purpose,
            beneficiary=annotation.beneficiary,
            effective_amount=annotation.effective_amount,
            source=annotation.source,
            confidence=annotation.confidence,
        )
        return await transactions.set_receivable(self.db, user_id, tx_id, annotation.receivable_id)

    async def set_pot(self, user_id: int, tx_id: int, pot_id: int) -> dm.TxView:
        await pots.get(self.db, user_id, pot_id)  # the pot is the user's
        return await transactions.set_pot(self.db, user_id, tx_id, pot_id)

    async def list(
        self, user_id: int, since: date, until: date, category: str | None = None
    ) -> list[dm.TxView]:
        found = await transactions.list_all(self.db, user_id, since=since, until=until)
        return [tx for tx in found if category is None or tx.category == category]


class PgReceivables(_Base):
    async def create(self, user_id: int, draft: ReceivableDraft) -> dm.Receivable:
        return await receivables.create(
            self.db,
            user_id,
            amount=draft.amount,
            debtor_label=draft.debtor_label,
            expected_by=draft.expected_by,
            transaction_id=draft.transaction_id,
            people_count=draft.people_count,
            amount_each=draft.amount_each,
        )

    async def get(self, user_id: int, receivable_id: int) -> dm.Receivable:
        return await receivables.get(self.db, user_id, receivable_id)

    async def cancel(self, user_id: int, receivable_id: int) -> dm.Receivable:
        return await receivables.cancel(self.db, user_id, receivable_id)

    async def mark_paid(self, user_id: int, receivable_id: int) -> dm.Receivable:
        return await receivables.update_status(
            self.db, user_id, receivable_id, ReceivableStatus.PAID
        )

    async def list_open(self, user_id: int) -> list[dm.Receivable]:
        return list(await receivables.list_open(self.db, user_id))

    async def open_for_transaction(self, user_id: int, tx_id: int) -> dm.Receivable | None:
        found = [r for r in await self.list_open(user_id) if r.transaction_id == tx_id]
        return max(found, key=lambda r: r.id) if found else None


class PgLifeFacts(_Base):
    async def create(self, user_id: int, draft: dm.LifeFactDraft) -> dm.LifeFact:
        return await life_facts.create(self.db, user_id, draft)

    async def get(self, user_id: int, fact_id: int) -> dm.LifeFact:
        return await life_facts.get(self.db, user_id, fact_id)

    async def update(self, user_id: int, fact_id: int, draft: dm.LifeFactDraft) -> dm.LifeFact:
        return await life_facts.replace(self.db, user_id, fact_id, draft)

    async def expire(self, user_id: int, fact_id: int, valid_to: date) -> dm.LifeFact:
        return await life_facts.expire(self.db, user_id, fact_id, valid_to)

    async def confirm(self, user_id: int, fact_id: int) -> dm.LifeFact:
        return await life_facts.confirm(self.db, user_id, fact_id)

    async def reject(self, user_id: int, fact_id: int) -> dm.LifeFact:
        return await life_facts.reject(self.db, user_id, fact_id)

    async def list_active(self, user_id: int) -> list[dm.LifeFact]:
        return list(await life_facts.list_active(self.db, user_id, clock.today()))


class PgSignatures(_Base):
    async def replace_for_fact(
        self, user_id: int, fact_id: int, sigs: Sequence[dm.Signature]
    ) -> None:
        await owned(self.db, m.LifeFact, user_id, fact_id, "Life fact")
        await signatures.replace_for_fact(self.db, user_id, fact_id, sigs)


class PgPatternRules(_Base):
    async def create(self, user_id: int, rule: dm.PatternRule) -> dm.PatternRule:
        return await pattern_rules.create(self.db, user_id, rule)


class PgPots(_Base):
    async def create(self, user_id: int, data: Mapping[str, Any]) -> dm.Pot:
        fields = _only(
            data, "deadline", "goal_id", "life_event_id", "fact_id", "monthly_contribution"
        )
        return await pots.create(
            self.db,
            user_id,
            name=data["name"],
            kind=PotKind(data["kind"]),
            target=Decimal(data["target"]),
            **fields,
        )

    async def get(self, user_id: int, pot_id: int) -> dm.Pot:
        return await pots.get(self.db, user_id, pot_id)

    async def update(self, user_id: int, pot_id: int, changes: Mapping[str, Any]) -> dm.Pot:
        fields = _only(changes, "name", "target", "deadline", "monthly_contribution")
        return await pots.update(self.db, user_id, pot_id, **fields)

    async def close(self, user_id: int, pot_id: int) -> dm.Pot:
        return await pots.close(self.db, user_id, pot_id)


class PgGoals(_Base):
    async def active(self, user_id: int) -> dm.Goal | None:
        return await goals.get_active(self.db, user_id)

    async def create(self, user_id: int, data: Mapping[str, Any]) -> dm.Goal:
        return await goals.create(
            self.db,
            user_id,
            amount=Decimal(data["amount"]),
            deadline=data["deadline"],
            **_only(data, "motivation", "soft"),
        )

    async def update(self, user_id: int, goal_id: int, changes: Mapping[str, Any]) -> dm.Goal:
        fields = _only(changes, "amount", "deadline", "motivation", "soft")
        return await goals.update(self.db, user_id, goal_id, **fields)


class PgRecords(_Base):
    """Plain per-user CRUD on one ORM table (only its columns are written)."""

    model: type[Base]
    what: str

    def __init__(self, db: AsyncSession, model: type[Base], what: str) -> None:
        super().__init__(db)
        self.model, self.what = model, what

    def _columns(self, data: Mapping[str, Any]) -> dict[str, Any]:
        names = {c.key for c in self.model.__table__.columns} - {"id", "user_id"}
        return {k: v for k, v in data.items() if k in names}

    async def _row(self, user_id: int, record_id: int) -> Base:
        return await owned(self.db, self.model, user_id, record_id, self.what)

    async def create(self, user_id: int, data: Mapping[str, Any]) -> Row:
        row = self.model(user_id=user_id, **self._columns(data))
        self.db.add(row)
        await self.db.flush()
        return _dict(row)

    async def get(self, user_id: int, record_id: int) -> Row:
        return _dict(await self._row(user_id, record_id))

    async def update(self, user_id: int, record_id: int, changes: Mapping[str, Any]) -> Row:
        row = await self._row(user_id, record_id)
        for name, value in self._columns(changes).items():
            setattr(row, name, value)
        await self.db.flush()
        return _dict(row)

    async def remove(self, user_id: int, record_id: int) -> None:
        await self.db.delete(await self._row(user_id, record_id))
        await self.db.flush()

    async def list(self, user_id: int) -> list[Row]:
        columns = self.model.__table__.c
        rows = await self.db.scalars(
            select(self.model).where(columns.user_id == user_id).order_by(columns.id)
        )
        return [_dict(r) for r in rows]


class PgIncomeSources(PgRecords):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, m.IncomeSource, "Income source")

    async def create(self, user_id: int, data: Mapping[str, Any]) -> Row:
        made = await income_sources.create(
            self.db,
            user_id,
            source=data["source"],
            amount=Decimal(data["amount"]),
            day_of_month=data["day_of_month"],
        )
        return await self.get(user_id, made.id)

    async def update(self, user_id: int, record_id: int, changes: Mapping[str, Any]) -> Row:
        fields = _only(changes, "source", "amount", "day_of_month")
        await income_sources.update(self.db, user_id, record_id, **fields)
        return await self.get(user_id, record_id)

    async def remove(self, user_id: int, record_id: int) -> None:
        await income_sources.delete(self.db, user_id, record_id)


class PgFixedCosts(PgRecords):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, m.FixedCost, "Fixed cost")

    async def create(self, user_id: int, data: Mapping[str, Any]) -> Row:
        made = await fixed_costs.create(
            self.db,
            user_id,
            name=data["name"],
            amount=Decimal(data["amount"]),
            day_of_month=data["day_of_month"],
        )
        return await self.get(user_id, made.id)

    async def update(self, user_id: int, record_id: int, changes: Mapping[str, Any]) -> Row:
        fields = _only(changes, "name", "amount", "day_of_month")
        await fixed_costs.update(self.db, user_id, record_id, **fields)
        return await self.get(user_id, record_id)

    async def remove(self, user_id: int, record_id: int) -> None:
        await fixed_costs.delete(self.db, user_id, record_id)


class PgLifeEvents(PgRecords):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, m.LifeEvent, "Life event")

    async def create(self, user_id: int, data: Mapping[str, Any]) -> Row:
        made = await life_events.create(
            self.db,
            user_id,
            name=data["name"],
            date=data["date"],
            est_cost=Decimal(data["est_cost"]),
            type=data["type"],
            source=data.get("source"),
        )
        return await self.get(user_id, made.id)

    async def update(self, user_id: int, record_id: int, changes: Mapping[str, Any]) -> Row:
        status = changes.get("status")
        if status == LifeEventStatus.CANCELLED:
            await life_events.cancel(self.db, user_id, record_id)
        elif status == LifeEventStatus.DONE:
            await life_events.mark_done(self.db, user_id, record_id)
        fields = _only(changes, "name", "date", "est_cost", "type")
        if fields:
            await life_events.update(self.db, user_id, record_id, **fields)
        return await self.get(user_id, record_id)


class PgSlips(PgRecords):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, m.Slip, "Slip")

    async def create(self, user_id: int, data: Mapping[str, Any]) -> Row:
        """`amount_over` is what that day's ledger went over its budget (0 without a row)."""
        day = await self.db.get(m.DayLedger, (user_id, data["date"]))
        over = max(Decimal("0"), day.spent - day.budget) if day is not None else Decimal("0")
        return await super().create(user_id, {"amount_over": over, **data})


class PgReflections(PgRecords):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, m.Reflection, "Reflection")

    async def create(self, user_id: int, data: Mapping[str, Any]) -> Row:
        today = clock.today()
        week_start = today - timedelta(days=today.weekday())
        return await super().create(user_id, {"week_start": week_start, **data})


class PgPlanPreferences(_Base):
    async def get(self, user_id: int) -> dm.PlanPreferences:
        return await plan_preferences.get(self.db, user_id)

    async def save(self, user_id: int, preferences: dm.PlanPreferences) -> dm.PlanPreferences:
        await users.get(self.db, user_id)
        return await plan_preferences.save(self.db, user_id, preferences)


class PgLifeProfile(_Base):
    async def set_note(self, user_id: int, key: str, value: str) -> Row:
        return await life_profile.set_key(self.db, user_id, key, value)


class PgAgentEvents(_Base):
    async def get(self, user_id: int, event_id: int) -> Row:
        return (await agent_events.get(self.db, user_id, event_id)).model_dump()

    async def open_question_for(self, user_id: int, tx_id: int) -> Row | None:
        row = await self.db.scalar(
            select(m.AgentEvent)
            .where(
                m.AgentEvent.user_id == user_id,
                m.AgentEvent.ref_transaction_id == tx_id,
                m.AgentEvent.status == AgentEventStatus.ASKED,
            )
            .order_by(m.AgentEvent.id.desc())
            .limit(1)
        )
        return None if row is None else await self.get(user_id, row.id)

    async def mark_answered(self, user_id: int, event_id: int) -> Row:
        return (await agent_events.mark_answered(self.db, user_id, event_id)).model_dump()

    async def mark_handled(self, user_id: int, event_id: int) -> Row:
        """pending | asked → handled. Already answered or handled → the event as it is (Claude
        often closes the question it just answered with `annotate_transaction`)."""
        event = await agent_events.get(self.db, user_id, event_id)
        if event.status in (AgentEventStatus.ANSWERED, AgentEventStatus.HANDLED):
            return event.model_dump()
        return (await agent_events.mark_handled(self.db, user_id, event_id)).model_dump()


class PgTransfers(_Base):
    async def to_savings(self, user_id: int, amount: Decimal) -> Row:
        """A manual transfer into the goal pot (like the payday auto-save): the account goes down
        by `amount` and the pot up."""
        if amount <= 0:
            raise invalid("invalid_amount", "A transfer amount must be positive.")
        pot = await pots.goal_pot(self.db, user_id)
        transfer = await transfers.create(
            self.db,
            user_id,
            amount=amount,
            kind=TransferKind.MANUAL,
            pot_id=pot.id if pot is not None else None,
        )
        await accounts.adjust_balance(self.db, user_id, -amount)
        if pot is not None:
            await pots.add_saved(self.db, user_id, pot.id, amount)
        return transfer.model_dump()


class PgUsers(_Base):
    async def mark_onboarded(self, user_id: int) -> Row:
        return (await users.set_onboarded(self.db, user_id)).model_dump()


class PgPlans(_Base):
    async def latest(self, user_id: int) -> Row | None:
        plan: PlanSummary | None = await plans.latest(self.db, user_id)
        return None if plan is None else plan.model_dump()


class PgForecasts(_Base):
    async def latest(self, user_id: int) -> Row | None:
        forecast: Forecast | None = await forecasts.latest(self.db, user_id)
        return None if forecast is None else forecast.model_dump()


class PgProducts(_Base):
    async def list(self) -> list[Row]:
        return [p.model_dump() for p in await products.list_all(self.db)]


class PgToolCalls:
    """Logs in its own unit of work (see the module docstring). No run → nothing to log against
    (`tool_calls.run_id` is NOT NULL): the run id comes from the call or from /chat's
    `agent_runs.CURRENT_RUN`."""

    async def log(
        self,
        user_id: int,
        run_id: int | None,
        tool_use_id: str,
        tool_name: str,
        tool_input: Mapping[str, Any],
        output: str,
        status: str,
    ) -> None:
        run = run_id if run_id is not None else agent_runs.CURRENT_RUN.get()
        if run is None:
            return
        try:
            stored: Any = json.loads(output)
        except ValueError:
            stored = output
        async with unit_of_work() as db:
            await tool_calls.log(
                db,
                user_id,
                run,
                tool_name=tool_name,
                input={"tool_use_id": tool_use_id, **_plain(tool_input)},
                output=stored,
                status=_TOOL_STATUS.get(status, ToolCallStatus.ERROR),
            )


def pg_services(db: AsyncSession) -> Services:
    """Every port over `db` (one unit of work)."""
    return Services(
        transactions=PgTransactions(db),
        receivables=PgReceivables(db),
        life_facts=PgLifeFacts(db),
        signatures=PgSignatures(db),
        pattern_rules=PgPatternRules(db),
        pots=PgPots(db),
        goals=PgGoals(db),
        income_sources=PgIncomeSources(db),
        fixed_costs=PgFixedCosts(db),
        life_events=PgLifeEvents(db),
        slips=PgSlips(db),
        reflections=PgReflections(db),
        plan_preferences=PgPlanPreferences(db),
        life_profile=PgLifeProfile(db),
        agent_events=PgAgentEvents(db),
        transfers=PgTransfers(db),
        users=PgUsers(db),
        plans=PgPlans(db),
        forecasts=PgForecasts(db),
        products=PgProducts(db),
        tool_calls=PgToolCalls(),
    )
