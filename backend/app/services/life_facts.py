"""Life facts: the person's life, one row per statement (arch 5.3) (B3 step 4).

States: hypothesis → confirmed | rejected; confirmed → expired. A rejected fact is never
proposed again (the inference checks rejected ones too).
"""

from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm
from app.domain.enums import FactStatus, Persistence


async def get(db: AsyncSession, user_id: int, fact_id: int) -> dm.LifeFact:
    """One fact. Another user's → not_found."""
    raise NotImplementedError("B3 step 4")


async def create(db: AsyncSession, user_id: int, fact: dm.LifeFact) -> dm.LifeFact:
    """Store a validated fact (its `id` is ignored); returns it with the new id."""
    raise NotImplementedError("B3 step 4")


async def update(
    db: AsyncSession,
    user_id: int,
    fact_id: int,
    *,
    value: dict[str, Any] | None = None,
    text: str | None = None,
    persistence: Persistence | None = None,
    valid_from: date | None = None,
    valid_to: date | None = None,
    confidence: float | None = None,
) -> dm.LifeFact:
    """Change only the fields given; the result is re-validated (F2 rules)."""
    raise NotImplementedError("B3 step 4")


async def expire(db: AsyncSession, user_id: int, fact_id: int, valid_to: date) -> dm.LifeFact:
    """confirmed → expired from `valid_to`. Otherwise → invalid_transition."""
    raise NotImplementedError("B3 step 4")


async def delete(db: AsyncSession, user_id: int, fact_id: int) -> None:
    """Remove the fact and its signatures (cascade). Another user's → not_found."""
    raise NotImplementedError("B3 step 4")


async def list_all(
    db: AsyncSession, user_id: int, status: FactStatus | None = None
) -> Sequence[dm.LifeFact]:
    """Every fact, or only one status (GET /life-facts?status=)."""
    raise NotImplementedError("B3 step 4")


async def list_active(db: AsyncSession, user_id: int, on_date: date) -> Sequence[dm.LifeFact]:
    """Confirmed facts whose validity window contains `on_date` (inclusive)."""
    raise NotImplementedError("B3 step 4")


async def list_hypotheses(db: AsyncSession, user_id: int) -> Sequence[dm.LifeFact]:
    """Facts still waiting for the 1-tap confirmation."""
    raise NotImplementedError("B3 step 4")


async def confirm(db: AsyncSession, user_id: int, fact_id: int) -> dm.LifeFact:
    """hypothesis → confirmed (confidence 0.9). Otherwise → invalid_transition."""
    raise NotImplementedError("B3 step 4")


async def reject(db: AsyncSession, user_id: int, fact_id: int) -> dm.LifeFact:
    """hypothesis → rejected (kept: never proposed again). Otherwise → invalid_transition."""
    raise NotImplementedError("B3 step 4")
