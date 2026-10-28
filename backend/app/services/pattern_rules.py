"""Learned rules: "every Friday is lunch with the team" (arch 5.3.7) (B3 step 4)."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm


async def get(db: AsyncSession, user_id: int, rule_id: int) -> dm.PatternRule:
    """One rule. Another user's → not_found."""
    raise NotImplementedError("B3 step 4")


async def create(db: AsyncSession, user_id: int, rule: dm.PatternRule) -> dm.PatternRule:
    """Store a validated rule (its `id` is ignored); returns it with the new id."""
    raise NotImplementedError("B3 step 4")


async def list_active(db: AsyncSession, user_id: int) -> Sequence[dm.PatternRule]:
    """Active rules, highest confidence first."""
    raise NotImplementedError("B3 step 4")


async def record_hit(db: AsyncSession, user_id: int, rule_id: int) -> dm.PatternRule:
    """hits += 1, `last_hit_at` = clock.now()."""
    raise NotImplementedError("B3 step 4")


async def record_miss(db: AsyncSession, user_id: int, rule_id: int) -> dm.PatternRule:
    """misses += 1 (a user correction). Deactivating after 2 misses is C8's decision."""
    raise NotImplementedError("B3 step 4")


async def set_confidence(
    db: AsyncSession, user_id: int, rule_id: int, confidence: float
) -> dm.PatternRule:
    """Learning (0.7 → 0.9) and decay (−0.2); outside [0, 1] → invalid_confidence (422)."""
    raise NotImplementedError("B3 step 4")


async def deactivate(db: AsyncSession, user_id: int, rule_id: int) -> dm.PatternRule:
    """active → inactive (idempotent)."""
    raise NotImplementedError("B3 step 4")
