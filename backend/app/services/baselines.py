"""Cached per-category baselines; only the engine writes them (arch 5.3.5) (B3 step 4)."""

from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain import models as dm
from app.domain.enums import Category
from app.services._common import invalid, view


async def replace_all(
    db: AsyncSession, user_id: int, baselines: Iterable[dm.Baseline]
) -> dict[Category, dm.Baseline]:
    """Replace every baseline of the user with these (categories not given are removed)."""
    by_category: dict[Category, dm.Baseline] = {}
    for baseline in baselines:
        if baseline.category in by_category:
            raise invalid("invalid_baselines", f"{baseline.category} is listed twice.")
        by_category[baseline.category] = baseline
    await db.execute(delete(m.CategoryBaseline).where(m.CategoryBaseline.user_id == user_id))
    db.add_all(m.CategoryBaseline(user_id=user_id, **b.model_dump()) for b in by_category.values())
    await db.flush()
    return await list_all(db, user_id)


async def list_all(db: AsyncSession, user_id: int) -> dict[Category, dm.Baseline]:
    """The baselines by category."""
    rows = await db.scalars(
        select(m.CategoryBaseline)
        .where(m.CategoryBaseline.user_id == user_id)
        .order_by(m.CategoryBaseline.category)
        .execution_options(populate_existing=True)
    )
    return {Category(r.category): view(dm.Baseline, r) for r in rows}
