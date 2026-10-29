"""Monte Carlo goal forecast (arch 6.7 "Goal forecast", D27, E8). Pure; numpy floats inside.

Savings_T = goal_pot.saved + max(0, Σ_m (Income − Fixed − ΣVar − PotContrib − Events + Recv − Shock))
over every month from the current one to the deadline's, for `n_paths` paths:
- Income: deterministic per month (salaries), or bootstrapped from history with an irregular-income fact.
- Var: per category, a bootstrap of the user's full-month effective totals (last 6 months, ≥ 3 needed),
  else lognormal around the baseline's monthly_expected (CV 0.25); × household-scale ratio for household
  categories in months where a temporary member is there; × the share of the month still to come.
- The current month = what was already spent this month (own share + what was paid for others,
  since that money left the account) + the expected rest.
- Events ± 20 %; receivables Bernoulli(p_repay) in their month; shocks Bernoulli(0.05) × lognormal(700),
  off when an emergency pot has money.
Draw order is fixed (variable categories, income, events, shocks, then receivables), so property tests
with the same seed compare like with like (common random numbers).
"""

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

import numpy as np

from app.domain.enums import Category, Direction, FactType, PotKind, PotStatus, Purpose, SignatureEffect
from app.domain.models import UserContext
from app.domain.money import to_money
from app.domain.results import Forecast
from app.engine.baselines import HOUSEHOLD_SCALED, household_scale
from app.engine.calendar import days_in_month, months_between, occurrences, paydays_between
from app.engine.ledger import counts_as_spent, ledger_day
from app.engine.savings import OPEN_RECEIVABLES, p_repay, pot_contribution

DEFAULT_PATHS = 10_000
MIN_HISTORY_MONTHS = 3
HISTORY_MONTHS = 6
PRIOR_CV = 0.25
EVENT_SPREAD = 0.20
SHOCK_PROBABILITY = 0.05
SHOCK_MEDIAN = 700.0
SHOCK_SIGMA = 0.6
QUANTILES = (10, 50, 90)

Month = tuple[int, int]


@dataclass(frozen=True)
class ForecastInputs:
    today: date
    deadline: date
    target: float
    saved: float
    months: tuple[Month, ...]
    income: tuple[float, ...]  # deterministic income per month
    fixed: tuple[float, ...]
    var_history: dict[Category, tuple[float, ...]]  # full-month effective totals, oldest first
    var_prior: dict[Category, float]  # monthly median when history is short
    var_scale: dict[Category, tuple[float, ...]]  # multiplier per month
    var_share: tuple[float, ...]  # share of each month still to come
    var_actual: float  # current month, already spent (own share + paid for others)
    events: tuple[float, ...]
    pot_contrib: tuple[float, ...]
    receivables: tuple[tuple[float, float, int], ...]  # (amount, p_repay, month index)
    shocks: bool
    income_history: tuple[float, ...] = ()  # non-empty → irregular income, bootstrapped
    income_actual: float = 0.0  # irregular income already received this month
    excluded: frozenset[Category] = field(default_factory=frozenset)


# ── building the inputs from the read model ──────────────────────────────────


def _month_bounds(month: Month) -> tuple[date, date]:
    year, m = month
    return date(year, m, 1), date(year, m, days_in_month(year, m))


def _per_month(day_of_month: int, amount: float, months: tuple[Month, ...], deadline: date) -> list[float]:
    out = []
    for month in months:
        first, last = _month_bounds(month)
        out.append(amount * len(occurrences(day_of_month, first - timedelta(days=1), min(last, deadline))))
    return out


def _full_months(ctx: UserContext, today: date) -> list[Month]:
    """Calendar months fully covered by the history, before the current month, at most the last 6."""
    if not ctx.transactions:
        return []
    start = min(ledger_day(t.occurred_at) for t in ctx.transactions)
    current = (today.year, today.month)
    months = [m for m in months_between(start, today) if m != current and _month_bounds(m)[0] >= start]
    return months[-HISTORY_MONTHS:]


def _irregular_income(ctx: UserContext) -> bool:
    for f in ctx.facts:
        if f.type == FactType.income_pattern:
            value = f.value if isinstance(f.value, dict) else vars(f.value)
            if value.get("regularity") == "irregular":
                return True
    return False


def build_forecast_inputs(
    ctx: UserContext, today: date, *, deadline: date | None = None, target: Decimal | None = None
) -> ForecastInputs:
    """ForecastInputs from the read model; `deadline` / `target` override the goal's (what-if, options)."""
    goal = ctx.goal
    if goal is None:
        raise ValueError("no active goal")
    deadline = deadline or goal.deadline
    months = tuple(months_between(today, deadline))
    count = len(months)

    income = [0.0] * count
    for s in ctx.income_sources:
        income = [
            a + b for a, b in zip(income, _per_month(s.day_of_month, float(s.amount), months, deadline))
        ]
    fixed = [0.0] * count
    for c in ctx.fixed_costs:
        fixed = [a + b for a, b in zip(fixed, _per_month(c.day_of_month, float(c.amount), months, deadline))]

    history_months = _full_months(ctx, today)
    var_totals: dict[Category, dict[Month, float]] = {}
    income_totals: dict[Month, float] = {m: 0.0 for m in history_months}
    current = (today.year, today.month)
    var_actual = income_actual = 0.0
    for t in ctx.transactions:
        day = ledger_day(t.occurred_at)
        month = (day.year, day.month)
        if t.direction == Direction.credit and t.category == Category.income:
            if month in income_totals:
                income_totals[month] += float(t.amount)
            elif month == current and day <= today:
                income_actual += float(t.amount)
            continue
        if month == current and day <= today and t.direction == Direction.debit:
            if counts_as_spent(t, ctx.fixed_costs):
                var_actual += float(t.effective_amount)
            if t.purpose != Purpose.planned_event:
                var_actual += float(t.amount - t.effective_amount)  # paid for others, left the account
        if month in income_totals and counts_as_spent(t, ctx.fixed_costs):
            var_totals.setdefault(t.category, {}).setdefault(month, 0.0)
            var_totals[t.category][month] += float(t.effective_amount)

    categories = set(var_totals) | {c for c, b in ctx.baselines.items() if b.monthly_expected > 0}
    var_history = {c: tuple(var_totals.get(c, {}).get(m, 0.0) for m in history_months) for c in categories}
    var_prior = {c: float(ctx.baselines[c].monthly_expected) for c in categories if c in ctx.baselines}
    for c in categories:
        if c not in var_prior and history_months:
            var_prior[c] = sum(var_history[c]) / len(history_months)

    scale_now = float(household_scale(ctx.facts, today))
    ratios = tuple(
        float(household_scale(ctx.facts, _month_bounds(m)[0] + timedelta(days=14))) / scale_now
        for m in months
    )
    var_scale = {c: ratios if c in HOUSEHOLD_SCALED else (1.0,) * count for c in categories}

    share = []
    for month in months:
        first, last = _month_bounds(month)
        start = max(first, today + timedelta(days=1))
        end = min(last, deadline)
        share.append(max(0, (end - start).days + 1) / days_in_month(*month))

    covered = {
        p.life_event_id for p in ctx.pots if p.life_event_id is not None and p.status == PotStatus.active
    }
    events = [0.0] * count
    for e in ctx.life_events:
        if e.status == "planned" and today <= e.date <= deadline and e.id not in covered:
            events[months.index((e.date.year, e.date.month))] += float(e.est_cost)
    for s in ctx.signatures:
        expected = s.effect == SignatureEffect.expects_event and s.expected_amount and s.expected_date
        if expected and today <= s.expected_date <= deadline:
            index = months.index((s.expected_date.year, s.expected_date.month))
            events[index] += float(s.expected_amount * s.strength)

    days = [s.day_of_month for s in ctx.income_sources]
    goal_pot_id = ctx.goal_pot.id if ctx.goal_pot is not None else None
    pot_contrib = [0.0] * count
    for p in ctx.pots:
        if p.id == goal_pot_id or p.kind in (PotKind.goal, PotKind.emergency) or p.status != PotStatus.active:
            continue
        per_payday = float(pot_contribution(p.target, p.saved, p.deadline, today, days))
        end = min(p.deadline or deadline, deadline)
        paydays = paydays_between(days, today, end)
        if not paydays and per_payday:
            pot_contrib[0] += per_payday
        for d in paydays:
            pot_contrib[months.index((d.year, d.month))] += per_payday

    receivables = tuple(
        (
            float(r.amount),
            float(p_repay(r.expected_by, today)),
            months.index(_month_of(max(r.expected_by, today))),
        )
        for r in ctx.receivables
        if r.status in OPEN_RECEIVABLES and r.expected_by <= deadline
    )
    emergency = any(
        p.kind == PotKind.emergency and p.status == PotStatus.active and p.saved > 0 for p in ctx.pots
    )
    irregular = _irregular_income(ctx) and len(history_months) >= MIN_HISTORY_MONTHS
    return ForecastInputs(
        today=today,
        deadline=deadline,
        target=float(target if target is not None else goal.amount),
        saved=float(ctx.goal_pot.saved) if ctx.goal_pot is not None else 0.0,
        months=months,
        income=(0.0,) * count if irregular else tuple(income),
        fixed=tuple(fixed),
        var_history=var_history,
        var_prior=var_prior,
        var_scale=var_scale,
        var_share=tuple(share),
        var_actual=var_actual,
        events=tuple(events),
        pot_contrib=tuple(pot_contrib),
        receivables=receivables,
        shocks=not emergency,
        income_history=tuple(income_totals[m] for m in history_months) if irregular else (),
        income_actual=income_actual if irregular else 0.0,
    )


def _month_of(d: date) -> Month:
    return (d.year, d.month)


# ── the simulation ───────────────────────────────────────────────────────────


def _sample_monthly(
    rng: np.random.Generator, history: tuple[float, ...], prior: float, shape: tuple[int, int]
) -> np.ndarray:
    if len(history) >= MIN_HISTORY_MONTHS:
        return rng.choice(np.asarray(history, dtype=float), size=shape)
    sigma = math.sqrt(math.log(1 + PRIOR_CV**2))
    return prior * rng.lognormal(0.0, sigma, size=shape)


def simulate_savings(inputs: ForecastInputs, n_paths: int, seed: int) -> np.ndarray:
    """Goal savings per path and month, shape (n_paths, months): saved + max(0, cumulative net)."""
    rng = np.random.default_rng(seed)
    shape = (n_paths, len(inputs.months))
    share = np.asarray(inputs.var_share)
    var = np.zeros(shape)
    for category in sorted(set(inputs.var_history) | set(inputs.var_prior)):
        if category in inputs.excluded:
            continue
        draws = _sample_monthly(
            rng, inputs.var_history.get(category, ()), inputs.var_prior.get(category, 0.0), shape
        )
        var += draws * np.asarray(inputs.var_scale.get(category, (1.0,) * shape[1])) * share
    var[:, 0] += inputs.var_actual
    income = np.broadcast_to(np.asarray(inputs.income), shape).copy()
    if inputs.income_history:
        income += rng.choice(np.asarray(inputs.income_history), size=shape) * share
        income[:, 0] += inputs.income_actual
    events = np.asarray(inputs.events) * rng.uniform(1 - EVENT_SPREAD, 1 + EVENT_SPREAD, size=shape)
    shock = (rng.random(shape) < SHOCK_PROBABILITY) * rng.lognormal(
        math.log(SHOCK_MEDIAN), SHOCK_SIGMA, size=shape
    )
    if not inputs.shocks:
        shock[:] = 0.0
    received = np.zeros(shape)
    for amount, probability, month in inputs.receivables:
        received[:, month] += amount * (rng.random(n_paths) < probability)
    net = income - np.asarray(inputs.fixed) - var - np.asarray(inputs.pot_contrib) - events + received - shock
    savings: np.ndarray = inputs.saved + np.maximum(np.cumsum(net, axis=1), 0.0)
    return savings


def _reach_date(inputs: ForecastInputs, median_path: np.ndarray) -> date | None:
    if inputs.saved >= inputs.target:
        return inputs.today
    hits = np.nonzero(median_path >= inputs.target)[0]
    if hits.size == 0:
        return None
    last_day = date(*inputs.months[int(hits[0])], days_in_month(*inputs.months[int(hits[0])]))
    return min(last_day, inputs.deadline)


def forecast(inputs: ForecastInputs, n_paths: int = DEFAULT_PATHS, seed: int = 0) -> Forecast:
    if inputs.saved >= inputs.target:
        saved = to_money(inputs.saved)
        return Forecast(probability=1.0, p10=saved, p50=saved, p90=saved, expected_reach_date=inputs.today)
    savings = simulate_savings(inputs, n_paths, seed)
    final = savings[:, -1]
    p10, p50, p90 = (to_money(round(float(q), 2)) for q in np.percentile(final, QUANTILES))
    return Forecast(
        probability=round(float(np.mean(final >= inputs.target)), 4),
        p10=p10,
        p50=p50,
        p90=p90,
        expected_reach_date=_reach_date(inputs, np.median(savings, axis=0)),
    )


def is_weekly_snapshot(today: date, last_snapshot: date | None) -> bool:
    """The first forecast on or after Monday 00:00 (sim time) of this week is the weekly snapshot."""
    week_start = today - timedelta(days=today.weekday())
    return last_snapshot is None or last_snapshot < week_start
