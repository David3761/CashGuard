"""C10: hypotheses, guessing a life fact from the transactions (arch 5.3.8, F16), pure.

`infer_hypotheses(ctx, today, rejected)` runs after the seed and weekly. Each detector looks at
the resolved transactions of `ctx` (the last 180 days) and proposes one `life_fact` with
`status=hypothesis`, `source=inferred`; the WS `fact.hypothesis` card asks `question_for(draft)`
("Ai mașină? [Da] [Nu]"). In priority order:

    vehicle  fuel (category fuel or a fuel merchant) in ≥ 3 of the last 4 weeks       → 0.5
    pet      a pet shop in each of the last 3 months (30-day windows)                 → 0.5
    child    a kindergarten payment in each of the last 3 months (age 4, editable)    → 0.5
    runner   sport gear (Decathlon / sport) + a race fee in the last 90 days          → 0.5
    moved    the latest rent payment differs by > 10% from the one before, last 120 d → 0.4

Never: a sensitive type. `health_pharmacy` rows are dropped before any detector runs and only
the types in `INFERABLE_TYPES` can come out, so a weekly pharmacy never becomes a health guess
(arch 4.5). No duplicate: a confirmed fact or an open hypothesis of the same kind blocks it, a
rejected one blocks it for good (F16 "never again"). At most one new hypothesis per run, and none
while 3 are still open (the snapshot shows at most 3, arch 6.5).
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final

from app.clock import APP_TZ
from app.domain.enums import (
    Category,
    Direction,
    FactSource,
    FactStatus,
    FactType,
    HouseholdRole,
    Language,
    Persistence,
)
from app.domain.models import (
    ActivityValue,
    Evidence,
    HouseholdMemberValue,
    HousingValue,
    LifeFactDraft,
    PetValue,
    TxView,
    VehicleValue,
)
from app.domain.user_context import UserContext
from app.i18n.format import format_money_in_sentence
from app.i18n.text import fold

INFERABLE_TYPES: Final = frozenset(
    {FactType.VEHICLE, FactType.PET, FactType.HOUSEHOLD_MEMBER, FactType.ACTIVITY, FactType.HOUSING}
)
SENSITIVE_CATEGORIES: Final = frozenset({Category.HEALTH_PHARMACY})
MAX_OPEN: Final = 3
CONFIDENCE: Final = 0.5
MOVED_CONFIDENCE: Final = 0.4  # a rent change can also be a raise
FUEL_WEEKS: Final = 4
FUEL_MIN_WEEKS: Final = 3
MONTHLY_MONTHS: Final = 3
MONTH_DAYS: Final = 30
RUNNER_DAYS: Final = 90
RENT_DAYS: Final = 120
RENT_CHANGE: Final = Decimal("0.10")
MAX_EVIDENCE: Final = 20
KINDERGARTEN_AGE: Final = 4  # a child needs an age (F2); kindergarten is 3-6, the user corrects it

FUEL_MERCHANTS: Final = frozenset({"petrom", "omv", "mol", "rompetrol", "lukoil", "socar"})
PET_MERCHANTS: Final = frozenset({"animax", "zoomania", "petmart", "maxi_pet"})
SPORT_MERCHANTS: Final = frozenset({"decathlon", "intersport", "hervis", "sportisimo"})
KINDERGARTEN_WORDS: Final = ("gradinita", "kindergarten", "after school", "afterschool")
RACE_WORDS: Final = (
    "maraton", "marathon", "semimaraton", "cros", "race", "trail", "taxa participare",
    "taxa inscriere", "inscriere concurs", "alergare", "10k", "5k", "parkrun",
)  # fmt: skip
RUNNING_WORDS: Final = ("alerg", "running", "runner", "maraton", "marathon", "jogging")

QUESTIONS: Final[Mapping[str, tuple[str, str]]] = {
    "vehicle": ("Ai mașină?", "Do you have a car?"),
    "pet": ("Ai un animal de companie?", "Do you have a pet?"),
    "child": ("Ai un copil la grădiniță?", "Do you have a child in kindergarten?"),
    "runner": ("Alergi la concursuri?", "Do you run races?"),
    "moved": (
        "Te-ai mutat? Chiria pare să fie acum {amount}.",
        "Did you move? Your rent seems to be {amount} now.",
    ),
}
"""kind → the 1-tap card's question (ro, en)."""

STATEMENTS: Final[Mapping[str, tuple[str, str]]] = {
    "vehicle": ("Am mașină", "I have a car"),
    "pet": ("Am un animal de companie", "I have a pet"),
    "child": ("Am un copil la grădiniță", "I have a child in kindergarten"),
    "runner": ("Alerg la concursuri", "I run races"),
    "moved": ("M-am mutat, chiria e acum {amount}", "I moved, my rent is {amount} now"),
}
"""kind → the fact's `text` once confirmed, in the user's words (ro, en)."""


@dataclass(frozen=True, slots=True)
class _Found:
    kind: str
    draft_type: FactType
    value: VehicleValue | PetValue | HouseholdMemberValue | ActivityValue | HousingValue
    evidence: tuple[TxView, ...]
    confidence: float = CONFIDENCE
    valid_from: date | None = None
    amount: Decimal | None = None


# ── reading the transactions ─────────────────────────────────────────────────────────────────


def _day(tx: TxView) -> date:
    return tx.occurred_at.astimezone(APP_TZ).date()


def _texts(tx: TxView) -> str:
    parts = [tx.merchant_raw, tx.merchant or "", tx.description or ""]
    parts += [item.name for item in tx.items or ()]
    return " ".join(fold(p) for p in parts)


def _has_word(tx: TxView, words: Iterable[str]) -> bool:
    text = _texts(tx)
    return any(word in text for word in words)


def _usable(ctx: UserContext, today: date) -> list[TxView]:
    """The debits up to `today`, with every sensitive row removed first."""
    return [
        tx
        for tx in ctx.transactions
        if tx.direction is Direction.DEBIT
        and tx.category not in SENSITIVE_CATEGORIES
        and _day(tx) <= today
    ]


def _windows(txs: Sequence[TxView], today: date, size: int, count: int) -> list[list[TxView]]:
    """`count` back-to-back windows of `size` days ending on `today`: the newest first."""
    out: list[list[TxView]] = [[] for _ in range(count)]
    for tx in txs:
        index = (today - _day(tx)).days // size
        if 0 <= index < count:
            out[index].append(tx)
    return out


def _evidence(txs: Iterable[TxView]) -> tuple[TxView, ...]:
    return tuple(sorted(txs, key=lambda t: t.occurred_at, reverse=True)[:MAX_EVIDENCE])


# ── the detectors ────────────────────────────────────────────────────────────────────────────


def _vehicle(txs: Sequence[TxView], today: date) -> _Found | None:
    fuel = [t for t in txs if t.category is Category.FUEL or t.merchant_id in FUEL_MERCHANTS]
    weeks = _windows(fuel, today, 7, FUEL_WEEKS)
    if sum(1 for week in weeks if week) < FUEL_MIN_WEEKS:
        return None
    hits = [t for week in weeks for t in week]
    return _Found("vehicle", FactType.VEHICLE, VehicleValue(kind="car"), _evidence(hits))


def _monthly(txs: Sequence[TxView], today: date, match: Callable[[TxView], bool]) -> list[TxView]:
    months = _windows([t for t in txs if match(t)], today, MONTH_DAYS, MONTHLY_MONTHS)
    return [t for month in months for t in month] if all(months) else []


def _pet(txs: Sequence[TxView], today: date) -> _Found | None:
    hits = _monthly(
        txs, today, lambda t: t.category is Category.PETS or t.merchant_id in PET_MERCHANTS
    )
    if not hits:
        return None
    return _Found("pet", FactType.PET, PetValue(species="pet"), _evidence(hits))


def _child(txs: Sequence[TxView], today: date) -> _Found | None:
    hits = _monthly(txs, today, lambda t: _has_word(t, KINDERGARTEN_WORDS))
    if not hits:
        return None
    value = HouseholdMemberValue(role=HouseholdRole.CHILD, age=KINDERGARTEN_AGE, relation="child")
    return _Found("child", FactType.HOUSEHOLD_MEMBER, value, _evidence(hits))


def _runner(txs: Sequence[TxView], today: date) -> _Found | None:
    recent = [t for t in txs if (today - _day(t)).days < RUNNER_DAYS]
    gear = [t for t in recent if t.merchant_id in SPORT_MERCHANTS or _has_word(t, ("decathlon",))]
    races = [t for t in recent if _has_word(t, RACE_WORDS)]
    if not gear or not races:
        return None
    value = ActivityValue(name="running")
    return _Found("runner", FactType.ACTIVITY, value, _evidence([*gear, *races]))


def _moved(txs: Sequence[TxView], today: date) -> _Found | None:
    rents = sorted(
        (
            t
            for t in txs
            if t.category is Category.HOUSING_RENT and (today - _day(t)).days < RENT_DAYS
        ),
        key=lambda t: t.occurred_at,
    )
    if len(rents) < 2:
        return None
    before, latest = rents[-2], rents[-1]
    if abs(latest.amount - before.amount) <= RENT_CHANGE * before.amount:
        return None
    value = HousingValue(kind="rent", note=f"rent {before.amount} → {latest.amount}")
    return _Found(
        "moved",
        FactType.HOUSING,
        value,
        (latest, before),
        confidence=MOVED_CONFIDENCE,
        valid_from=_day(latest),
        amount=latest.amount,
    )


DETECTORS: Final = (_vehicle, _pet, _child, _runner, _moved)


# ── dedupe: confirmed, open and rejected facts ───────────────────────────────────────────────


def _kind_of(draft: LifeFactDraft) -> str | None:
    """Which detector a fact (confirmed, open or rejected) blocks; None: blocks nothing."""
    value = draft.value
    if draft.type is FactType.VEHICLE:
        return "vehicle"
    if draft.type is FactType.PET:
        return "pet"
    if isinstance(value, HouseholdMemberValue) and value.role is HouseholdRole.CHILD:
        return "child"
    if isinstance(value, ActivityValue) and any(w in fold(value.name) for w in RUNNING_WORDS):
        return "runner"
    if draft.type is FactType.HOUSING:
        return "moved"
    return None


def _blocked(found: _Found, known: Iterable[LifeFactDraft]) -> bool:
    for fact in known:
        if _kind_of(fact) != found.kind:
            continue
        if found.kind != "moved":
            return True
        # a housing fact blocks "moved?" only if it's about this change (told or asked since)
        if found.valid_from is not None and fact.valid_from >= found.valid_from:
            return True
    return False


# ── the entry point ──────────────────────────────────────────────────────────────────────────


def _draft(found: _Found, today: date, lang: Language) -> LifeFactDraft:
    return LifeFactDraft(
        type=found.draft_type,
        value=found.value,
        text=_render(STATEMENTS, found.kind, lang, found.amount),
        source=FactSource.INFERRED,
        status=FactStatus.HYPOTHESIS,
        confidence=found.confidence,
        persistence=Persistence.PERMANENT,
        valid_from=found.valid_from or today,
        evidence=Evidence(transaction_ids=tuple(t.id for t in found.evidence)),
    )


def _render(
    table: Mapping[str, tuple[str, str]], kind: str, lang: Language, amount: Decimal | None
) -> str:
    ro, en = table[kind]
    template = ro if lang is Language.RO else en
    money = format_money_in_sentence(amount, lang.value) if amount is not None else ""
    return template.format_map({"amount": money})


def infer_hypotheses(
    ctx: UserContext, today: date, rejected: Iterable[LifeFactDraft] = ()
) -> list[LifeFactDraft]:
    """At most one new hypothesis from `ctx`'s transactions; `rejected` are the user's "Nu"s."""
    if len(ctx.hypotheses) >= MAX_OPEN:
        return []
    known = [*ctx.facts, *ctx.hypotheses, *rejected]
    txs = _usable(ctx, today)
    for detect in DETECTORS:
        found = detect(txs, today)
        if found is None or found.draft_type not in INFERABLE_TYPES or _blocked(found, known):
            continue
        return [_draft(found, today, ctx.profile.language)]
    return []


def hypothesis_kind(draft: LifeFactDraft) -> str | None:
    """The detector kind of a hypothesis (for its question), None for any other fact."""
    return _kind_of(draft)


def question_for(draft: LifeFactDraft, lang: Language | str) -> str | None:
    """The 1-tap card's question for an inferred hypothesis, in `lang` (None: not one of ours)."""
    kind = _kind_of(draft)
    if kind is None:
        return None
    amount = None
    if kind == "moved" and isinstance(draft.value, HousingValue) and draft.value.note:
        amount = Decimal(draft.value.note.rsplit(" ", 1)[-1])
    return _render(QUESTIONS, kind, Language(lang), amount)
