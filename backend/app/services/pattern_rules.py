"""Learned rules: "every Friday is lunch with the team" (arch 5.3.7) (B3 step 4)."""

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db import models as m
from app.domain import models as dm
from app.services._common import invalid, owned


def _view(row: m.PatternRule) -> dm.PatternRule:
    return dm.PatternRule.model_validate(
        {
            "id": row.id,
            "kind": row.kind,
            "match": row.match,
            "outcome": row.outcome,
            "confidence": float(row.confidence),
            "hits": row.hits,
            "misses": row.misses,
            "source": row.source,
            "active": row.active,
            "last_hit_at": row.last_hit_at,
        }
    )


async def _row(db: AsyncSession, user_id: int, rule_id: int) -> m.PatternRule:
    return await owned(db, m.PatternRule, user_id, rule_id, "Rule")


async def get(db: AsyncSession, user_id: int, rule_id: int) -> dm.PatternRule:
    """One rule. Another user's → not_found."""
    return _view(await _row(db, user_id, rule_id))


async def create(db: AsyncSession, user_id: int, rule: dm.PatternRule) -> dm.PatternRule:
    """Store a validated rule (its `id` is ignored); returns it with the new id."""
    row = m.PatternRule(
        user_id=user_id,
        kind=rule.kind,
        match=rule.match.model_dump(mode="json", exclude_none=True),
        outcome=rule.outcome.model_dump(mode="json", exclude_none=True),
        confidence=Decimal(str(rule.confidence)),
        hits=rule.hits,
        misses=rule.misses,
        source=rule.source,
        active=rule.active,
        last_hit_at=rule.last_hit_at,
    )
    db.add(row)
    await db.flush()
    return _view(row)


async def list_active(db: AsyncSession, user_id: int) -> Sequence[dm.PatternRule]:
    """Active rules, highest confidence first."""
    rows = await db.scalars(
        select(m.PatternRule)
        .where(m.PatternRule.user_id == user_id, m.PatternRule.active.is_(True))
        .order_by(m.PatternRule.confidence.desc(), m.PatternRule.id)
    )
    return [_view(r) for r in rows]


async def record_hit(db: AsyncSession, user_id: int, rule_id: int) -> dm.PatternRule:
    """hits += 1, `last_hit_at` = clock.now()."""
    row = await _row(db, user_id, rule_id)
    row.hits += 1
    row.last_hit_at = clock.now()
    await db.flush()
    return _view(row)


async def record_miss(db: AsyncSession, user_id: int, rule_id: int) -> dm.PatternRule:
    """misses += 1 (a user correction). Deactivating after 2 misses is C8's decision."""
    row = await _row(db, user_id, rule_id)
    row.misses += 1
    await db.flush()
    return _view(row)


async def set_confidence(
    db: AsyncSession, user_id: int, rule_id: int, confidence: float
) -> dm.PatternRule:
    """Learning (0.7 → 0.9) and decay (−0.2); outside [0, 1] → invalid_confidence (422)."""
    row = await _row(db, user_id, rule_id)
    if not 0 <= confidence <= 1:
        raise invalid("invalid_confidence", "confidence is between 0 and 1.")
    row.confidence = Decimal(str(confidence))
    await db.flush()
    return _view(row)


async def deactivate(db: AsyncSession, user_id: int, rule_id: int) -> dm.PatternRule:
    """active → inactive (idempotent)."""
    row = await _row(db, user_id, rule_id)
    row.active = False
    await db.flush()
    return _view(row)
