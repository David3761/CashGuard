"""C6: evaluate one transaction against the person's life (arch 5.3.4 steps 1-7), pure.

1. normalise (C2): merchant id, category (the script's wins), multi-category flag;
2. hard filters, in order: below max(50 lei, 1% of monthly income) → ignore; credit → auto;
   a recurring bill (a fixed cost within ±10% and ±3 days, bill categories only) → auto,
   essential_living; health_pharmacy → auto, essential_living, never asked; an active event pot
   (its life event's category, before its deadline) → auto, planned_event, pot_id; a classify
   rule at ≥ 0.9 → auto with its outcome;
3. life-fit (C5) · 4. anomaly features (E7) · 5. raw = 0.5·stat + 0.2·novelty + 0.3·materiality,
   unexplained = raw · (1 - life_fit) · (1 - rule_match);
6. decide: raw ≥ 0.5 and life_fit ≥ 0.6 → inform; unexplained ≥ 0.55 → ask; else auto;
   a matching suppress rule turns ask into auto ("nu mai întreba de asta");
7. ask is provisional: effective_amount = amount, purpose unknown.
"""

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any, Final

from pydantic import JsonValue

from app.clock import APP_TZ
from app.context.life_fit import explain, fit_purpose, life_fit
from app.context.normalize import normalize
from app.context.rules import best_rule
from app.domain.enums import (
    AnnotationSource,
    Beneficiary,
    Category,
    Decision,
    Direction,
    Language,
    LifeEventStatus,
    LifeEventType,
    PotKind,
    PotStatus,
    Purpose,
    RuleKind,
)
from app.domain.models import Baseline, PatternRule, Pot, TxView
from app.domain.results import Evaluation, FitResult, QuestionHint
from app.domain.user_context import UserContext
from app.engine.anomaly import anomaly_features
from app.engine.baselines import Priors, children_count, compute_baselines, load_priors
from app.i18n.format import format_money_in_sentence
from app.i18n.labels import label

FLOOR: Final = Decimal(50)
FLOOR_INCOME_SHARE: Final = Decimal("0.01")
BILL_AMOUNT: Final = Decimal("0.10")
BILL_DAYS: Final = 3
AUTO_RULE: Final = 0.9
INFORM_RAW: Final = 0.5
INFORM_FIT: Final = 0.6
ASK_UNEXPLAINED: Final = 0.55
GUESS_CONFIDENCE: Final = 0.4
BILL_CATEGORIES: Final = (
    Category.HOUSING_RENT, Category.UTILITIES, Category.TELECOM, Category.SUBSCRIPTIONS,
    Category.SPORT, Category.EDUCATION, Category.KIDS, Category.TRANSFERS, Category.OTHER,
)  # fmt: skip
ESSENTIAL_CATEGORIES: Final = (
    Category.GROCERIES, Category.TRANSPORT, Category.FUEL, Category.HEALTH_PHARMACY,
    Category.HOUSING_RENT, Category.UTILITIES, Category.TELECOM, Category.HOUSEHOLD_GOODS,
)  # fmt: skip
EVENT_CATEGORIES: Final[Mapping[LifeEventType, tuple[Category, ...]]] = {
    LifeEventType.TRIP: (Category.TRAVEL,),
    LifeEventType.GIFT: (Category.GIFTS,),
    LifeEventType.SOCIAL: (Category.RESTAURANTS, Category.ENTERTAINMENT),
    LifeEventType.EDUCATION: (Category.EDUCATION, Category.BOOKS),
}

EVAL_TEMPLATES: Final[Mapping[str, tuple[str, str]]] = {
    "eval.ignore": (
        "Sumă mică, am trecut-o la {category}.",
        "A small amount, filed as {category}.",
    ),
    "eval.credit": ("Bani primiți.", "Money in."),
    "eval.bill": ("Plată recurentă: {name}.", "Recurring payment: {name}."),
    "eval.health": ("Sănătate: nu te întreb de asta.", "Health: I won't ask about this."),
    "eval.pot": ("Plătit din „{pot}”, era plănuit.", "Paid from “{pot}”, it was planned."),
    "eval.rule": ("{label}, nu te mai întreb de asta.", "{label}, I won't ask about this again."),
    "eval.auto": ("{category}, obișnuit pentru tine.", "{category}, usual for you."),
}
"""Explanation key → (ro, en). Descriptive only: never "good" or "bad"."""


def default_priors() -> Priors:
    """data/priors.json (C1), read once and strictly (E6's loader): the prior when the context
    has no baseline yet."""
    return load_priors()


def _text(key: str, lang: Language, **values: str) -> str:
    ro, en = EVAL_TEMPLATES[key]
    return (ro if lang is Language.RO else en).format_map(values)


def monthly_income(ctx: UserContext) -> Decimal:
    return sum((s.amount for s in ctx.income_sources), Decimal(0))


def monthly_disposable(ctx: UserContext) -> Decimal:
    return monthly_income(ctx) - sum((c.amount for c in ctx.fixed_costs), Decimal(0))


def amount_floor(ctx: UserContext) -> Decimal:
    return max(FLOOR, FLOOR_INCOME_SHARE * monthly_income(ctx))


def guess_purpose(category: Category) -> Purpose:
    return (
        Purpose.ESSENTIAL_LIVING
        if category in ESSENTIAL_CATEGORIES
        else Purpose.UNPLANNED_DISCRETIONARY
    )


def goal_impact(ctx: UserContext, amount: Decimal) -> float:
    """amount / max(remaining to the goal, 1); 0 without a goal (5.3.6)."""
    if ctx.goal is None:
        return 0.0
    saved = ctx.goal_pot.saved if ctx.goal_pot is not None else Decimal(0)
    return float(amount / max(ctx.goal.amount - saved, Decimal(1)))


def _bill(ctx: UserContext, tx: TxView, category: Category) -> str | None:
    if category not in BILL_CATEGORIES:
        return None
    day = tx.occurred_at.astimezone(APP_TZ).day
    for cost in ctx.fixed_costs:
        close = abs(tx.amount - cost.amount) <= BILL_AMOUNT * cost.amount
        if close and abs(day - cost.day_of_month) <= BILL_DAYS:
            return cost.name
    return None


def _pot(ctx: UserContext, category: Category, day: date) -> Pot | None:
    events = {e.id: e for e in ctx.life_events if e.status is LifeEventStatus.PLANNED}
    for pot in ctx.pots:
        if pot.kind is not PotKind.EVENT or pot.status is not PotStatus.ACTIVE:
            continue
        event = events.get(pot.life_event_id) if pot.life_event_id is not None else None
        if event is None or category not in EVENT_CATEGORIES.get(event.type, ()):
            continue
        if pot.deadline is None or day <= pot.deadline:
            return pot
    return None


def _baseline(ctx: UserContext, category: Category, today: date) -> Baseline | None:
    if category in ctx.baselines:
        return ctx.baselines[category]
    computed = compute_baselines(
        ctx.transactions,
        default_priors(),
        ctx.profile.household_scale,
        ctx.profile.city,
        today,
        children=children_count(ctx.facts, today),
    )
    return computed.get(category)


def decide(raw: float, fit: float, unexplained: float) -> Decision:
    """Step 6 of 5.3.4: the thresholds are inclusive."""
    if raw >= INFORM_RAW and fit >= INFORM_FIT:
        return Decision.INFORM
    if unexplained >= ASK_UNEXPLAINED:
        return Decision.ASK
    return Decision.AUTO


def _hint(
    tx: TxView, baseline: Baseline | None, novelty: float, multi: bool, lang: Language
) -> QuestionHint:
    params: dict[str, JsonValue] = {"amount": format_money_in_sentence(tx.amount, lang)}
    if tx.merchant:
        params["merchant"] = tx.merchant
    ratio = (
        float(tx.amount / baseline.expected_median)
        if baseline is not None and baseline.expected_median > 0
        else 0.0
    )
    if ratio >= 2:
        reason, params["ratio"] = "basket_ratio", round(ratio)
    elif novelty >= 1:
        reason = "new_merchant"
    else:
        reason = "large_amount"
    return QuestionHint(reason=reason, params=params, ask_what_item=multi and not tx.items)


def evaluate(ctx: UserContext, tx: TxView) -> Evaluation:
    """The reading of `tx` for this person (5.3.4); bomboe's pipeline saves it."""
    lang = ctx.profile.language
    found = normalize(tx.merchant_raw, tx.mcc, tx.category)
    category = found.category
    tx = tx.replace(category=category, merchant_id=tx.merchant_id or found.merchant_id)
    merchant = tx.merchant or found.name
    day = tx.occurred_at.astimezone(APP_TZ).date()
    impact = goal_impact(ctx, tx.amount)
    cat_label = label(category, lang)

    def auto(
        purpose: Purpose,
        explanation: str | None,
        *,
        decision: Decision = Decision.AUTO,
        source: AnnotationSource = AnnotationSource.AUTO,
        confidence: float = 1.0,
        **extra: Any,
    ) -> Evaluation:
        return Evaluation.model_validate(
            {
                "category": category,
                "merchant_id": tx.merchant_id,
                "merchant": merchant[:80],
                "purpose": purpose,
                "beneficiary": Beneficiary.SELF,
                "effective_amount": tx.amount,
                "annotation_source": source,
                "confidence": confidence,
                "life_fit": 0.0,
                "anomaly_score": 0.0,
                "unexplained": 0.0,
                "decision": decision,
                "explanation": explanation,
                "goal_impact": impact,
                **extra,
            }
        )

    # 2. hard filters
    if tx.amount < amount_floor(ctx):
        return auto(
            guess_purpose(category),
            _text("eval.ignore", lang, category=cat_label),
            decision=Decision.IGNORE,
            confidence=GUESS_CONFIDENCE,
        )
    if tx.direction is Direction.CREDIT:
        return auto(Purpose.UNKNOWN, _text("eval.credit", lang))
    bill = _bill(ctx, tx, category)
    if bill is not None:
        return auto(Purpose.ESSENTIAL_LIVING, _text("eval.bill", lang, name=bill))
    if category is Category.HEALTH_PHARMACY:
        return auto(Purpose.ESSENTIAL_LIVING, _text("eval.health", lang))
    pot = _pot(ctx, category, day)
    if pot is not None:
        return auto(
            Purpose.PLANNED_EVENT,
            _text("eval.pot", lang, pot=pot.name),
            source=AnnotationSource.POT,
            pot_id=pot.id,
        )
    rule = best_rule(ctx.rules, tx, RuleKind.CLASSIFY)
    if rule is not None and rule.confidence >= AUTO_RULE:
        return auto(
            rule.outcome.purpose or guess_purpose(category),
            _text("eval.rule", lang, label=rule.outcome.label or cat_label),
            source=AnnotationSource.RULE,
            confidence=rule.confidence,
            matched_rule_id=rule.id,
        )

    # 3-6. life-fit, deviation, score, decision
    fit = life_fit(tx, ctx)
    baseline = _baseline(ctx, category, day)
    features = anomaly_features(tx, baseline, ctx.transactions, monthly_disposable(ctx))
    raw = 0.5 * features.stat + 0.2 * features.novelty + 0.3 * features.materiality
    rule_match = fit.score if fit.source == "rule" else 0.0
    unexplained = raw * (1 - fit.score) * (1 - rule_match)
    decision = decide(raw, fit.score, unexplained)
    if decision is Decision.ASK and _suppressed(ctx.rules, tx):
        decision = Decision.AUTO
    scores: dict[str, Any] = {
        "life_fit": fit.score,
        "anomaly_score": raw,
        "unexplained": unexplained,
        "matched_fact_id": fit.fact_id,
        "matched_rule_id": fit.rule_id,
    }
    if decision is Decision.ASK:  # 7. provisional until answered
        hint = _hint(tx, baseline, features.novelty, found.multi_category, lang)
        return auto(
            Purpose.UNKNOWN,
            None,
            decision=decision,
            confidence=0.0,
            question_hint=hint,
            **scores,
        )
    purpose = fit_purpose(fit) or guess_purpose(category)
    because = explain(fit, lang) if fit.source != "none" else None
    return auto(
        purpose,
        because or _text("eval.auto", lang, category=cat_label),
        decision=decision,
        source=_source(fit),
        confidence=fit.score if fit.source != "none" else GUESS_CONFIDENCE,
        **scores,
    )


def _source(fit: FitResult) -> AnnotationSource:
    if fit.source in ("signature", "expects_event"):
        return AnnotationSource.FACT
    return AnnotationSource.RULE if fit.source == "rule" else AnnotationSource.AUTO


def _suppressed(rules: tuple[PatternRule, ...], tx: TxView) -> bool:
    return best_rule(rules, tx, RuleKind.SUPPRESS) is not None
