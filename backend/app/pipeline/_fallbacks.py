"""bomboe's stand-ins (arch 15.1) that `ports.py` still uses after the integration, each a
TODO(INT) there: `apply_annotation` (until our async A3 handler lands), `on_fact_changed` (until
C9 replaces our no-op stub) and `rank_products` (until C12 exists)."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import local_date
from app.domain import models as dm
from app.domain.enums import AnnotationSource, Beneficiary, Direction, Purpose
from app.domain.models import TxView
from app.domain.money import split_share
from app.domain.results import PropagationResult
from app.domain.user_context import UserContext
from app.engine.service import recompute_plan
from app.services import ledger, transactions


async def apply_annotation(
    db: AsyncSession,
    user_id: int,
    tx_id: int,
    purpose: Purpose,
    beneficiary: Beneficiary,
    own_amount: Decimal | None = None,
    people_count: int | None = None,
    others_will_repay: bool = False,
    debtor_label: str | None = None,
    source: AnnotationSource = AnnotationSource.USER_EDIT,
) -> TxView:
    """S0 (David G.'s shared annotate logic, A3): own_amount wins over people_count; the
    ledger moves by the effective-amount delta (danutu's on_annotation_changed)."""
    tx = await transactions.get(db, user_id, tx_id)
    effective = tx.effective_amount
    if own_amount is not None:
        effective = own_amount
    elif people_count is not None:
        effective, _ = split_share(tx.amount, people_count)
    new = await transactions.annotate(
        db,
        user_id,
        tx_id,
        purpose=purpose,
        beneficiary=beneficiary,
        effective_amount=effective,
        source=source,
    )
    if tx.direction == Direction.DEBIT and new.effective_amount != tx.effective_amount:
        await ledger.add_spent(
            db, user_id, local_date(tx.occurred_at), new.effective_amount - tx.effective_amount
        )
    return new


async def on_fact_changed(db: AsyncSession, user_id: int, fact_id: int) -> PropagationResult:
    """Stand-in for C9: re-plans with the real engine (the fact's effects reach the plan)."""
    plan = await recompute_plan(
        db, user_id, reason="life fact changed", trigger_ref={"fact_id": fact_id}
    )
    return PropagationResult(fact_id=fact_id, plan=plan)


def rank_products(
    ctx: UserContext, products: list[dm.Product]
) -> list[tuple[dm.Product, str | None]]:
    """S0 (David G., C12): catalogue order, no reason."""
    return [(p, None) for p in products]
