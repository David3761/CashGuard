"""Transaction tool handlers (A3 step 2): S0 stub of the shared `apply_annotation`.

One implementation for the `annotate_transaction` tool and bomboe's `PATCH /transactions/{id}`
(B6). A3 replaces the body: write through `transactions.annotate`, create the receivable, call
danutu's `on_annotation_changed` and C8's `learn_from_annotation`, mark the question answered.

The stub only computes the split (effective = `own_amount` if given, which wins over
`people_count`; else `split_share(amount, people_count)`; else the whole amount) and writes
nothing. `db` is typed `Any` until bomboe's session exists.
"""

import importlib
from decimal import Decimal
from typing import Any

from app.domain.enums import AnnotationSource, Beneficiary, Purpose
from app.domain.models import DomainModel, TxView
from app.domain.money import Money, share_each, split_share, to_money
from app.errors import DomainError

# ── TODO(A3): the result shape is A3's (F2 has none); kept minimal until A3 lands. ─────────


class AnnotationResult(DomainModel):  # TODO(A3): the real handler's result
    transaction_id: int
    purpose: Purpose
    beneficiary: Beneficiary
    effective_amount: Money
    receivable_amount: Money | None = None  # what the others owe, when they will repay
    amount_each: Money | None = None  # for the card ("100 lei each")
    estimated: bool = False
    source: AnnotationSource


def _transaction(db: Any, user_id: int, tx_id: int) -> TxView:
    """bomboe's `services.transactions.get` (B3), looked up at call time (not merged yet)."""
    tx: TxView = importlib.import_module("app.services.transactions").get(db, user_id, tx_id)
    return tx


def apply_annotation(
    db: Any,
    user_id: int,
    tx_id: int,
    purpose: Purpose,
    beneficiary: Beneficiary,
    own_amount: Decimal | None = None,
    people_count: int | None = None,
    others_will_repay: bool = False,
    debtor_label: str | None = None,
    source: AnnotationSource = AnnotationSource.ANSWER,
) -> AnnotationResult:
    """Stub of A3: the user's share and the receivable, computed only (nothing is saved)."""
    tx = _transaction(db, user_id, tx_id)
    if own_amount is not None:
        own = to_money(own_amount)
        if own < 0 or own > tx.amount:
            raise DomainError("invalid_own_amount", f"own_amount must be 0..{tx.amount}", 422)
    elif people_count is not None:
        own = split_share(tx.amount, people_count).own
    else:
        own = tx.amount
    others = tx.amount - own
    repay = others_will_repay and others > 0
    each = (
        share_each(others, people_count - 1)
        if repay and people_count and people_count > 1
        else None
    )
    return AnnotationResult(
        transaction_id=tx.id,
        purpose=purpose,
        beneficiary=beneficiary,
        effective_amount=own,
        receivable_amount=others if repay else None,
        amount_each=each,
        source=source,
    )
