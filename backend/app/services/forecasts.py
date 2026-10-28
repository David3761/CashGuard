"""Goal probability history: "81%, vs 72% last week" (arch 6.7) (B3 step 4)."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.results import Forecast


async def save(
    db: AsyncSession, user_id: int, forecast: Forecast, *, goal_id: int, reason: str | None = None
) -> Forecast:
    """Store one forecast (its `is_weekly_snapshot` flag is the engine's decision)."""
    raise NotImplementedError("B3 step 4")


async def latest(db: AsyncSession, user_id: int) -> Forecast | None:
    """The newest forecast, with `previous_probability` from the one before and
    `last_week_probability` from the last weekly snapshot."""
    raise NotImplementedError("B3 step 4")


async def last_weekly_snapshot(db: AsyncSession, user_id: int) -> Forecast | None:
    """The newest forecast flagged as a weekly snapshot."""
    raise NotImplementedError("B3 step 4")


async def weekly_history(db: AsyncSession, user_id: int) -> Sequence[Forecast]:
    """Every weekly snapshot, oldest first (GET /forecast `history`)."""
    raise NotImplementedError("B3 step 4")
