"""C5: how well the person's life explains one transaction (arch 5.3.4 step 3), pure.

For every active `explains` signature s:
    match = 0.35·category + 0.20·merchant + 0.20·item + 0.15·amount_in_range + 0.10·time
        item: 1 when an item/description keyword matches (case- and diacritics-insensitive)
        amount_in_range: 1 inside [min, max], decaying linearly to 0 at 2x outside it
        time: 1 with no constraint, else 1 only inside the window (weekdays, hours, months)
        (no category, merchant or item match → 0: amount and time alone explain nothing)
    saturation = min(1, days since the last similar purchase / s.replacement_cycle_days)
        similar = same category and (a keyword match or an amount within ±30%); 1 if none
    fit = match · s.strength · fact.confidence · saturation
The other sources: `expects_event` (window + category + amount within ±50% of expected, scored
strength · confidence), a partial classify rule (< 0.9: its confidence) and a precedent (a
user-answered transaction at the same merchant, or the same category within ±30%:
0.8 · (1 - |Δ| / amount)). life_fit = the best; ties: higher score, then a confirmed fact over a
hypothesis, then the most recent fact. Pots are C6's hard filter.

The winner carries `explanation_key` + `params`; `explain()` renders them from the RO / EN
templates below. They describe the reading, never judge the purchase.
"""

import re
from collections.abc import Iterable, Mapping
from datetime import timedelta
from decimal import Decimal
from typing import Final

from pydantic import JsonValue

from app.clock import APP_TZ
from app.domain.enums import (
    AnnotationSource,
    Direction,
    FactStatus,
    Language,
    Purpose,
    RuleKind,
    SignatureEffect,
)
from app.domain.models import LifeFact, PatternRule, Signature, TxView
from app.domain.results import FitResult
from app.domain.user_context import UserContext
from app.engine.anomaly import merchant_key
from app.i18n.labels import label
from app.i18n.text import fold

W_CATEGORY: Final = 0.35
W_MERCHANT: Final = 0.20
W_ITEM: Final = 0.20
W_AMOUNT: Final = 0.15
W_TIME: Final = 0.10
PRECEDENT_WEIGHT: Final = 0.8
SIMILAR_AMOUNT: Final = Decimal("0.30")
EVENT_AMOUNT: Final = Decimal("0.50")
AUTO_RULE_CONFIDENCE: Final = 0.9  # a classify rule at ≥ 0.9 is C6's hard filter, not a fit
RULE_AMOUNT_LIMIT: Final = 2  # 5.3.7: a rule doesn't apply above 2x its max amount
_ANSWERED: Final = (AnnotationSource.ANSWER, AnnotationSource.USER_EDIT)

NO_FIT: Final = FitResult(score=0.0, source="none")

FIT_TEMPLATES: Final[Mapping[str, tuple[str, str]]] = {
    "fit.signature": (
        "{purpose}: nu te-am întrebat, pentru că mi-ai spus „{fact}”.",
        "{purpose}: I didn't ask, because you told me “{fact}”.",
    ),
    "fit.expects_event": (
        "{purpose}: era o cheltuială așteptată („{fact}”).",
        "{purpose}: an expected expense (“{fact}”).",
    ),
    "fit.rule": (
        "{label}, ca de obicei.",
        "{label}, as usual.",
    ),
    "fit.precedent": (
        "Seamănă cu ce mi-ai explicat data trecută la {merchant}.",
        "Like what you explained to me last time at {merchant}.",
    ),
}
"""explanation_key → (ro, en). `{purpose}` is the purpose's label (C1)."""


# ── the match terms ──────────────────────────────────────────────────────────────────────────


def _clip01(value: float) -> float:
    return min(1.0, max(0.0, value))


def _texts(tx: TxView) -> list[str]:
    texts = [item.name for item in tx.items or ()]
    if tx.description:
        texts.append(tx.description)
    return [fold(text) for text in texts]


def keyword_match(tx: TxView, keywords: Iterable[str]) -> bool:
    """A keyword appears as a whole word in an item name or the description (folded)."""
    texts = _texts(tx)
    for keyword in keywords:
        pattern = re.compile(rf"(?<!\w){re.escape(fold(keyword).strip())}(?!\w)")
        if any(pattern.search(text) for text in texts):
            return True
    return False


def merchant_match(tx: TxView, hints: Iterable[str]) -> bool:
    names = [fold(name) for name in (tx.merchant, tx.merchant_raw, tx.merchant_id) if name]
    return any(fold(hint).strip() in name for hint in hints for name in names if hint.strip())


def amount_term(amount: Decimal, low: Decimal | None, high: Decimal | None) -> float:
    """1 inside [low, high]; linearly down to 0 at 2x above high or at half of low."""
    if high is not None and amount > high:
        return _clip01(1 - float((amount - high) / high)) if high > 0 else 0.0
    if low is not None and amount < low:
        return _clip01(2 - float(low / amount)) if amount > 0 else 0.0
    return 1.0


def time_term(tx: TxView, signature: Signature) -> float:
    window = signature.time_window
    if window is None:
        return 1.0
    local = tx.occurred_at.astimezone(APP_TZ)
    if window.weekdays and local.isoweekday() not in window.weekdays:
        return 0.0
    if window.months and local.month not in window.months:
        return 0.0
    if window.from_ is None or window.to is None:
        return 1.0
    return 1.0 if window.from_ <= local.time().replace(tzinfo=None) < window.to else 0.0


def match_score(tx: TxView, signature: Signature) -> float:
    category = 1.0 if signature.category is not None and signature.category == tx.category else 0.0
    merchant = 1.0 if merchant_match(tx, signature.merchant_hints) else 0.0
    item = 1.0 if keyword_match(tx, signature.item_keywords) else 0.0
    if category == merchant == item == 0:
        return 0.0  # the signature is about something else: amount and time alone never fit
    amount = amount_term(tx.amount, signature.amount_min, signature.amount_max)
    return (
        W_CATEGORY * category
        + W_MERCHANT * merchant
        + W_ITEM * item
        + W_AMOUNT * amount
        + W_TIME * time_term(tx, signature)
    )


def saturation(tx: TxView, signature: Signature, history: Iterable[TxView]) -> float:
    """min(1, days since the last similar purchase / cycle); 1 with no cycle or no purchase."""
    cycle = signature.replacement_cycle_days
    if cycle is None:
        return 1.0
    days: int | None = None
    for past in history:
        if past.id == tx.id or past.category != tx.category or past.occurred_at >= tx.occurred_at:
            continue
        close = abs(past.amount - tx.amount) <= SIMILAR_AMOUNT * tx.amount
        if not (close or keyword_match(past, signature.item_keywords)):
            continue
        gap = (tx.occurred_at.date() - past.occurred_at.date()).days
        days = gap if days is None else min(days, gap)
    return 1.0 if days is None else min(1.0, days / cycle)


# ── rules ────────────────────────────────────────────────────────────────────────────────────


def rule_matches(rule: PatternRule, tx: TxView) -> bool:
    """Minimal C8 `rule_matches` (C6 needs it now): merchant, category, amount (≤ 2x max) and
    the weekday / hour window, in Bucharest time."""
    match = rule.match
    if not rule.active:
        return False
    if match.merchant_id is not None and match.merchant_id != tx.merchant_id:
        return False
    if match.category is not None and match.category != tx.category:
        return False
    if match.amount_min is not None and tx.amount < match.amount_min:
        return False
    if match.amount_max is not None and tx.amount > RULE_AMOUNT_LIMIT * match.amount_max:
        return False
    local = tx.occurred_at.astimezone(APP_TZ)
    if match.weekdays and local.isoweekday() not in match.weekdays:
        return False
    if match.from_ is not None and match.to is not None:
        return match.from_ <= local.time().replace(tzinfo=None) < match.to
    return True


def best_rule(rules: Iterable[PatternRule], tx: TxView, kind: RuleKind) -> PatternRule | None:
    matching = [r for r in rules if r.kind is kind and rule_matches(r, tx)]
    return max(matching, key=lambda r: (r.confidence, r.id or 0), default=None)


# ── the sources ──────────────────────────────────────────────────────────────────────────────

_Ranked = tuple[float, int, float, FitResult]  # score, confirmed (1/0), fact recency, result


def _facts_by_id(ctx: UserContext) -> dict[int, LifeFact]:
    return {f.id: f for f in (*ctx.hypotheses, *ctx.facts)}  # a confirmed fact wins an id clash


def _rank(score: float, fact: LifeFact | None, result: FitResult) -> _Ranked:
    confirmed = 1 if fact is None or fact.status is FactStatus.CONFIRMED else 0
    recency = fact.created_at.timestamp() if fact is not None else 0.0
    return (score, confirmed, recency, result)


def _signature_fits(tx: TxView, ctx: UserContext) -> list[_Ranked]:
    facts = _facts_by_id(ctx)
    out = []
    for signature in ctx.signatures:
        if not signature.active:
            continue
        fact = facts.get(signature.fact_id) if signature.fact_id is not None else None
        if signature.fact_id is not None and fact is None:
            continue  # its fact is no longer active
        confidence = fact.confidence if fact is not None else 1.0
        params: dict[str, JsonValue] = {
            "purpose": signature.purpose.value,
            "fact": fact.text if fact is not None else "",
        }
        if signature.effect is SignatureEffect.EXPLAINS:
            score = (
                match_score(tx, signature)
                * signature.strength
                * confidence
                * saturation(tx, signature, ctx.transactions)
            )
            result = FitResult(
                score=_clip01(score),
                source="signature",
                fact_id=signature.fact_id,
                explanation_key="fit.signature",
                params=params,
            )
        elif signature.effect is SignatureEffect.EXPECTS_EVENT and _expected(tx, signature):
            result = FitResult(
                score=_clip01(signature.strength * confidence),
                source="expects_event",
                fact_id=signature.fact_id,
                explanation_key="fit.expects_event",
                params=params,
            )
        else:
            continue
        out.append(_rank(result.score, fact, result))
    return out


def _expected(tx: TxView, signature: Signature) -> bool:
    if signature.category is None or signature.category != tx.category:
        return False
    expected = signature.expected_amount
    if expected is None or abs(tx.amount - expected) > EVENT_AMOUNT * expected:
        return False
    day = tx.occurred_at.astimezone(APP_TZ).date()
    window = signature.time_window
    if window is not None and window.months:
        return day.month in window.months
    if signature.expected_date is not None:
        return abs(day - signature.expected_date) <= timedelta(days=31)
    return False


def _rule_fit(tx: TxView, ctx: UserContext) -> list[_Ranked]:
    rule = best_rule(ctx.rules, tx, RuleKind.CLASSIFY)
    if rule is None or rule.confidence >= AUTO_RULE_CONFIDENCE:
        return []
    params: dict[str, JsonValue] = {"label": rule.outcome.label or ""}
    if rule.outcome.purpose is not None:
        params["purpose"] = rule.outcome.purpose.value
    result = FitResult(
        score=rule.confidence,
        source="rule",
        rule_id=rule.id,
        explanation_key="fit.rule",
        params=params,
    )
    return [_rank(result.score, None, result)]


def _precedent_fit(tx: TxView, ctx: UserContext) -> list[_Ranked]:
    best: FitResult | None = None
    key = merchant_key(tx)
    for past in ctx.transactions:
        if past.id == tx.id or past.direction is not Direction.DEBIT:
            continue
        if past.annotation_source not in _ANSWERED or past.occurred_at >= tx.occurred_at:
            continue
        delta = abs(past.amount - tx.amount)
        same_merchant = merchant_key(past) == key
        close = past.category == tx.category and delta <= SIMILAR_AMOUNT * tx.amount
        if not (same_merchant or close):
            continue
        score = _clip01(PRECEDENT_WEIGHT * (1 - float(delta / tx.amount)))
        if best is None or score > best.score:
            params: dict[str, JsonValue] = {"merchant": past.merchant or past.merchant_raw}
            if past.purpose is not None:
                params["purpose"] = past.purpose.value
            best = FitResult(
                score=score, source="precedent", explanation_key="fit.precedent", params=params
            )
    return [] if best is None else [_rank(best.score, None, best)]


def life_fit(tx: TxView, ctx: UserContext) -> FitResult:
    """The best explanation the person's life gives for `tx` (score 0 with source "none")."""
    ranked = [
        *_signature_fits(tx, ctx),
        *_rule_fit(tx, ctx),
        *_precedent_fit(tx, ctx),
    ]
    ranked = [r for r in ranked if r[0] > 0]
    if not ranked:
        return NO_FIT
    return max(ranked, key=lambda r: r[:3])[3]


def fit_purpose(fit: FitResult) -> Purpose | None:
    value = fit.params.get("purpose")
    return Purpose(value) if isinstance(value, str) else None


def explain(fit: FitResult, lang: Language | str) -> str | None:
    """The "because" in the user's language, or None when nothing explains the transaction."""
    if fit.explanation_key is None or fit.explanation_key not in FIT_TEMPLATES:
        return None
    ro, en = FIT_TEMPLATES[fit.explanation_key]
    template = ro if Language(lang) is Language.RO else en
    purpose = fit_purpose(fit)
    values = {k: str(v) for k, v in fit.params.items()}
    values["purpose"] = label(purpose, lang) if purpose is not None else ""
    return template.format_map(values)
