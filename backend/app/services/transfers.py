"""Transfers to savings: manual and the payday auto-save (D37) (B3 step 2)."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm
from app.domain.enums import TransferKind


async def get(db: AsyncSession, user_id: int, transfer_id: int) -> dm.Transfer:
    """One transfer. Another user's → not_found."""
    raise NotImplementedError("B3 step 2")


async def create(
    db: AsyncSession,
    user_id: int,
    *,
    amount: Decimal,
    kind: TransferKind = TransferKind.MANUAL,
    pot_id: int | None = None,
    income_transaction_id: int | None = None,
) -> dm.Transfer:
    """Record the transfer (moving the money is the engine's job). A second auto-save for the
    same income transaction → already_saved (409)."""
    raise NotImplementedError("B3 step 2")


async def for_income(
    db: AsyncSession, user_id: int, income_transaction_id: int
) -> dm.Transfer | None:
    """The auto-save made for that salary, if any (idempotency check)."""
    raise NotImplementedError("B3 step 2")


async def undo(db: AsyncSession, user_id: int, transfer_id: int) -> dm.Transfer:
    """Set `undone_at` once; a second undo → already_undone (409). The caller moves the money
    back."""
    raise NotImplementedError("B3 step 2")
