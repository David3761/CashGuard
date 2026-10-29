"""Drivers and options for the goal forecast (arch 6.7, E9). Pure.

Drivers: re-run the forecast with each cuttable category 100 lei/month lower → percentage points
gained.
Options (only when P < 0.6 or it dropped by more than 10 pp): at most 3, each re-simulated, cheapest
for
the user first: (1) count the expected receivables, (2) move the deadline (soft goals only),
(3) reduce the top driver by at most 25 % of its baseline. Never essential, household or protected
categories. Labels are i18n keys + params (`label_key` + `params`).

TODO(INT): nothing translates the `option.*` keys yet: `app/i18n` has no table for them, `/forecast`
sends `label` (the raw key) to the app and the snapshot prints it; RO / EN texts with the params
(amount, deadline, months, category) still need adding.
"""

from collections.abc import Iterable
from dataclasses import replace
from datetime import date
from decimal import Decimal

from app.domain.enums import Category, SignatureEffect
from app.domain.models import Signature
from app.domain.money import to_money
from app.domain.results import Driver, Option
from app.domain.user_context import UserContext
from app.engine.baselines import ESSENTIAL, HOUSEHOLD_SCALED, NOT_SPENDING
from app.engine.calendar import days_in_month
from app.engine.forecast import ForecastInputs, build_forecast_inputs, forecast

PROBABILITY_FLOOR = 0.6
DROP_TRIGGER = 0.10
MAX_OPTIONS = 3
DRIVER_PATHS = 2_000
DRIVER_CUT = 100.0
MAX_CUT_SHARE = Decimal("0.25")
DEADLINE_STEPS_MONTHS = (1, 2, 3, 6)
NEVER_CUT = (
    ESSENTIAL
    | HOUSEHOLD_SCALED
    | NOT_SPENDING
    | {
        Category.KIDS,
        Category.PETS,
        Category.HOUSING_RENT,
        Category.UTILITIES,
        Category.TELECOM,
        Category.EDUCATION,
    }
)


def cuttable_categories(
    categories: Iterable[Category], signatures: Iterable[Signature]
) -> set[Category]:
    protected = {
        s.category for s in signatures if s.effect == SignatureEffect.PROTECTS and s.category
    }
    return {c for c in categories if c not in NEVER_CUT and c not in protected}


def _cut(inputs: ForecastInputs, category: Category, per_month: float) -> ForecastInputs:
    history = {**inputs.var_history}
    prior = {**inputs.var_prior}
    if category in history:
        history[category] = tuple(max(0.0, x - per_month) for x in history[category])
    if category in prior:
        prior[category] = max(0.0, prior[category] - per_month)
    return replace(inputs, var_history=history, var_prior=prior)


def drivers(inputs: ForecastInputs, signatures: Iterable[Signature], seed: int) -> list[Driver]:
    """Percentage points gained per 100 lei/month less in each cuttable category, best first."""
    base = forecast(inputs, DRIVER_PATHS, seed).probability
    found = []
    for category in sorted(
        cuttable_categories(set(inputs.var_history) | set(inputs.var_prior), signatures)
    ):
        gained = forecast(_cut(inputs, category, DRIVER_CUT), DRIVER_PATHS, seed).probability - base
        found.append(Driver(category=category, pp_per_100_lei=round(max(0.0, gained) * 100, 2)))
    return sorted(found, key=lambda d: (-d.pp_per_100_lei, d.category))


def _add_months(d: date, months: int) -> date:
    year, month = divmod(d.year * 12 + d.month - 1 + months, 12)
    month += 1
    return date(year, month, min(d.day, days_in_month(year, month)))


def options(
    ctx: UserContext, today: date, *, current: float, previous: float | None, seed: int
) -> list[Option]:
    dropped = previous is not None and previous - current > DROP_TRIGGER
    if ctx.goal is None or (current >= PROBABILITY_FLOOR and not dropped):
        return []
    inputs = build_forecast_inputs(ctx, today)
    found: list[Option] = []

    if inputs.receivables:
        certain = replace(inputs, receivables=tuple((a, 1.0, m) for a, _, m in inputs.receivables))
        total = to_money(sum(a for a, _, _ in inputs.receivables))
        found.append(
            Option(
                kind="count_receivables",
                label="option.count_receivables",
                label_key="option.count_receivables",
                params={"amount": total},
                probability=forecast(certain, seed=seed).probability,
                apply_hint={"tool": "offer_payment_request"},
            )
        )

    if ctx.goal.soft:  # only a soft deadline may move (goals.soft)
        for months in DEADLINE_STEPS_MONTHS:
            new_deadline = _add_months(ctx.goal.deadline, months)
            p = forecast(
                build_forecast_inputs(ctx, today, deadline=new_deadline), seed=seed
            ).probability
            if p >= PROBABILITY_FLOOR or months == DEADLINE_STEPS_MONTHS[-1]:
                found.append(
                    Option(
                        kind="move_deadline",
                        label="option.move_deadline",
                        label_key="option.move_deadline",
                        params={"deadline": new_deadline, "months": months},
                        probability=p,
                        apply_hint={"tool": "update_goal", "deadline": new_deadline.isoformat()},
                    )
                )
                break

    top = drivers(inputs, ctx.signatures, seed)
    if top:
        category = top[0].category
        baseline = to_money(inputs.var_prior.get(category, 0.0))
        cut = to_money(baseline * MAX_CUT_SHARE)
        if cut > 0:
            found.append(
                Option(
                    kind="reduce_category",
                    label="option.reduce_category",
                    label_key="option.reduce_category",
                    params={
                        "category": category,
                        "amount_per_month": cut,
                        "baseline_per_month": baseline,
                    },
                    probability=forecast(_cut(inputs, category, float(cut)), seed=seed).probability,
                    apply_hint={"tool": "shape_budget", "category": category},
                )
            )

    return [o for o in found if o.probability > current][:MAX_OPTIONS]
