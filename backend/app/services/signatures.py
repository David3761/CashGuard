"""Spending signatures: what each fact predicts (arch 5.3.3) (B3 step 4)."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm
from app.domain.enums import SignatureEffect


async def replace_for_fact(
    db: AsyncSession, user_id: int, fact_id: int, signatures: Sequence[dm.Signature]
) -> Sequence[dm.Signature]:
    """Atomically swap the fact's signatures for these (an error halfway keeps the old set).
    Another user's fact → not_found."""
    raise NotImplementedError("B3 step 4")


async def list_active(
    db: AsyncSession, user_id: int, effect: SignatureEffect | None = None
) -> Sequence[dm.Signature]:
    """Active signatures of confirmed facts, optionally of one effect."""
    raise NotImplementedError("B3 step 4")


async def list_for_fact(db: AsyncSession, user_id: int, fact_id: int) -> Sequence[dm.Signature]:
    """One fact's signatures (the "Explică: …" line on the profile screen)."""
    raise NotImplementedError("B3 step 4")
