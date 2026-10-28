"""The merchant catalogue (not per user) (B3 step 1)."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm


async def list_all(db: AsyncSession) -> Sequence[dm.Merchant]:
    """Every merchant."""
    raise NotImplementedError("B3 step 1")


async def get(db: AsyncSession, merchant_id: str) -> dm.Merchant:
    """One merchant by slug. Unknown → not_found."""
    raise NotImplementedError("B3 step 1")
