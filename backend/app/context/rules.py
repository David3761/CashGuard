"""C8: learning rules ("if every Friday is team lunch, it stops asking"; arch 5.3.7), pure.

- `rule_matches(rule, tx)`: an active rule's merchant, category, amount (from `amount_min` up to
  2x `amount_max`: above that it's a new situation) and weekday / time window (both ends
  inclusive, Bucharest time). The kind doesn't matter: a `suppress` rule matches like a classify
  rule, it just never classifies (C6 uses it only to turn `ask` into `auto`).
- `learn(annotated_tx, history, rules)`, after the user explained a transaction (answer / edit):
  - a classify rule already matches it: the same purpose is a confirmation (hits + 1; the 3rd
    confirmation lifts it to 0.9), another purpose is a correction (misses + 1; 2 misses
    deactivate it);
  - otherwise the same pattern explained twice (same category and weekday, time within ±1 h,
    amount within ±40% of the earlier one, the same purpose) → a new classify rule at 0.7 (0.9
    when it is already the 3rd time).
- `explicit_rule(...)`: "în fiecare vineri mâncăm cu echipa" (the `create_pattern_rule` tool) →
  0.9 straight away.
- `decay(rules, today)`: -0.2 per full 60 days without a hit, counted from the rule's ladder
  value (0.9 explicit or ≥ 3 hits, else 0.7), so running it twice the same day changes nothing;
  below 0.5 → inactive.

Nothing here judges a purchase: a rule only remembers how the person explained it.
"""

from collections.abc import Iterable, Sequence
from datetime import date, datetime, time, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Final

from app.clock import APP_TZ
from app.domain.enums import AnnotationSource, Direction, Purpose, RuleKind, RuleSource
from app.domain.models import PatternRule, RuleMatch, RuleOutcome, TxView
from app.domain.results import RuleChange

AMOUNT_LIMIT: Final = 2  # a rule doesn't apply above 2x its max amount
SIMILAR_AMOUNT: Final = Decimal("0.40")
SIMILAR_MINUTES: Final = 60
LEARN_AFTER: Final = 2  # explanations of the same pattern → a rule
CONFIRM_AFTER: Final = 3  # confirmations → the auto confidence
LEARNED_CONFIDENCE: Final = 0.7
CONFIRMED_CONFIDENCE: Final = 0.9
EXPLICIT_CONFIDENCE: Final = 0.9
DECAY_DAYS: Final = 60
DECAY_STEP: Final = 0.2
MIN_CONFIDENCE: Final = 0.5  # below → inactive
MAX_MISSES: Final = 2
RANGE_LOW: Final = Decimal("0.60")  # a new rule's amount range: ±40% around what was seen
RANGE_HIGH: Final = Decimal("1.40")
USER_SOURCES: Final = (AnnotationSource.ANSWER, AnnotationSource.USER_EDIT)
_LAST_MINUTE: Final = time(23, 59)


# ── matching ─────────────────────────────────────────────────────────────────────────────────


def _local(tx: TxView) -> datetime:
    return tx.occurred_at.astimezone(APP_TZ)


def rule_matches(rule: PatternRule, tx: TxView) -> bool:
    """Does the active `rule` cover `tx`? (Every bound inclusive; amount ≤ 2x `amount_max`.)"""
    match = rule.match
    if not rule.active:
        return False
    if match.merchant_id is not None and match.merchant_id != tx.merchant_id:
        return False
    if match.category is not None and match.category != tx.category:
        return False
    if match.amount_min is not None and tx.amount < match.amount_min:
        return False
    if match.amount_max is not None and tx.amount > AMOUNT_LIMIT * match.amount_max:
        return False
    local = _local(tx)
    if match.weekdays and local.isoweekday() not in match.weekdays:
        return False
    if match.from_ is not None and match.to is not None:
        return match.from_ <= local.time().replace(tzinfo=None) <= match.to
    return True


def best_rule(rules: Iterable[PatternRule], tx: TxView, kind: RuleKind) -> PatternRule | None:
    """The most confident matching rule of `kind` (ties: the higher id)."""
    matching = [r for r in rules if r.kind is kind and rule_matches(r, tx)]
    return max(matching, key=lambda r: (r.confidence, r.id or 0), default=None)


# ── learning ─────────────────────────────────────────────────────────────────────────────────


def _minutes(tx: TxView) -> int:
    local = _local(tx)
    return local.hour * 60 + local.minute


def similar(earlier: TxView, later: TxView) -> bool:
    """The same pattern: category, weekday, time within ±1 h, amount within ±40% of `earlier`."""
    if earlier.category is None or earlier.category != later.category:
        return False
    if _local(earlier).isoweekday() != _local(later).isoweekday():
        return False
    if abs(_minutes(earlier) - _minutes(later)) > SIMILAR_MINUTES:
        return False
    return abs(later.amount - earlier.amount) <= SIMILAR_AMOUNT * earlier.amount


def _explained(tx: TxView) -> bool:
    return (
        tx.annotation_source in USER_SOURCES
        and tx.direction is Direction.DEBIT
        and tx.category is not None
        and tx.purpose is not None
        and tx.purpose is not Purpose.UNKNOWN
    )


def ladder(rule: PatternRule) -> float:
    """The confidence a rule earns from how it was made: explicit or ≥ 3 hits → 0.9, else 0.7."""
    if rule.source is RuleSource.EXPLICIT or rule.hits >= CONFIRM_AFTER:
        return CONFIRMED_CONFIDENCE
    return LEARNED_CONFIDENCE


def _covering_rule(rules: Iterable[PatternRule], tx: TxView) -> PatternRule | None:
    covering = [
        r
        for r in rules
        if r.kind is RuleKind.CLASSIFY
        and r.active
        and (rule_matches(r, tx) or (r.id is not None and r.id == tx.matched_rule_id))
    ]
    return max(covering, key=lambda r: (r.confidence, r.id or 0), default=None)


def _confirm_or_correct(rule: PatternRule, tx: TxView) -> RuleChange | None:
    if rule.last_hit_at is not None and rule.last_hit_at >= tx.occurred_at:
        return None  # this transaction (or a later one) was already counted
    if tx.purpose == rule.outcome.purpose:
        hits = rule.hits + 1
        confidence = max(rule.confidence, ladder(rule.replace(hits=hits)))
        confirmed = rule.replace(hits=hits, confidence=confidence, last_hit_at=tx.occurred_at)
        return RuleChange(action="updated", rule=confirmed, previous_confidence=rule.confidence)
    misses = rule.misses + 1
    active = misses < MAX_MISSES
    corrected = rule.replace(misses=misses, active=active)
    return RuleChange(
        action="updated" if active else "deactivated",
        rule=corrected,
        previous_confidence=rule.confidence,
    )


def _window(txs: Sequence[TxView]) -> tuple[time, time]:
    """From the earliest time - 1 h (down to the hour) to the latest + 1 h (up to the hour)."""
    low = max(0, min(_minutes(t) for t in txs) - SIMILAR_MINUTES) // 60 * 60
    high = -(-(max(_minutes(t) for t in txs) + SIMILAR_MINUTES) // 60) * 60
    to = _LAST_MINUTE if high >= 24 * 60 else time(high // 60, high % 60)
    return time(low // 60, low % 60), to


def _new_rule(tx: TxView, matches: Sequence[TxView]) -> PatternRule:
    seen = [tx, *matches]
    start, end = _window(seen)
    amounts = [t.amount for t in seen]
    count = len(seen)
    return PatternRule(
        kind=RuleKind.CLASSIFY,
        match=RuleMatch.model_validate(
            {
                "category": tx.category,
                "weekdays": (_local(tx).isoweekday(),),
                "from": start,
                "to": end,
                "amount_min": (min(amounts) * RANGE_LOW).quantize(Decimal(1), ROUND_FLOOR),
                "amount_max": (max(amounts) * RANGE_HIGH).quantize(Decimal(1), ROUND_CEILING),
            }
        ),
        outcome=RuleOutcome(purpose=tx.purpose),
        confidence=CONFIRMED_CONFIDENCE if count >= CONFIRM_AFTER else LEARNED_CONFIDENCE,
        hits=count,
        source=RuleSource.LEARNED,
        created_at=tx.occurred_at,
        last_hit_at=tx.occurred_at,
    )


def learn(
    annotated_tx: TxView, history: Iterable[TxView], rules: Iterable[PatternRule]
) -> RuleChange | None:
    """What the user's explanation of `annotated_tx` teaches (5.3.7), or None.

    Only the user's own words count (`annotation_source` answer / user_edit, a known purpose).
    `history` is the person's other transactions; `rules` their rules (inactive ones are
    ignored)."""
    tx = annotated_tx
    if not _explained(tx):
        return None
    rules = tuple(rules)
    covering = _covering_rule(rules, tx)
    if covering is not None:
        return _confirm_or_correct(covering, tx)
    matches = [
        past
        for past in history
        if past.id != tx.id
        and past.occurred_at < tx.occurred_at
        and _explained(past)
        and past.purpose == tx.purpose
        and similar(past, tx)
    ]
    if len(matches) + 1 < LEARN_AFTER:
        return None
    return RuleChange(action="created", rule=_new_rule(tx, matches))


def explicit_rule(
    kind: RuleKind, match: RuleMatch, outcome: RuleOutcome, now: datetime
) -> PatternRule:
    """A rule the person stated ("în fiecare vineri mâncăm cu echipa"): 0.9 at once."""
    return PatternRule(
        kind=kind,
        match=match,
        outcome=outcome,
        confidence=EXPLICIT_CONFIDENCE,
        source=RuleSource.EXPLICIT,
        created_at=now,
    )


# ── decay ────────────────────────────────────────────────────────────────────────────────────


def decay(rules: Iterable[PatternRule], today: date) -> list[RuleChange]:
    """-0.2 per full 60 days without a hit (from the ladder value); below 0.5 → inactive.
    Idempotent for a given `today`: only the rules that change are returned."""
    out = []
    for rule in rules:
        if not rule.active:
            continue
        last = (rule.last_hit_at or rule.created_at).astimezone(APP_TZ).date()
        periods = (today - last) // timedelta(days=DECAY_DAYS)
        if periods < 1:
            continue
        target = max(0.0, round(ladder(rule) - DECAY_STEP * periods, 2))
        if target >= rule.confidence:
            continue  # already decayed this far
        active = target >= MIN_CONFIDENCE
        out.append(
            RuleChange(
                action="updated" if active else "deactivated",
                rule=rule.replace(confidence=target, active=active),
                previous_confidence=rule.confidence,
            )
        )
    return out
