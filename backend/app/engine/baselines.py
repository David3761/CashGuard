"""Household scale and context-adjusted baselines (arch 5.3.5). Pure, no DB, no clock.

Household scale (OECD-modified): the user is the first adult (1.0); `household_member` facts list
the *other* people, each 0.5 if 14 or older, 0.3 if a child under 14. Pets are a separate fact type.

Baselines: per category, the personal median + MAD of effective amounts over the last 180 days
(bound inclusive, Bucharest days), blended with the prior: (n·personal + 5·prior) / (n + 5).
Household categories (arch 4.5) use prior × household scale × city index.
"""

import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from decimal import Decimal
from typing import TypedDict
from zoneinfo import ZoneInfo

from app.domain.enums import Beneficiary, Category, Direction, FactStatus, FactType, Purpose
from app.domain.models import Baseline, LifeFact, TxView
from app.domain.money import to_money
from app.engine.calendar import days_in_month
from app.engine.stats import blend, median_and_mad, monthly_rate


class CategoryPrior(TypedDict):
    basket_median: float
    monthly_median: float
    cv: float


class Priors(TypedDict):
    """Shape of `data/priors.json` (C1): single-adult priors per category + city index."""

    city_index: dict[str, float]
    categories: dict[str, CategoryPrior]


# (role, age, valid_from, valid_to): one `household_member` fact, other than the user
Member = tuple[str, int | None, date | None, date | None]

USER_WEIGHT = Decimal("1.0")
OTHER_PERSON_WEIGHT = Decimal("0.5")
CHILD_WEIGHT = Decimal("0.3")
CHILD_AGE_LIMIT = 14

BUCHAREST = ZoneInfo("Europe/Bucharest")
WINDOW_DAYS = 180
PRIOR_WEIGHT = 5
MAD_FALLBACK_SHARE = Decimal("0.25")
HOUSEHOLD_SCALED = frozenset(
    {
        Category.GROCERIES,
        Category.HOUSEHOLD_GOODS,
        Category.HEALTH_PHARMACY,
        Category.UTILITIES,
        Category.KIDS,
        Category.CLOTHING,
        Category.PERSONAL_CARE,
    }
)
# variable essentials only: rent and utilities are fixed costs and already left out of the daily budget
ESSENTIAL = frozenset(
    {Category.GROCERIES, Category.TRANSPORT, Category.HEALTH_PHARMACY, Category.HOUSEHOLD_GOODS}
)
NOT_SPENDING = frozenset({Category.INCOME, Category.TRANSFERS, Category.SAVINGS})
NOT_ME = frozenset({Beneficiary.OTHERS, Beneficiary.EMPLOYER})


# ── household scale ──────────────────────────────────────────────────────────


def is_active(valid_from: date | None, valid_to: date | None, on_date: date) -> bool:
    """True when `on_date` is inside `[valid_from, valid_to]`; a missing bound is open-ended."""
    if valid_from is not None and valid_to is not None and valid_to < valid_from:
        raise ValueError("valid_to must not be before valid_from")
    return (valid_from is None or valid_from <= on_date) and (valid_to is None or on_date <= valid_to)


def person_weight(role: str, age: int | None) -> Decimal:
    """OECD weight of one member other than the user: 0.5 from 14 years, 0.3 for a younger child."""
    if age is not None and age < 0:
        raise ValueError("age must be ≥ 0")
    if role == "adult":
        return OTHER_PERSON_WEIGHT
    if role == "child":
        if age is None:
            raise ValueError("a child needs an age")
        return CHILD_WEIGHT if age < CHILD_AGE_LIMIT else OTHER_PERSON_WEIGHT
    raise ValueError(f"unknown household role {role!r} (expected 'adult' or 'child')")


def scale_from_members(members: Iterable[Member], on_date: date) -> Decimal:
    """1.0 for the user plus the weight of every member active on `on_date`."""
    return USER_WEIGHT + sum(
        (
            person_weight(role, age)
            for role, age, valid_from, valid_to in members
            if is_active(valid_from, valid_to, on_date)
        ),
        Decimal(0),
    )


def household_scale(facts: Iterable[LifeFact], on_date: date) -> Decimal:
    """Household scale on `on_date` from the confirmed `household_member` facts (hypotheses don't count)."""
    members = [
        (f.value.role, f.value.age, f.valid_from, f.valid_to)
        for f in facts
        if f.type == FactType.HOUSEHOLD_MEMBER and f.status == FactStatus.CONFIRMED
    ]
    return scale_from_members(members, on_date)


# ── baselines ────────────────────────────────────────────────────────────────


def _local_date(tx: TxView) -> date:
    return tx.occurred_at.astimezone(BUCHAREST).date()


def _counts(tx: TxView) -> bool:
    """Own spending only: debits, not pot-funded, not for others / the employer, own share > 0."""
    return (
        tx.direction == Direction.DEBIT
        and tx.category not in NOT_SPENDING
        and tx.purpose != Purpose.PLANNED_EVENT
        and tx.beneficiary not in NOT_ME
        and tx.effective_amount > 0
    )


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()


def _city_index(priors: Priors, city: str | None) -> Decimal:
    """City index, matched ignoring case and diacritics ("Iasi" = "Iași"); unknown city → 1."""
    if city is not None:
        for name, index in priors["city_index"].items():
            if _fold(name) == _fold(city):
                return Decimal(str(index))
    return Decimal(1)


def _baseline(
    category: Category,
    amounts: list[Decimal],
    prior: CategoryPrior | None,
    scale: Decimal,
    city_index: Decimal,
    span_days: int,
) -> Baseline:
    n = len(amounts)
    personal_median, personal_mad = median_and_mad(amounts)
    personal_monthly = monthly_rate(sum(amounts, Decimal(0)), span_days)
    household = category in HOUSEHOLD_SCALED
    context = scale * city_index if household else Decimal(1)
    k = PRIOR_WEIGHT if prior is not None else 0  # no prior → personal history only
    prior_median = Decimal(str(prior["basket_median"])) * context if prior else Decimal(0)
    prior_monthly = Decimal(str(prior["monthly_median"])) * context if prior else Decimal(0)
    expected_median = blend(n, personal_median, prior_median, k)
    return Baseline(
        category=category,
        personal_median=to_money(personal_median),
        personal_mad=to_money(personal_mad if personal_mad > 0 else MAD_FALLBACK_SHARE * expected_median),
        n=n,
        prior_median=to_money(prior_median),
        household_multiplier=scale if household else Decimal(1),
        expected_median=to_money(expected_median),
        monthly_expected=to_money(blend(n, personal_monthly, prior_monthly, k)),
    )


def compute_baselines(
    txs: Iterable[TxView], priors: Priors, scale: Decimal, city: str | None, today: date
) -> dict[Category, Baseline]:
    """One baseline per spending category seen in the window or present in the priors."""
    since = today - timedelta(days=WINDOW_DAYS)
    window = [t for t in txs if since <= _local_date(t) <= today]
    # the history actually covered (a 4-month seed must not be read as 6 months)
    span_days = (today - min(map(_local_date, window))).days + 1 if window else 0
    amounts: defaultdict[Category, list[Decimal]] = defaultdict(list)
    for t in window:
        if _counts(t):
            amounts[t.category].append(t.effective_amount)
    city_index = _city_index(priors, city)
    categories = (set(amounts) | {Category(c) for c in priors["categories"]}) - NOT_SPENDING
    return {
        c: _baseline(c, amounts.get(c, []), priors["categories"].get(c), scale, city_index, span_days)
        for c in sorted(categories)
    }


def essentials_floor(baselines: Mapping[Category, Baseline], month: date) -> Decimal:
    """Per day: Σ monthly_expected of the essential categories / days in `month`'s month."""
    total = sum((b.monthly_expected for c, b in baselines.items() if c in ESSENTIAL), Decimal(0))
    return to_money(total / days_in_month(month.year, month.month))


def rescale(
    baselines: Mapping[Category, Baseline], old_scale: Decimal, new_scale: Decimal
) -> dict[Category, Baseline]:
    """Instant household change: household categories × new/old; others unchanged (arch 5.3.5)."""
    if old_scale <= 0 or new_scale <= 0:
        raise ValueError("household scales must be > 0")
    ratio = new_scale / old_scale
    return {
        c: b.model_copy(
            update={
                "prior_median": to_money(b.prior_median * ratio),
                "expected_median": to_money(b.expected_median * ratio),
                "monthly_expected": to_money(b.monthly_expected * ratio),
                "household_multiplier": new_scale,
            }
        )
        if c in HOUSEHOLD_SCALED
        else b
        for c, b in baselines.items()
    }
