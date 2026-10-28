"""Cached per-category baselines; only the engine writes them (arch 5.3.5) (B3 step 4)."""

from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm
from app.domain.enums import Category


async def replace_all(
    db: AsyncSession, user_id: int, baselines: Iterable[dm.Baseline]
) -> dict[Category, dm.Baseline]:
    """Replace every baseline of the user with these (categories not given are removed)."""
    raise NotImplementedError("B3 step 4")


async def list_all(db: AsyncSession, user_id: int) -> dict[Category, dm.Baseline]:
    """The baselines by category."""
    raise NotImplementedError("B3 step 4")
