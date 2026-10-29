"""The mock product catalogue (not per user) (B3 step 1)."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain import models as dm
from app.services._common import view


async def list_all(db: AsyncSession) -> Sequence[dm.Product]:
    """Every product, by id (C12 ranks them per user)."""
    rows = await db.scalars(select(m.Product).order_by(m.Product.id))
    return [view(dm.Product, r) for r in rows]
