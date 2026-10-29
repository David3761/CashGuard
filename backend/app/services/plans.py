"""Plan versions (every version is kept) (B3 step 2)."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain.results import PlanResult, PlanSummary
from app.services._common import not_found

PLAN_LOCK_SPACE = 1  # pg_advisory_xact_lock(1, user_id): separate from the pipeline's lock


def _summary(row: m.Plan, previous: m.Plan | None) -> PlanSummary:
    result = PlanResult.model_validate(row.payload)
    prev = PlanResult.model_validate(previous.payload).today_budget if previous else None
    return PlanSummary(
        version=row.version,
        feasible=row.feasible,
        today_budget=result.today_budget,
        previous_today_budget=prev,
        next_7_days=result.next_7_days,
        reason=row.reason,
        created_at=row.created_at,
    )


async def _version(db: AsyncSession, user_id: int, version: int) -> m.Plan | None:
    return await db.scalar(
        select(m.Plan).where(m.Plan.user_id == user_id, m.Plan.version == version)
    )


async def latest(db: AsyncSession, user_id: int) -> PlanSummary | None:
    """The newest version, with `previous_today_budget` from the one before; None before the
    first plan."""
    rows = list(
        await db.scalars(
            select(m.Plan).where(m.Plan.user_id == user_id).order_by(m.Plan.version.desc()).limit(2)
        )
    )
    if not rows:
        return None
    return _summary(rows[0], rows[1] if len(rows) > 1 else None)


async def by_version(db: AsyncSession, user_id: int, version: int) -> PlanSummary:
    """One version. Unknown → not_found."""
    row = await _version(db, user_id, version)
    if row is None:
        raise not_found(f"Plan version {version}")
    return _summary(row, await _version(db, user_id, version - 1))


async def history(db: AsyncSession, user_id: int) -> Sequence[PlanSummary]:
    """Every version, newest first (GET /plan/history)."""
    rows = list(
        await db.scalars(
            select(m.Plan).where(m.Plan.user_id == user_id).order_by(m.Plan.version.desc())
        )
    )
    return [_summary(row, rows[i + 1] if i + 1 < len(rows) else None) for i, row in enumerate(rows)]


async def next_version(db: AsyncSession, user_id: int) -> int:
    """1 + the newest version (1 when none)."""
    newest = await db.scalar(select(func.max(m.Plan.version)).where(m.Plan.user_id == user_id))
    return (newest or 0) + 1


async def save(
    db: AsyncSession,
    user_id: int,
    result: PlanResult,
    *,
    reason: str,
    trigger_ref: dict[str, Any] | None = None,
) -> PlanSummary:
    """Save `result` as the next version (concurrency-safe) with why it changed (arch 6.7)."""
    # Serialise version numbering per user until the transaction ends.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:space, :user_id)"),
        {"space": PLAN_LOCK_SPACE, "user_id": user_id},
    )
    previous = await db.scalar(
        select(m.Plan).where(m.Plan.user_id == user_id).order_by(m.Plan.version.desc()).limit(1)
    )
    row = m.Plan(
        user_id=user_id,
        version=(previous.version + 1) if previous else 1,
        feasible=result.feasible,
        payload=result.model_dump(mode="json"),
        reason=reason,
        trigger_ref=trigger_ref,
    )
    db.add(row)
    await db.flush()
    return _summary(row, previous)
