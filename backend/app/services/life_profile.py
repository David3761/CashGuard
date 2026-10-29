"""Soft coaching notes only (what works / doesn't); facts are life_facts (B3 step 1)."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.services._common import not_found


async def get(db: AsyncSession, user_id: int) -> dict[str, Any]:
    """The notes (`{}` when none)."""
    row = await db.get(m.LifeProfile, user_id)
    return dict(row.data) if row is not None else {}


async def set_key(db: AsyncSession, user_id: int, key: str, value: Any) -> dict[str, Any]:
    """Set one key; returns all the notes."""
    row = await db.get(m.LifeProfile, user_id)
    if row is None:
        row = m.LifeProfile(user_id=user_id, data={})
        db.add(row)
    row.data = {**row.data, key: value}  # a new dict, so the JSONB change is saved
    await db.flush()
    return dict(row.data)


async def delete_key(db: AsyncSession, user_id: int, key: str) -> dict[str, Any]:
    """Remove one key (missing key → not_found); returns all the notes."""
    row = await db.get(m.LifeProfile, user_id)
    if row is None or key not in row.data:
        raise not_found(f"Life profile note {key!r}")
    row.data = {k: v for k, v in row.data.items() if k != key}
    await db.flush()
    return dict(row.data)
