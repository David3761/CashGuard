"""The merchant catalogue (not per user) (B3 step 1)."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain import models as dm
from app.services._common import not_found, view


async def list_all(db: AsyncSession) -> Sequence[dm.Merchant]:
    """Every merchant, by id."""
    rows = await db.scalars(select(m.Merchant).order_by(m.Merchant.id))
    return [view(dm.Merchant, r) for r in rows]


async def get(db: AsyncSession, merchant_id: str) -> dm.Merchant:
    """One merchant by slug. Unknown → not_found."""
    row = await db.get(m.Merchant, merchant_id)
    if row is None:
        raise not_found("Merchant")
    return view(dm.Merchant, row)
