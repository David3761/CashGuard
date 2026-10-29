"""C11: the Romanian calendar as expected spending (arch 5.3.3 expects_event, 5.3.9), pure.

`data/calendar.json` (C1) lists fixed dates (8 Martie, 1 Iunie, Crăciun), computed ones (Paște,
Orthodox, by the Meeus Julian algorithm) and configurable ones (school start, Black Friday). An
event counts for a person only when their life makes it relevant: one with `requires_child_age`
(1 Iunie, school start) needs a confirmed child fact with a known age inside that range.

Three outputs over the same rules:
- `expected_events(ctx, today)`: the relevant events of the coming `days_ahead` days (proactive
  check-ins, the plan's "expected events", 5.3.9);
- `event_signatures(ctx, today)`: the same as `expects_event` `Signature`s (origin library, the
  child fact's id or None) that the engine and C5's `_expected` can read;
- `calendar_fit(tx, ctx)`: the `life_fit` source C5 calls for one transaction (`fit.calendar`).

**No double counting (the rule).** C4's library already writes `expects_event` signatures for a
child fact (`child_school`: books in Aug-Sep, `child_1_iunie`: kids in June) and an `explains` one
for a Christmas life event. A calendar item for category c around date d is dropped when any
active signature in the context already covers c in d's month (its `time_window.months` has the
month, or its `expected_date` is in that month), whatever its origin or effect: the library (and
Claude's signatures) win, the calendar fills only the gaps (e.g. gifts on 1 Iunie, clothing for
school start). `life_fit` also takes the single best source, never a sum.

**Only an explaining purpose.** An event explains a category only when it says why: anything for
a child event is `household_care`, gifts are `social_connection`, holiday groceries
`essential_living`. Black Friday's electronics and clothing predict a peak, they don't explain a
purchase, so they never become a signature or a fit (they stay in `expected_events`).
"""

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from functools import cache
from typing import Any, Final

from pydantic import JsonValue

from app.clock import APP_TZ
from app.config import BACKEND_DIR
from app.domain.enums import (
    Category,
    Direction,
    FactType,
    HouseholdRole,
    Language,
    Purpose,
    SignatureEffect,
    SignatureOrigin,
)
from app.domain.models import HouseholdMemberValue, LifeFact, Signature, TxView
from app.domain.money import to_money
from app.domain.results import FitResult
from app.domain.user_context import UserContext

DAYS_AHEAD: Final = 60
STRENGTH: Final = 0.6  # below a confirmed library signature (0.7-0.9): a calendar guess
EVENT_BASKETS: Final = Decimal(2)  # an event's expected amount: about two usual baskets
FIT_AMOUNT_LIMIT: Final = Decimal(3)  # a fit decays above 3x the usual basket (0 at 6x)
EXPLAINING_PURPOSE: Final[Mapping[Category, Purpose]] = {
    Category.GIFTS: Purpose.SOCIAL_CONNECTION,
    Category.GROCERIES: Purpose.ESSENTIAL_LIVING,
}
"""A category's purpose for an event that isn't about a child (a child event: household_care)."""


@dataclass(frozen=True, slots=True)
class CalendarEntry:
    """One `data/calendar.json` item."""

    id: str
    name: Mapping[Language, str]
    categories: tuple[Category, ...]
    lead_days: int
    child_ages: tuple[int, int] | None = None
    month_day: tuple[int, int] | None = None  # fixed
    rule: str | None = None  # computed
    dates: tuple[date, ...] = ()  # configurable

    def dates_in(self, year: int) -> list[date]:
        if self.month_day is not None:
            return [date(year, *self.month_day)]
        if self.rule == "orthodox_easter":
            return [orthodox_easter(year)]
        return [d for d in self.dates if d.year == year]


@dataclass(frozen=True, slots=True)
class ExpectedEvent:
    """A relevant calendar event on `day`; spending for it starts `lead_days` before."""

    id: str
    name: Mapping[Language, str]
    day: date
    starts: date
    categories: tuple[Category, ...]
    fact_id: int | None = None  # the child fact that makes it relevant
    fact_confidence: float = 1.0

    def purpose(self, category: Category) -> Purpose | None:
        if self.fact_id is not None:
            return Purpose.HOUSEHOLD_CARE
        return EXPLAINING_PURPOSE.get(category)


# ── the calendar ─────────────────────────────────────────────────────────────────────────────


def orthodox_easter(year: int) -> date:
    """Orthodox Easter (Gregorian date) by the Meeus Julian algorithm; valid 1900-2099 (+13)."""
    if not 1900 <= year <= 2099:
        raise ValueError(f"orthodox_easter covers 1900-2099, got {year}")
    a, b, c = year % 4, year % 7, year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month, day = divmod(d + e + 114, 31)
    return date(year, month, day + 1) + timedelta(days=13)


def _entry(raw: Mapping[str, Any]) -> CalendarEntry:
    ages = raw.get("requires_child_age")
    return CalendarEntry(
        id=raw["id"],
        name={Language.RO: raw["name"]["ro"], Language.EN: raw["name"]["en"]},
        categories=tuple(Category(c) for c in raw["categories"]),
        lead_days=int(raw["lead_days"]),
        child_ages=(int(ages[0]), int(ages[1])) if ages else None,
        month_day=(int(raw["month"]), int(raw["day"])) if "month" in raw else None,
        rule=raw.get("rule"),
        dates=tuple(date.fromisoformat(d) for d in raw.get("dates", ())),
    )


def parse_calendar(data: Mapping[str, Any]) -> tuple[CalendarEntry, ...]:
    raws = [*data.get("fixed", ()), *data.get("computed", ()), *data.get("configurable", ())]
    return tuple(_entry(raw) for raw in raws)


@cache
def load_calendar() -> tuple[CalendarEntry, ...]:
    """data/calendar.json, read once."""
    return parse_calendar(json.loads((BACKEND_DIR / "data" / "calendar.json").read_text("utf-8")))


@cache
def _prior_baskets() -> Mapping[str, Decimal]:
    raw = json.loads((BACKEND_DIR / "data" / "priors.json").read_text("utf-8"))
    return {c: Decimal(str(v["basket_median"])) for c, v in raw["categories"].items()}


def usual_basket(ctx: UserContext, category: Category) -> Decimal:
    """The person's usual purchase in `category`: their baseline, else the population prior."""
    baseline = ctx.baselines.get(category)
    if baseline is not None and baseline.expected_median > 0:
        return baseline.expected_median
    return _prior_baskets().get(category.value, Decimal(100))


# ── relevance ────────────────────────────────────────────────────────────────────────────────


def _children(ctx: UserContext) -> list[tuple[LifeFact, int]]:
    out = []
    for fact in ctx.facts:
        value = fact.value
        if (
            fact.type is FactType.HOUSEHOLD_MEMBER
            and isinstance(value, HouseholdMemberValue)
            and value.role is HouseholdRole.CHILD
            and value.age is not None
        ):
            out.append((fact, value.age))
    return sorted(out, key=lambda pair: pair[0].id)


def _occurrence(entry: CalendarEntry, day: date, ctx: UserContext) -> ExpectedEvent | None:
    """`entry` on `day` for this person, or None when their life doesn't make it relevant."""
    fact_id, confidence = None, 1.0
    if entry.child_ages is not None:
        low, high = entry.child_ages
        kids = [fact for fact, age in _children(ctx) if low <= age <= high]
        if not kids:
            return None
        fact_id, confidence = kids[0].id, kids[0].confidence
    return ExpectedEvent(
        id=entry.id,
        name=entry.name,
        day=day,
        starts=day - timedelta(days=entry.lead_days),
        categories=entry.categories,
        fact_id=fact_id,
        fact_confidence=confidence,
    )


def _events_between(
    ctx: UserContext, start: date, end: date, entries: Sequence[CalendarEntry]
) -> list[ExpectedEvent]:
    out = []
    for entry in entries:
        for year in range(start.year, end.year + 1):
            for day in entry.dates_in(year):
                if start <= day <= end and (event := _occurrence(entry, day, ctx)) is not None:
                    out.append(event)
    return sorted(out, key=lambda e: (e.day, e.id))


def expected_events(
    ctx: UserContext,
    today: date,
    *,
    days_ahead: int = DAYS_AHEAD,
    entries: Sequence[CalendarEntry] | None = None,
) -> list[ExpectedEvent]:
    """The relevant events from `today` to `today + days_ahead`, the soonest first."""
    calendar = load_calendar() if entries is None else entries
    return _events_between(ctx, today, today + timedelta(days=days_ahead), calendar)


# ── no double counting ───────────────────────────────────────────────────────────────────────


def covered(signatures: Iterable[Signature], category: Category, month: int) -> bool:
    """An active signature already covers `category` in `month` (the library wins)."""
    for signature in signatures:
        if not signature.active or signature.category is not category:
            continue
        window = signature.time_window
        if window is not None and month in window.months:
            return True
        if signature.expected_date is not None and signature.expected_date.month == month:
            return True
    return False


# ── signatures & the life_fit source ─────────────────────────────────────────────────────────


def event_signatures(
    ctx: UserContext,
    today: date,
    *,
    days_ahead: int = DAYS_AHEAD,
    entries: Sequence[CalendarEntry] | None = None,
) -> list[Signature]:
    """`expects_event` signatures for the coming events, minus what a signature already covers."""
    out = []
    for event in expected_events(ctx, today, days_ahead=days_ahead, entries=entries):
        for category in event.categories:
            purpose = event.purpose(category)
            if purpose is None or covered(ctx.signatures, category, event.day.month):
                continue
            out.append(
                Signature(
                    fact_id=event.fact_id,
                    effect=SignatureEffect.EXPECTS_EVENT,
                    category=category,
                    expected_date=event.day,
                    expected_amount=to_money(usual_basket(ctx, category) * EVENT_BASKETS),
                    purpose=purpose,
                    strength=STRENGTH,
                    origin=SignatureOrigin.LIBRARY,
                )
            )
    return out


def _amount_factor(amount: Decimal, limit: Decimal) -> float:
    if amount <= limit:
        return 1.0
    return max(0.0, 1 - float((amount - limit) / limit))


def calendar_fit(
    tx: TxView, ctx: UserContext, entries: Sequence[CalendarEntry] | None = None
) -> FitResult | None:
    """The best calendar event that explains `tx` (its day inside the event's lead window, its
    category one the event explains, not covered by a signature), or None."""
    if tx.direction is not Direction.DEBIT or tx.category is None:
        return None
    day = tx.occurred_at.astimezone(APP_TZ).date()
    calendar = load_calendar() if entries is None else entries
    lead = max((e.lead_days for e in calendar), default=0)
    best: FitResult | None = None
    for event in _events_between(ctx, day, day + timedelta(days=lead), calendar):
        purpose = event.purpose(tx.category)
        if tx.category not in event.categories or purpose is None or day < event.starts:
            continue
        if covered(ctx.signatures, tx.category, event.day.month):
            continue
        limit = usual_basket(ctx, tx.category) * FIT_AMOUNT_LIMIT
        score = STRENGTH * event.fact_confidence * _amount_factor(tx.amount, limit)
        if score <= 0 or (best is not None and score <= best.score):
            continue
        params: dict[str, JsonValue] = {
            "purpose": purpose.value,
            "event": event.id,
            "event_ro": event.name[Language.RO],
            "event_en": event.name[Language.EN],
        }
        best = FitResult(
            score=score,
            source="expects_event",
            fact_id=event.fact_id,
            explanation_key="fit.calendar",
            params=params,
        )
    return best
