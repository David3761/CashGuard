"""How the user shaped the budget (D19) (B3 step 1)."""

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain import models as dm
from app.domain.enums import Category
from app.services._common import invalid


def _merge(current: dict[Any, Any], changes: dict[Any, Any] | None) -> dict[Any, Any]:
    """Apply `changes` on top of `current`; a None value removes that key."""
    merged = dict(current)
    for key, value in (changes or {}).items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


async def get(db: AsyncSession, user_id: int) -> dm.PlanPreferences:
    """The preferences; the defaults when the user never shaped anything."""
    row = await db.get(m.PlanPreferences, user_id)
    if row is None:
        return dm.PlanPreferences()
    return dm.PlanPreferences.model_validate(
        {
            "weekday_weights": row.weekday_weights,
            "pinned_days": row.pinned_days,
            "category_caps": row.category_caps,
            "buffer_pct": row.buffer_pct,
        }
    )


async def update(
    db: AsyncSession,
    user_id: int,
    *,
    weekday_weights: dict[str, float] | None = None,
    pinned_days: dict[date, Decimal | None] | None = None,
    category_caps: dict[Category, Decimal | None] | None = None,
    buffer_pct: Decimal | None = None,
) -> dm.PlanPreferences:
    """Merge into the stored preferences; a `None` value removes that pin / cap (shape_budget)."""
    current = await get(db, user_id)
    try:
        prefs = dm.PlanPreferences.model_validate(
            {
                "weekday_weights": _merge(dict(current.weekday_weights), weekday_weights),
                "pinned_days": _merge(dict(current.pinned_days), pinned_days),
                "category_caps": _merge(dict(current.category_caps), category_caps),
                "buffer_pct": current.buffer_pct if buffer_pct is None else buffer_pct,
            }
        )
    except ValidationError as exc:
        raise invalid("invalid_preferences", str(exc.errors()[0]["msg"])) from exc
    stored = prefs.model_dump(mode="json")
    row = await db.get(m.PlanPreferences, user_id)
    if row is None:
        row = m.PlanPreferences(user_id=user_id)
        db.add(row)
    row.weekday_weights = stored["weekday_weights"]
    row.pinned_days = stored["pinned_days"]
    row.category_caps = stored["category_caps"]
    row.buffer_pct = prefs.buffer_pct
    await db.flush()
    return prefs


async def save(db: AsyncSession, user_id: int, prefs: dm.PlanPreferences) -> dm.PlanPreferences:
    """Store the whole preferences as given (the agent's `shape_budget` computed them, pins
    removed included)."""
    stored = prefs.model_dump(mode="json")
    row = await db.get(m.PlanPreferences, user_id)
    if row is None:
        row = m.PlanPreferences(user_id=user_id)
        db.add(row)
    row.weekday_weights = stored["weekday_weights"]
    row.pinned_days = stored["pinned_days"]
    row.category_caps = stored["category_caps"]
    row.buffer_pct = prefs.buffer_pct
    await db.flush()
    return prefs
