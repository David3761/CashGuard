"""C12: the mock savings products ranked for one person (arch 6.6 `suggest_savings_products`, 16.5).

"Compare financial products using customer context" (the challenge slide): the same three mock
products, ranked by what this person's life needs. Pure: the inputs are the goal (horizon + a set
amount), the income (stable or irregular) and the facts; nothing is read or written here.

The rules, first match wins for the top product (WB C12):
    1. irregular income (an `income_pattern` fact with irregular, or a freelancer) → liquidity
       first: the flexible pot (instant), then the rest by liquidity
    2. no active goal (no horizon)                                → the flexible pot
    3. horizon < 3 months                                         → the flexible pot
    4. horizon ≥ 6 months, a set goal amount and a stable income  → the term deposit
    5. otherwise (3-5 months, or ≥ 6 months without a stable income) → the savings account
The horizon is whole calendar months from `today` to the goal deadline (15 Jun → 14 Sep is 2,
→ 15 Sep is 3). Below the top product: in liquidity-first mode by liquidity, else the products
that fit the horizon first, then the higher rate. Every result is marked mock (16.5).

Each result carries `reason_key` + `params` and `why_for_you` in RO and EN: descriptive, never a
judgment, checked against A5's banned list by the tests.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Final

from app.domain.enums import FactType, Language, Liquidity, ProductKind
from app.domain.models import Goal, IncomeSource, LifeFact, Product
from app.domain.user_context import UserContext
from app.i18n.format import format_pct

SHORT_MONTHS: Final = 3  # below: the flexible pot
LOCK_MONTHS: Final = 6  # from here, with a set amount and a stable income: the term deposit
IRREGULAR_EMPLOYMENT: Final = frozenset({"freelancer", "self_employed", "pfa", "gig"})
LIQUIDITY_ORDER: Final[Mapping[Liquidity, int]] = {
    Liquidity.INSTANT: 0,
    Liquidity.NOTICE: 1,
    Liquidity.LOCKED: 2,
}
KIND_BY_LIQUIDITY: Final[Mapping[Liquidity, ProductKind]] = {
    Liquidity.INSTANT: ProductKind.FLEXIBLE_POT,
    Liquidity.NOTICE: ProductKind.SAVINGS_ACCOUNT,
    Liquidity.LOCKED: ProductKind.TERM_DEPOSIT,
}
TOP_SCORE: Final = 0.9
FIT_SCORE: Final = 0.6
REACHABLE_SCORE: Final = 0.35
UNSURE_LOCK_SCORE: Final = 0.25  # a lock-in while the income is still unknown
POOR_SCORE: Final = 0.1

REASONS: Final[Mapping[str, tuple[str, str]]] = {
    # the top product
    "top.irregular_income": (
        "Venitul tău variază de la o lună la alta, așa că e bine ca economiile să fie la "
        "îndemână: le poți retrage oricând, fără penalizare ({rate} pe an).",
        "Your income changes from month to month, so it helps to keep your savings within "
        "reach: you can take them out any time, with no penalty ({rate} a year).",
    ),
    "top.no_horizon": (
        "Obiectivul tău nu are încă un termen: aici banii rămân disponibili oricând, până "
        "stabilim data ({rate} pe an).",
        "Your goal has no deadline yet: here the money stays available any time until we set "
        "a date ({rate} a year).",
    ),
    "top.short_horizon": (
        "Până la termen ai {months}, așa că banii trebuie să fie disponibili oricând: îi poți "
        "retrage fără penalizare ({rate} pe an).",
        "Your deadline is {months} away, so the money should be available any time: you can "
        "take it out with no penalty ({rate} a year).",
    ),
    "top.locked_fits": (
        "Ai un venit stabil și {months} până la termen: poți bloca suma pentru {lock} la cea "
        "mai bună dobândă ({rate} pe an).",
        "Your income is steady and your deadline is {months} away: you can lock the money for "
        "{lock} at the best rate ({rate} a year).",
    ),
    "top.medium_horizon": (
        "Până la termen ai {months}: contul de economii are o dobândă mai bună ({rate} pe an) "
        "și banii rămân accesibili cu un scurt preaviz.",
        "Your deadline is {months} away: a savings account pays a better rate ({rate} a year) "
        "and the money stays reachable with short notice.",
    ),
    "top.no_steady_income": (
        "Până la termen ai {months}, dar încă nu știu cât de stabil e venitul tău: contul de "
        "economii are o dobândă bună ({rate} pe an) fără să blocheze banii.",
        "Your deadline is {months} away, but I don't know yet how steady your income is: a "
        "savings account pays a good rate ({rate} a year) without locking the money.",
    ),
    # the others
    "alt.fits": (
        "Se potrivește și cu termenul tău ({months}), cu {rate} pe an.",
        "Also fits your deadline ({months} away), at {rate} a year.",
    ),
    "alt.instant": (
        "Banii sunt disponibili oricând, cu o dobândă mai mică ({rate} pe an).",
        "The money is available any time, at a lower rate ({rate} a year).",
    ),
    "alt.notice": (
        "Dobândă mai bună ({rate} pe an), cu un scurt preaviz la retragere.",
        "A better rate ({rate} a year), with short notice to withdraw.",
    ),
    "alt.too_long": (
        "E gândit pentru cel puțin {lock}, mai mult decât timpul până la termen ({months}).",
        "It's made for at least {lock}, longer than the time to your deadline ({months}).",
    ),
    "alt.locked_irregular": (
        "Blochează banii pentru {lock}: cu un venit care variază, e mai sigur să-i ai la îndemână.",
        "Locks the money for {lock}: with an income that changes, it's safer to keep it within "
        "reach.",
    ),
    "alt.locked_no_goal": (
        "Blochează banii pentru {lock}: are sens după ce stabilim termenul obiectivului.",
        "Locks the money for {lock}: it makes sense once we set your goal's deadline.",
    ),
    "alt.no_steady_income": (
        "Blochează banii pentru {lock}: are sens când venitul tău e stabil.",
        "Locks the money for {lock}: it makes sense once your income is steady.",
    ),
}
"""reason_key → (ro, en). `{months}` / `{lock}` are month phrases, `{rate}` a percent."""


@dataclass(frozen=True, slots=True)
class ProductNeeds:
    """What the ranking reads about the person (pure input, built from a context or services)."""

    horizon_months: int | None  # None: no active goal
    set_amount: bool  # the goal has a fixed target amount
    stable_income: bool
    irregular_income: bool


@dataclass(frozen=True, slots=True)
class ProductOffer:
    """One mock product, from F2's `Product` or a `products` row / data/products.json item."""

    id: int | str
    name: str
    kind: ProductKind
    rate: Decimal
    liquidity: Liquidity
    min_months: int
    max_months: int
    mock: bool = True

    def fits(self, months: int) -> bool:
        """`months` is inside the product's horizon (past the max still fits: nothing longer)."""
        return self.min_months <= months


@dataclass(frozen=True, slots=True)
class RankedProduct:
    """A product ranked for this person: higher `score` first, the reason in RO and EN."""

    product: ProductOffer
    score: float
    reason_key: str
    params: Mapping[str, Any]
    why_for_you: Mapping[Language, str]
    fits: bool
    mock: bool = field(default=True)  # every product is a mock one (16.5), whatever the row says

    def why(self, lang: Language | str) -> str:
        return self.why_for_you[Language(lang)]


# ── inputs ───────────────────────────────────────────────────────────────────────────────────


def months_between(today: date, deadline: date) -> int:
    """Whole calendar months from `today` to `deadline` (0 when it's past or under a month)."""
    months = (deadline.year - today.year) * 12 + deadline.month - today.month
    if deadline.day < today.day:
        months -= 1
    return max(0, months)


def _fact_value(fact: LifeFact) -> Mapping[str, Any]:
    dumped: Mapping[str, Any] = fact.value.model_dump()
    return dumped


def needs_from(
    goal: Goal | None,
    income_sources: Iterable[IncomeSource | Mapping[str, Any]],
    facts: Iterable[LifeFact],
    today: date,
) -> ProductNeeds:
    """The needs from the goal, the income sources and the confirmed facts."""
    irregular = regular_said = False
    for fact in facts:
        value = _fact_value(fact)
        if fact.type is FactType.INCOME_PATTERN:
            irregular |= bool(value.get("irregular"))
            regular_said |= value.get("irregular") is False
        elif fact.type is FactType.EMPLOYMENT:
            irregular |= str(value.get("kind", "")).strip().lower() in IRREGULAR_EMPLOYMENT
    has_income = any(True for _ in income_sources)
    return ProductNeeds(
        horizon_months=None if goal is None else months_between(today, goal.deadline),
        set_amount=goal is not None and goal.amount > 0,
        stable_income=not irregular and (has_income or regular_said),
        irregular_income=irregular,
    )


def needs_for(ctx: UserContext, today: date) -> ProductNeeds:
    return needs_from(ctx.goal, ctx.income_sources, ctx.facts, today)


def as_offer(product: Product | ProductOffer | Mapping[str, Any]) -> ProductOffer:
    """A `ProductOffer` from a model or a row; a row without `kind` gets it from its liquidity."""
    if isinstance(product, ProductOffer):
        return product
    row: Mapping[str, Any] = product.model_dump() if isinstance(product, Product) else product
    liquidity = Liquidity(row["liquidity"])
    kind = row.get("kind")
    return ProductOffer(
        id=row["id"],
        name=str(row.get("name") or row["id"]),
        kind=ProductKind(kind) if kind else KIND_BY_LIQUIDITY[liquidity],
        rate=Decimal(str(row.get("rate", 0))),
        liquidity=liquidity,
        min_months=int(row.get("min_months", 0)),
        max_months=int(row.get("max_months", 0)),
        mock=bool(row.get("mock", True)),
    )


# ── texts ────────────────────────────────────────────────────────────────────────────────────


def months_phrase(months: int | None, lang: Language) -> str:
    """ "3 luni" / "o lună" / "20 de luni" / "sub o lună"; EN "3 months" / "1 month"."""
    if months is None:
        return ""
    if lang is Language.RO:
        if months == 0:
            return "sub o lună"
        if months == 1:
            return "o lună"
        return f"{months} de luni" if months >= 20 else f"{months} luni"
    if months == 0:
        return "less than a month"
    return "1 month" if months == 1 else f"{months} months"


def render(key: str, params: Mapping[str, Any], lang: Language) -> str:
    ro, en = REASONS[key]
    values = {
        "months": months_phrase(params.get("months"), lang),
        "lock": months_phrase(params.get("lock_months"), lang),
        "rate": format_pct(Decimal(str(params.get("rate", 0))), lang.value, decimals=1),
    }
    return (ro if lang is Language.RO else en).format_map(values)


# ── the ranking ──────────────────────────────────────────────────────────────────────────────


def _top_kind(needs: ProductNeeds, offers: Sequence[ProductOffer]) -> tuple[ProductKind, str]:
    months = needs.horizon_months
    if needs.irregular_income:
        return ProductKind.FLEXIBLE_POT, "top.irregular_income"
    if months is None:
        return ProductKind.FLEXIBLE_POT, "top.no_horizon"
    if months < SHORT_MONTHS:
        return ProductKind.FLEXIBLE_POT, "top.short_horizon"
    deposit_fits = any(o.kind is ProductKind.TERM_DEPOSIT and o.fits(months) for o in offers)
    if months >= LOCK_MONTHS and needs.set_amount and needs.stable_income and deposit_fits:
        return ProductKind.TERM_DEPOSIT, "top.locked_fits"
    if months >= LOCK_MONTHS and not needs.stable_income:
        return ProductKind.SAVINGS_ACCOUNT, "top.no_steady_income"
    return ProductKind.SAVINGS_ACCOUNT, "top.medium_horizon"


def _liquidity_first(needs: ProductNeeds) -> bool:
    months = needs.horizon_months
    return needs.irregular_income or months is None or months < SHORT_MONTHS


def _alternative(offer: ProductOffer, needs: ProductNeeds) -> tuple[str, float]:
    months = needs.horizon_months
    locked = offer.liquidity is Liquidity.LOCKED
    if locked and needs.irregular_income:
        return "alt.locked_irregular", POOR_SCORE
    if locked and months is None:
        return "alt.locked_no_goal", POOR_SCORE
    if months is not None and not offer.fits(months):
        return "alt.too_long", POOR_SCORE
    if locked and not needs.stable_income:
        return "alt.no_steady_income", UNSURE_LOCK_SCORE
    if offer.liquidity is Liquidity.INSTANT:
        return "alt.instant", REACHABLE_SCORE
    if _liquidity_first(needs) or months is None:
        return "alt.notice", REACHABLE_SCORE
    return "alt.fits", FIT_SCORE


def _order_key(offer: ProductOffer, needs: ProductNeeds) -> tuple[int, Decimal, str]:
    if _liquidity_first(needs):
        return (LIQUIDITY_ORDER[offer.liquidity], -offer.rate, str(offer.id))
    return (0, -offer.rate, str(offer.id))


def rank_offers(needs: ProductNeeds, products: Iterable[Any]) -> list[RankedProduct]:
    """`products` (models, rows or offers) ranked for `needs`: the best first."""
    offers = [as_offer(p) for p in products]
    top_kind, top_key = _top_kind(needs, offers)
    top = min(
        (o for o in offers if o.kind is top_kind),
        key=lambda o: (-o.rate, str(o.id)),
        default=None,
    )
    ranked: list[tuple[float, tuple[int, Decimal, str], RankedProduct]] = []
    for offer in offers:
        key, score = (top_key, TOP_SCORE) if offer is top else _alternative(offer, needs)
        params: dict[str, Any] = {
            "rate": float(offer.rate),
            "lock_months": offer.min_months,
            "min_months": offer.min_months,
            "max_months": offer.max_months,
        }
        if needs.horizon_months is not None:
            params["months"] = needs.horizon_months
        months = needs.horizon_months
        item = RankedProduct(
            product=offer,
            score=score,
            reason_key=key,
            params=params,
            why_for_you={lang: render(key, params, lang) for lang in Language},
            fits=offer is top or (months is not None and offer.fits(months)),
        )
        ranked.append((score, _order_key(offer, needs), item))
    ranked.sort(key=lambda r: (-r[0], r[1]))
    return [item for _, _, item in ranked]


def rank_products(ctx: UserContext, products: Iterable[Any], today: date) -> list[RankedProduct]:
    """C12's core: `products` ranked for the person in `ctx` on `today`."""
    return rank_offers(needs_for(ctx, today), products)
