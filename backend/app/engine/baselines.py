"""Household scale and context-adjusted baselines (arch 5.3.5, E6). Pure, no DB, no clock.

Household scale (OECD-modified): the user is the first adult (1.0); `household_member` facts list
the *other* people, each 0.5 if 14 or older, 0.3 if a child under 14. Pets are a separate fact type.

Baselines: per category, the personal median + MAD of effective amounts over the last 180 days
(bound inclusive, Bucharest days), blended with the prior: (n·personal + 5·prior) / (n + 5).
Priors come from `data/priors.json` (C1, H-9), read strictly:
- household categories (`HOUSEHOLD_SCALED_CATEGORIES`, arch 4.5): prior x household scale x city
index;
- `kids` (D50): the monthly prior x the number of children x city index, the basket per transaction
  (x city index only); no children → no kids prior (only the person's own history);
- D51: the file has no prior for fixed-cost categories (rent, utilities, …): history only;
- the other categories: the prior as is (the city index applies only to household categories).

Integration (danutu's E6 + David G.'s C5 minimum): danutu's structure and history window; our
priors file shape, D50, the strict loader, `children_count` / `effective_mad` / `city_index`.
"""

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import NotRequired, TypedDict, cast
from zoneinfo import ZoneInfo

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
from app.domain.money import parse_json, to_money
from app.engine.calendar import days_in_month
from app.engine.stats import blend, median_and_mad, monthly_rate
from app.i18n.text import fold


class CategoryPrior(TypedDict):
    """One category of `data/priors.json`: single adult, lei."""

    monthly_mean: Decimal
    basket_median: Decimal
    basket_cv: NotRequired[Decimal]
    cv: NotRequired[Decimal]


class CityEntry(TypedDict):
    id: str
    names: list[str]
    index: Decimal


class Priors(TypedDict):
    """Shape of `data/priors.json` (C1): single-adult priors per category + city indices."""

    categories: dict[str, CategoryPrior]
    cities: NotRequired[list[CityEntry]]
    city_ignored_words: NotRequired[list[str]]
    default_city_index: NotRequired[Decimal]


PRIORS_PATH = Path(__file__).resolve().parents[2] / "data" / "priors.json"

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
HOUSEHOLD_SCALED = frozenset(HOUSEHOLD_SCALED_CATEGORIES)
# variable essentials only: rent and utilities are fixed costs and already left out of the daily
# budget
ESSENTIAL = frozenset(
    {Category.GROCERIES, Category.TRANSPORT, Category.HEALTH_PHARMACY, Category.HOUSEHOLD_GOODS}
)
NOT_SPENDING = frozenset({Category.INCOME, Category.TRANSFERS, Category.SAVINGS})
NOT_ME = frozenset({Beneficiary.OTHERS, Beneficiary.EMPLOYER})


@lru_cache(maxsize=1)
def load_priors() -> Priors:
    """`data/priors.json`, read once and strictly (Decimal numbers, no duplicate keys, H-9)."""
    return cast(Priors, parse_json(PRIORS_PATH.read_bytes()))


# ── household scale ──────────────────────────────────────────────────────────


def is_active(valid_from: date | None, valid_to: date | None, on_date: date) -> bool:
    """True when `on_date` is inside `[valid_from, valid_to]`; a missing bound is open-ended."""
    if valid_from is not None and valid_to is not None and valid_to < valid_from:
        raise ValueError("valid_to must not be before valid_from")
    return (valid_from is None or valid_from <= on_date) and (
        valid_to is None or on_date <= valid_to
    )


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


def _members(facts: Iterable[LifeFact]) -> list[tuple[LifeFact, HouseholdMemberValue]]:
    return [
        (f, f.value)
        for f in facts
        if f.type is FactType.HOUSEHOLD_MEMBER
        and f.status is FactStatus.CONFIRMED
        and isinstance(f.value, HouseholdMemberValue)
    ]


def household_scale(facts: Iterable[LifeFact], on_date: date) -> Decimal:
    """Household scale on `on_date` from the confirmed `household_member` facts (hypotheses don't
    count)."""
    members: list[Member] = [
        (str(v.role), v.age, f.valid_from, f.valid_to) for f, v in _members(facts)
    ]
    return scale_from_members(members, on_date)


def children_count(facts: Iterable[LifeFact], on_date: date) -> int:
    """The children in the confirmed household facts on `on_date` (D50's kids multiplier)."""
    return sum(
        1
        for f, v in _members(facts)
        if v.role is HouseholdRole.CHILD and is_active(f.valid_from, f.valid_to, on_date)
    )


# ── priors ───────────────────────────────────────────────────────────────────


def city_key(name: str, ignored: Iterable[str] = ()) -> str:
    """The city lookup key (H-9): folded words without punctuation, ignored words ("municipiul",
    "romania", "sector"…) and numbers, joined without spaces."""
    skip = set(ignored)
    words = re.split(r"[^0-9a-z]+", fold(name))
    return "".join(w for w in words if w and w not in skip and not w.isdigit())


def city_index(priors: Priors, city: str | None) -> Decimal:
    """The city's price index from priors.json; an unknown or missing city → the default."""
    default = Decimal(str(priors.get("default_city_index", 1)))
    if not city:
        return default
    ignored = priors.get("city_ignored_words", [])
    wanted = city_key(city, ignored)
    if not wanted:
        return default
    for entry in priors.get("cities", []):
        names = [entry["id"], *entry["names"]]
        if wanted in {city_key(n, ignored) for n in names}:
            return Decimal(str(entry["index"]))
    return default


def multiplier_for(category: Category, scale: Decimal, children: int) -> Decimal:
    """What the single-adult monthly prior of `category` is multiplied with (before the city)."""
    if category is Category.KIDS:
        return Decimal(children)  # D50: per child
    return scale if category in HOUSEHOLD_SCALED else Decimal(1)


# ── baselines ────────────────────────────────────────────────────────────────


def _local_date(tx: TxView) -> date:
    return tx.occurred_at.astimezone(BUCHAREST).date()


def counts(tx: TxView) -> bool:
    """Own normal spending only: categorised debits, not pot-funded, not a planned event, not for
    others / the employer, own share > 0."""
    return (
        tx.direction is Direction.DEBIT
        and tx.category is not None
        and tx.category not in NOT_SPENDING
        and tx.purpose is not Purpose.PLANNED_EVENT
        and tx.beneficiary not in NOT_ME
        and tx.pot_id is None
        and tx.effective_amount > 0
    )


def effective_mad(baseline: Baseline) -> Decimal:
    """The baseline's MAD, or 0.25 x the expected median when it has none (stored baselines
    already carry the fallback; this also covers hand-built ones)."""
    if baseline.personal_mad > 0:
        return baseline.personal_mad
    return baseline.expected_median * MAD_FALLBACK_SHARE


def _baseline(
    category: Category,
    amounts: list[Decimal],
    prior: CategoryPrior | None,
    scale: Decimal,
    index: Decimal,
    children: int,
    span_days: int,
) -> Baseline:
    n = len(amounts)
    personal_median, personal_mad = median_and_mad(amounts)
    personal_monthly = monthly_rate(sum(amounts, Decimal(0)), span_days)
    household = category in HOUSEHOLD_SCALED
    city = index if household else Decimal(1)
    multiplier = multiplier_for(category, scale, children) if prior is not None else Decimal(1)
    k = PRIOR_WEIGHT if prior is not None else 0  # no prior → personal history only
    if prior is None:
        prior_median = prior_monthly = Decimal(0)
    elif category is Category.KIDS:  # D50: the month per child, the basket per transaction
        prior_median = Decimal(str(prior["basket_median"])) * city
        prior_monthly = Decimal(str(prior["monthly_mean"])) * multiplier * city
    else:
        prior_median = Decimal(str(prior["basket_median"])) * multiplier * city
        prior_monthly = Decimal(str(prior["monthly_mean"])) * multiplier * city
    expected_median = blend(n, personal_median, prior_median, k) if n + k else Decimal(0)
    mad = personal_mad if personal_mad > 0 else MAD_FALLBACK_SHARE * expected_median
    return Baseline(
        category=category,
        personal_median=to_money(personal_median),
        personal_mad=to_money(mad),
        n=n,
        prior_median=to_money(prior_median),
        household_multiplier=multiplier if multiplier > 0 else Decimal(1),
        expected_median=to_money(expected_median),
        monthly_expected=to_money(
            blend(n, personal_monthly, prior_monthly, k) if n + k else Decimal(0)
        ),
    )


def compute_baselines(
    txs: Iterable[TxView],
    priors: Priors,
    scale: Decimal,
    city: str | None,
    today: date,
    *,
    children: int = 0,
) -> dict[Category, Baseline]:
    """One baseline per spending category seen in the window or present in the priors.

    `children` (D50): the number of children; 0 → no kids prior."""
    since = today - timedelta(days=WINDOW_DAYS)
    window = [t for t in txs if since <= _local_date(t) <= today]
    # the history actually covered (a 4-month seed must not be read as 6 months)
    span_days = (today - min(map(_local_date, window))).days + 1 if window else 0
    amounts: defaultdict[Category, list[Decimal]] = defaultdict(list)
    for t in window:
        if counts(t) and t.category is not None:
            amounts[t.category].append(t.effective_amount)
    index = city_index(priors, city)
    rows: dict[Category, CategoryPrior] = {}
    for name, row in priors["categories"].items():
        category = Category(name)
        if category is Category.KIDS and children <= 0:
            continue  # D50: no children → no kids prior
        rows[category] = row
    categories = (set(amounts) | set(rows)) - NOT_SPENDING
    return {
        c: _baseline(c, amounts.get(c, []), rows.get(c), scale, index, children, span_days)
        for c in sorted(categories)
    }


def essentials_floor(baselines: Mapping[Category, Baseline], month: date) -> Decimal:
    """Per day: Σ monthly_expected of the essential categories / days in `month`'s month."""
    total = sum((b.monthly_expected for c, b in baselines.items() if c in ESSENTIAL), Decimal(0))
    return to_money(total / days_in_month(month.year, month.month))


def rescale(
    baselines: Mapping[Category, Baseline], old_scale: Decimal, new_scale: Decimal
) -> dict[Category, Baseline]:
    """Instant household change: household categories x new/old; others unchanged (arch 5.3.5).
    `kids` scales with the children (D50), not the household scale: it's left unchanged."""
    if old_scale <= 0 or new_scale <= 0:
        raise ValueError("household scales must be > 0")
    ratio = new_scale / old_scale
    return {
        c: b.replace(
            prior_median=to_money(b.prior_median * ratio),
            expected_median=to_money(b.expected_median * ratio),
            monthly_expected=to_money(b.monthly_expected * ratio),
            household_multiplier=new_scale,
        )
        if c in HOUSEHOLD_SCALED and c is not Category.KIDS
        else b
        for c, b in baselines.items()
    }
