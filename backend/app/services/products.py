"""The mock product catalogue (not per user) (B3 step 1)."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm


async def list_all(db: AsyncSession) -> Sequence[dm.Product]:
    """Every product, in catalogue order (C12 ranks them per user)."""
    raise NotImplementedError("B3 step 1")
