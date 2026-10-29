"""Goal probability history: "81%, vs 72% last week" (arch 6.7) (B3 step 4)."""

from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db import models as m
from app.domain.results import Forecast
from app.services._common import invalid, owned


def _view(
    row: m.GoalForecast, previous: float | None = None, last_week: float | None = None
) -> Forecast:
    return Forecast.model_validate(
        {
            "probability": float(row.probability),
            "previous_probability": previous,
            "last_week_probability": last_week,
            "p10": row.p10,
            "p50": row.p50,
            "p90": row.p90,
            "expected_reach_date": row.expected_reach_date,
            "drivers": row.drivers,
            "options": row.options,
            "plan_version": row.plan_version,
            "sim_date": row.sim_date,
            "is_weekly_snapshot": row.is_weekly_snapshot,
        }
    )


async def save(
    db: AsyncSession, user_id: int, forecast: Forecast, *, goal_id: int, reason: str | None = None
) -> Forecast:
    """Store one forecast (its `is_weekly_snapshot` flag is the engine's decision)."""
    await owned(db, m.Goal, user_id, goal_id, "Goal")
    if forecast.plan_version is None:
        raise invalid("invalid_forecast", "A forecast belongs to a plan version.")
    row = m.GoalForecast(
        user_id=user_id,
        goal_id=goal_id,
        plan_version=forecast.plan_version,
        sim_date=forecast.sim_date or clock.today(),
        probability=Decimal(str(round(forecast.probability, 4))),
        p10=forecast.p10,
        p50=forecast.p50,
        p90=forecast.p90,
        expected_reach_date=forecast.expected_reach_date,
        drivers=[d.model_dump(mode="json") for d in forecast.drivers],
        options=[o.model_dump(mode="json") for o in forecast.options]
        if forecast.options is not None
        else None,
        is_weekly_snapshot=forecast.is_weekly_snapshot,
        reason=reason,
    )
    db.add(row)
    await db.flush()
    return _view(row)


async def latest(db: AsyncSession, user_id: int) -> Forecast | None:
    """The newest forecast, with `previous_probability` from the one before and
    `last_week_probability` from the last weekly snapshot. Newest = the last one saved (id):
    `computed_at` is the sim clock, which `/sim/reset` moves back below the seeded forecast's."""
    rows = list(
        await db.scalars(
            select(m.GoalForecast)
            .where(m.GoalForecast.user_id == user_id)
            .order_by(m.GoalForecast.id.desc())
            .limit(2)
        )
    )
    if not rows:
        return None
    newest = rows[0]
    this_monday = newest.sim_date - timedelta(days=newest.sim_date.weekday())
    last_week = await db.scalar(
        select(m.GoalForecast.probability)
        .where(
            m.GoalForecast.user_id == user_id,
            m.GoalForecast.is_weekly_snapshot.is_(True),
            m.GoalForecast.sim_date < this_monday,
        )
        .order_by(m.GoalForecast.sim_date.desc(), m.GoalForecast.id.desc())
        .limit(1)
    )
    previous = float(rows[1].probability) if len(rows) > 1 else None
    return _view(newest, previous, float(last_week) if last_week is not None else None)


async def last_weekly_snapshot(db: AsyncSession, user_id: int) -> Forecast | None:
    """The newest forecast flagged as a weekly snapshot."""
    row = await db.scalar(
        select(m.GoalForecast)
        .where(m.GoalForecast.user_id == user_id, m.GoalForecast.is_weekly_snapshot.is_(True))
        .order_by(m.GoalForecast.sim_date.desc(), m.GoalForecast.id.desc())
        .limit(1)
    )
    return _view(row) if row is not None else None


async def weekly_history(db: AsyncSession, user_id: int) -> Sequence[Forecast]:
    """Every weekly snapshot, oldest first (GET /forecast `history`)."""
    rows = await db.scalars(
        select(m.GoalForecast)
        .where(m.GoalForecast.user_id == user_id, m.GoalForecast.is_weekly_snapshot.is_(True))
        .order_by(m.GoalForecast.sim_date, m.GoalForecast.id)
    )
    return [_view(r) for r in rows]
