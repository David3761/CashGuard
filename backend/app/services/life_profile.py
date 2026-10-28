"""Soft coaching notes only (what works / doesn't); facts are life_facts (B3 step 1)."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


async def get(db: AsyncSession, user_id: int) -> dict[str, Any]:
    """The notes (`{}` when none)."""
    raise NotImplementedError("B3 step 1")


async def set_key(db: AsyncSession, user_id: int, key: str, value: Any) -> dict[str, Any]:
    """Set one key; returns all the notes."""
    raise NotImplementedError("B3 step 1")


async def delete_key(db: AsyncSession, user_id: int, key: str) -> dict[str, Any]:
    """Remove one key (missing key → not_found); returns all the notes."""
    raise NotImplementedError("B3 step 1")
