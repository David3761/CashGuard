"""E6 minimum (danutu's task, written by David G.'s C5-C7 agent under D42): baselines, pure.

Arch 5.3.5 with D50 (kids is per child) and D51 (priors cover variable spending only):
- household scale, OECD-modified: the user 1.0, each other person 14+ 0.5, each child under 14
  0.3; a temporary member counts only inside its validity window;
- prior = basket prior x household scale x city index for the household-scaled categories,
  x the number of children for `kids` (0 children → 0), x the city index for the rest;
- blend: expected = (n · personal_median + 5 · prior_median) / (n + 5) over the last 180 days of
  clean effective amounts (debits, no planned_event, no "not me", no pot-funded spending);
- MAD = 0 → 0.25 x the expected median (applied in `effective_mad`).

Not here yet (danutu's E6 proper): `essentials_floor`, `rescale` and the DB shell.
"""

import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Final

from app.domain.enums import (
    HOUSEHOLD_SCALED_CATEGORIES,
    Beneficiary,
    Category,
    Direction,
    FactStatus,
    FactType,
    HouseholdRole,
    Purpose,
)
from app.domain.models import Baseline, HouseholdMemberValue, LifeFact, TxView
from app.domain.money import to_money
from app.i18n.text import fold

BLEND_K: Final = 5
HISTORY_DAYS: Final = 180
CHILD_AGE: Final = 14  # a child is under 14 (OECD-modified scale)
MAD_FALLBACK: Final = Decimal("0.25")
_ADULT_WEIGHT: Final = Decimal("0.5")
_CHILD_WEIGHT: Final = Decimal("0.3")
_MONTHS_IN_HISTORY: Final = Decimal(6)


def _household_members(facts: Iterable[LifeFact], on_date: date) -> list[HouseholdMemberValue]:
    """The other household members on `on_date`: confirmed facts inside their window."""
    members = []
    for fact in facts:
        if fact.type is not FactType.HOUSEHOLD_MEMBER or fact.status is not FactStatus.CONFIRMED:
            continue
        if fact.valid_from > on_date or (fact.valid_to is not None and fact.valid_to < on_date):
            continue
        if isinstance(fact.value, HouseholdMemberValue):
            members.append(fact.value)
    return members


def _is_young_child(member: HouseholdMemberValue) -> bool:
    return member.role is HouseholdRole.CHILD and member.age is not None and member.age < CHILD_AGE


def household_scale(facts: Iterable[LifeFact], on_date: date) -> Decimal:
    """OECD-modified scale: 1 (the user) + 0.5 per other person 14+ + 0.3 per child under 14."""
    scale = Decimal(1)
    for member in _household_members(facts, on_date):
        scale += _CHILD_WEIGHT if _is_young_child(member) else _ADULT_WEIGHT
    return scale


def children_count(facts: Iterable[LifeFact], on_date: date) -> int:
    """The children in the household facts on `on_date` (D50's kids multiplier)."""
    members = _household_members(facts, on_date)
    return sum(1 for member in members if member.role is HouseholdRole.CHILD)


def city_index(priors: Mapping[str, Any], city: str | None) -> Decimal:
    """The city's price index from priors.json; an unknown or missing city → the default."""
    default = Decimal(str(priors.get("default_city_index", 1)))
    if not city:
        return default
    wanted = fold(city).strip()
    for entry in priors.get("cities", ()):
        if any(fold(name) == wanted for name in entry["names"]) or entry["id"] == wanted:
            return Decimal(str(entry["index"]))
    return default


def multiplier_for(category: Category, scale: Decimal, children: int) -> Decimal:
    """What the single-adult prior of `category` is multiplied with (before the city index)."""
    if category is Category.KIDS:
        return Decimal(children)  # D50: per child, 0 children → 0
    return scale if category in HOUSEHOLD_SCALED_CATEGORIES else Decimal(1)


def clean_history(txs: Iterable[TxView], today: date) -> list[TxView]:
    """Debits of the last 180 days (inclusive) that describe the user's own normal spending."""
    since = today - timedelta(days=HISTORY_DAYS)
    return [
        tx
        for tx in txs
        if tx.direction is Direction.DEBIT
        and tx.category is not None
        and since <= tx.occurred_at.date() <= today
        and tx.effective_amount > 0
        and tx.purpose is not Purpose.PLANNED_EVENT
        and tx.beneficiary is not Beneficiary.OTHERS
        and tx.pot_id is None
    ]


def _median(values: Sequence[Decimal]) -> Decimal:
    return Decimal(statistics.median(values)) if values else Decimal(0)


def effective_mad(baseline: Baseline) -> Decimal:
    """The baseline's MAD, or 0.25 x the expected median when the history has none."""
    if baseline.personal_mad > 0:
        return baseline.personal_mad
    return baseline.expected_median * MAD_FALLBACK


def compute_baselines(
    txs: Iterable[TxView],
    priors: Mapping[str, Any],
    scale: Decimal,
    city: str | None,
    today: date,
    *,
    children: int = 0,
) -> dict[Category, Baseline]:
    """One baseline per category with a prior or with history (arch 5.3.5, D50, D51)."""
    amounts: dict[Category, list[Decimal]] = defaultdict(list)
    for tx in clean_history(txs, today):
        if tx.category is not None:  # always: clean_history drops the uncategorised
            amounts[tx.category].append(tx.effective_amount)
    prior_rows: Mapping[str, Mapping[str, Any]] = priors.get("categories", {})
    index = city_index(priors, city)
    out: dict[Category, Baseline] = {}
    for category in Category:
        history = sorted(amounts.get(category, []))
        row = prior_rows.get(category.value)
        if category is Category.KIDS and children == 0:
            row = None  # D50: no children → no kids prior (only the person's own history)
        if row is None and not history:
            continue
        n = len(history)
        median = _median(history)
        mad = _median([abs(x - median) for x in history])
        multiplier = multiplier_for(category, scale, children) if row is not None else Decimal(1)
        if row is None:  # D51: no prior (rent, utilities, …) → the person's own history only
            prior_median = prior_monthly = Decimal(0)
            expected = median
            monthly = sum(history, Decimal(0)) / _MONTHS_IN_HISTORY
        else:
            prior_median = Decimal(str(row["basket_median"])) * multiplier * index
            prior_monthly = Decimal(str(row["monthly_mean"])) * multiplier * index
            expected = (n * median + BLEND_K * prior_median) / (n + BLEND_K)
            personal_monthly = sum(history, Decimal(0)) / _MONTHS_IN_HISTORY
            monthly = (n * personal_monthly + BLEND_K * prior_monthly) / (n + BLEND_K)
        out[category] = Baseline(
            category=category,
            personal_median=to_money(median),
            personal_mad=to_money(mad),
            n=n,
            prior_median=to_money(prior_median),
            household_multiplier=multiplier,
            expected_median=to_money(expected),
            monthly_expected=to_money(monthly),
        )
    return out
