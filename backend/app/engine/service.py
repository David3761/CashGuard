"""DB shells for the engine (arch 15.1): load with the context loader or a service, call the pure
core, save.

Async because the DB layer (B2) and `load_user_context` (B4) are async; arch 15.1 shows plain `def`.
Every write goes through bomboe's services and is scoped by `user_id`; the caller owns the
transaction.
"""

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.domain.enums import PotKind, TransferKind
from app.domain.models import Baseline, Transfer, TxView
from app.domain.results import AnomalyFeatures, Forecast, PlanSummary, SimResult
from app.domain.user_context import UserContext
from app.engine import anomaly, ledger
from app.engine.baselines import (
    children_count,
    compute_baselines,
    essentials_floor,
    household_scale,
    load_priors,
)
from app.engine.budget import compute_plan, plan_inputs
from app.engine.forecast import build_forecast_inputs, forecast, is_weekly_snapshot
from app.engine.options import drivers, options
from app.engine.savings import auto_save_amount, matching_income_source, pot_contribution
from app.engine.simulate import simulate
from app.engine.stats import stable_seed
from app.errors import DomainError
from app.services import accounts as accounts_service
from app.services import baselines as baselines_service
from app.services import fixed_costs as fixed_costs_service
from app.services import forecasts as forecasts_service
from app.services import ledger as ledger_service
from app.services import notify as notify_service
from app.services import plans as plans_service
from app.services import pots as pots_service
from app.services import transactions as transactions_service
from app.services import transfers as transfers_service
from app.services import users as users_service
from app.services.context_loader import load_user_context

PLAN_LOCK_NAMESPACE = 7331  # pg_advisory_xact_lock(namespace, user_id): one plan version at a time


async def _context(db: AsyncSession, user_id: int) -> tuple[date, UserContext]:
    today = clock.today()
    return today, await load_user_context(db, user_id, today)


# ── E6: baselines ────────────────────────────────────────────────────────────


async def recompute_baselines(db: AsyncSession, user_id: int) -> dict[str, Baseline]:
    """Recompute and save `category_baselines` and `users.household_scale` (arch 5.3.5)."""
    today, ctx = await _context(db, user_id)
    scale = household_scale(ctx.facts, today)
    baselines = compute_baselines(
        ctx.transactions,
        load_priors(),
        scale,
        ctx.profile.city,
        today,
        children=children_count(ctx.facts, today),  # D50
    )
    await baselines_service.replace_all(db, user_id, list(baselines.values()))
    await users_service.update(db, user_id, household_scale=scale)
    return {str(c): b for c, b in baselines.items()}


# ── E3: ledger ───────────────────────────────────────────────────────────────


async def _write_delta(db: AsyncSession, user_id: int, delta: ledger.LedgerDelta) -> None:
    if delta.balance:
        await accounts_service.adjust_balance(db, user_id, delta.balance)
    if delta.spent:
        await ledger_service.add_spent(db, user_id, delta.day, delta.spent)  # atomic (B3)
    if delta.pot_saved and delta.pot_id is not None:
        await pots_service.add_saved(db, user_id, delta.pot_id, delta.pot_saved)


async def apply_transaction(db: AsyncSession, user_id: int, tx_id: int) -> None:
    """Balance, day_ledger (effective amount) and pot for one newly processed transaction."""
    tx = await transactions_service.get(db, user_id, tx_id)
    if tx.status == "resolved":
        return  # already applied: processing twice must not move money twice
    fixed = await fixed_costs_service.list_all(db, user_id)
    await _write_delta(db, user_id, ledger.apply(tx, fixed))


async def on_annotation_changed(
    db: AsyncSession, user_id: int, tx_id: int, old: TxView, new: TxView
) -> None:
    """Move the day's spent (and the pot) when an answer or an edit re-annotates a transaction."""
    fixed = await fixed_costs_service.list_all(db, user_id)
    await _write_delta(db, user_id, ledger.reannotate_delta(old, new, fixed))


async def own_share_estimate(db: AsyncSession, user_id: int, tx: TxView) -> Decimal:
    """The user's share when they gave no count or amount: the usual basket, clamped to the
    amount."""
    _, ctx = await _context(db, user_id)
    baseline = ctx.baselines.get(tx.category) if tx.category is not None else None
    return ledger.estimate_own_share(tx.amount, baseline)


# ── E7: anomaly features ─────────────────────────────────────────────────────


async def anomaly_features(db: AsyncSession, user_id: int, tx: TxView) -> AnomalyFeatures:
    _, ctx = await _context(db, user_id)
    disposable = anomaly.monthly_disposable(ctx.income_sources, ctx.fixed_costs)
    baseline = ctx.baselines.get(tx.category) if tx.category is not None else None
    return anomaly.anomaly_features(tx, baseline, ctx.transactions, disposable)


# ── E4: plan versions ────────────────────────────────────────────────────────


async def recompute_plan(
    db: AsyncSession, user_id: int, reason: str, trigger_ref: dict[str, Any] | None = None
) -> PlanSummary | None:
    """Compute and save the next plan version; also refresh the pots' contributions. No goal →
    None."""
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:ns, :uid)"), {"ns": PLAN_LOCK_NAMESPACE, "uid": user_id}
    )
    today, ctx = await _context(db, user_id)
    result = compute_plan(plan_inputs(ctx, today, essentials_floor(ctx.baselines, today)), today)
    if result is None:
        return None
    # bomboe's plans.save assigns the next version (under its own lock) and fills
    # previous_today_budget from the version before.
    summary = await plans_service.save(db, user_id, result, reason=reason, trigger_ref=trigger_ref)
    paydays = [s.day_of_month for s in ctx.income_sources]
    for pot in ctx.pots:
        if pot.kind in (PotKind.EVENT, PotKind.CUSTOM):
            contribution = pot_contribution(pot.target, pot.saved, pot.deadline, today, paydays)
            await pots_service.update(db, user_id, pot.id, monthly_contribution=contribution)
    return summary


# ── E8 / E9: forecast, drivers, options ──────────────────────────────────────


async def forecast_goal(db: AsyncSession, user_id: int, plan_version: int) -> Forecast:
    """Forecast + drivers + options, saved as a `goal_forecasts` row (weekly snapshot on
    Mondays)."""
    today, ctx = await _context(db, user_id)
    if ctx.goal is None:
        raise DomainError("no_goal", "there is no active goal to forecast")
    seed = stable_seed(user_id, today, plan_version)
    inputs = build_forecast_inputs(ctx, today)
    result = forecast(inputs, seed=seed)
    previous = ctx.forecast.probability if ctx.forecast is not None else None
    last_week = ctx.last_weekly_forecast
    result = result.model_copy(
        update={
            "drivers": drivers(inputs, ctx.signatures, seed),
            "options": options(ctx, today, current=result.probability, previous=previous, seed=seed)
            or None,
            "previous_probability": previous,
            "last_week_probability": last_week.probability if last_week is not None else None,
            "is_weekly_snapshot": is_weekly_snapshot(
                today, last_week.sim_date if last_week is not None else None
            ),
            "sim_date": today,
            "plan_version": plan_version,
        }
    )
    reason = ctx.plan.reason if ctx.plan is not None else None
    await forecasts_service.save(db, user_id, result, goal_id=ctx.goal.id, reason=reason)
    return result


# ── E5: what-if ──────────────────────────────────────────────────────────────


async def simulate_plan(db: AsyncSession, user_id: int, changes: Mapping[str, Any]) -> SimResult:
    """What-if on a copy of the context; writes nothing."""
    today, ctx = await _context(db, user_id)
    version = ctx.plan.version if ctx.plan is not None else 0
    return simulate(ctx, today, changes, seed=stable_seed(user_id, today, version))


# ── E10: payday auto-save ────────────────────────────────────────────────────


async def auto_save(db: AsyncSession, user_id: int, income_tx_id: int) -> Transfer | None:
    """Move the planned saving to the goal pot when a salary is processed (D37); idempotent per
    salary."""
    existing = await transfers_service.for_income(db, user_id, income_tx_id)
    if existing is not None:
        return existing
    tx = await transactions_service.get(db, user_id, income_tx_id)
    today, ctx = await _context(db, user_id)
    goal, pot = ctx.goal, ctx.goal_pot
    if goal is None or pot is None or matching_income_source(tx, ctx.income_sources) is None:
        return None
    amount = auto_save_amount(
        still_to_save=goal.amount - pot.saved,
        goal_deadline=goal.deadline,
        balance=ctx.account.current_balance,
        today=today,
        income_days=[s.day_of_month for s in ctx.income_sources],
        fixed_costs=ctx.fixed_costs,
        essentials_floor=essentials_floor(ctx.baselines, today),
    )
    if amount <= 0:
        return None
    transfer = await transfers_service.create(
        db,
        user_id,
        amount=amount,
        kind=TransferKind.AUTO_SAVE,
        pot_id=pot.id,
        income_transaction_id=income_tx_id,
    )
    await accounts_service.adjust_balance(db, user_id, -amount)
    await pots_service.add_saved(db, user_id, pot.id, amount)
    await notify_service.notify(
        db,
        user_id,
        "auto_save",
        {"amount": amount, "pot_name": pot.name, "transfer_id": transfer.id},
    )
    return transfer
