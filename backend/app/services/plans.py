"""Plan versions (every version is kept) (B3 step 2)."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.results import PlanResult, PlanSummary


async def latest(db: AsyncSession, user_id: int) -> PlanSummary | None:
    """The newest version, with `previous_today_budget` from the one before; None before the
    first plan."""
    raise NotImplementedError("B3 step 2")


async def by_version(db: AsyncSession, user_id: int, version: int) -> PlanSummary:
    """One version. Unknown → not_found."""
    raise NotImplementedError("B3 step 2")


async def history(db: AsyncSession, user_id: int) -> Sequence[PlanSummary]:
    """Every version, newest first (GET /plan/history)."""
    raise NotImplementedError("B3 step 2")


async def next_version(db: AsyncSession, user_id: int) -> int:
    """1 + the newest version (1 when none)."""
    raise NotImplementedError("B3 step 2")


async def save(
    db: AsyncSession,
    user_id: int,
    result: PlanResult,
    *,
    reason: str,
    trigger_ref: dict[str, Any] | None = None,
) -> PlanSummary:
    """Save `result` as the next version (concurrency-safe) with why it changed (arch 6.7)."""
    raise NotImplementedError("B3 step 2")
