"""Money other people owe the user (arch 4.4) (B3 step 4).

States: open → requested → paid; open | requested → cancelled.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm
from app.domain.enums import ReceivableStatus


async def get(db: AsyncSession, user_id: int, receivable_id: int) -> dm.Receivable:
    """One receivable. Another user's → not_found."""
    raise NotImplementedError("B3 step 4")


async def create(
    db: AsyncSession,
    user_id: int,
    *,
    amount: Decimal,
    debtor_label: str,
    expected_by: date,
    transaction_id: int | None = None,
    people_count: int | None = None,
    amount_each: Decimal | None = None,
) -> dm.Receivable:
    """An open receivable."""
    raise NotImplementedError("B3 step 4")


async def list_all(
    db: AsyncSession, user_id: int, status: ReceivableStatus | None = None
) -> Sequence[dm.Receivable]:
    """Every receivable, or only one status (GET /receivables?status=), newest first."""
    raise NotImplementedError("B3 step 4")


async def list_open(db: AsyncSession, user_id: int) -> Sequence[dm.Receivable]:
    """Open and requested (still expected), by `expected_by`."""
    raise NotImplementedError("B3 step 4")


async def update_status(
    db: AsyncSession, user_id: int, receivable_id: int, status: ReceivableStatus
) -> dm.Receivable:
    """Follow the state machine (sets `requested_at` / `paid_at`); anything else →
    invalid_transition (409)."""
    raise NotImplementedError("B3 step 4")


async def cancel(db: AsyncSession, user_id: int, receivable_id: int) -> dm.Receivable:
    """open | requested → cancelled ("nu, a fost doar pentru mine")."""
    raise NotImplementedError("B3 step 4")
