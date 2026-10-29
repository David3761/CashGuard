"""Transaction tool handlers (A3 step 2) and the shared `apply_annotation` (arch 6.6, F11, 15.2).

`apply_annotation` is the one implementation behind the `annotate_transaction` tool and bomboe's
`PATCH /transactions/{id}` (B6); it keeps S0's signature, as a coroutine (B6 awaits it). **The
code computes every amount**, never Claude:

- effective (the user's own share) = `own_amount` if given (it wins over `people_count`), else
  `split_share(amount, people_count)`, else, for a purchase shared with or made for others,
  danutu's `own_share_estimate` with `estimated: true` (clamped to 0..amount); a purchase for
  the user alone is the whole amount.
- a receivable when `others_will_repay` and the others' share > 0 (`amount_each` for the card,
  per other person when `people_count` > 1). A receivable already open on the transaction that
  no longer matches (a correction like "doar pentru mine") is cancelled.
- then danutu's `on_annotation_changed(old, new)` (the ledger delta; the transaction before and
  after go along), C8's `learn_from_annotation`, and the open question on the transaction is
  marked answered.
"""

from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal
from typing import Any

from app import clock
from app.agent.handlers.common import RunState, ToolContext, to_jsonable
from app.agent.ports import (
    Annotation,
    ContextPort,
    EnginePort,
    LazyContext,
    LazyEngine,
    ReceivableDraft,
    Services,
    services_for,
)
from app.domain.enums import AnnotationSource, Beneficiary, Direction, Purpose
from app.domain.models import DomainModel, Receivable, TxView
from app.domain.money import Money, share_each, split_share, to_money
from app.errors import DomainError

RECEIVABLE_DUE_DAYS = 14  # the receivable reminder fires after 14 days (F11)
ESTIMATED_CONFIDENCE = 0.6
DEFAULT_DEBTOR = {"ro": "alții", "en": "others"}
SHARED_BENEFICIARIES = (Beneficiary.SHARED, Beneficiary.OTHERS)


class AnnotationResult(DomainModel):
    """What `apply_annotation` did (the tool result and B6's PATCH response)."""

    transaction_id: int
    purpose: Purpose
    beneficiary: Beneficiary
    amount: Money
    previous_effective_amount: Money
    effective_amount: Money
    estimated: bool = False
    receivable_id: int | None = None
    receivable_amount: Money | None = None  # what the others owe, when they will repay
    people_count: int | None = None
    amount_each: Money | None = None  # for the card ("4 x 100 lei")
    cancelled_receivable_id: int | None = None  # a correction cancelled it
    answered_event_id: int | None = None
    source: AnnotationSource


async def _own_share(
    db: Any,
    user_id: int,
    tx: TxView,
    *,
    purpose: Purpose,
    beneficiary: Beneficiary,
    own_amount: Decimal | None,
    people_count: int | None,
    others_will_repay: bool,
    engine: EnginePort,
) -> tuple[Decimal, bool]:
    """(the user's share, estimated?)."""
    if own_amount is not None:
        own = to_money(own_amount)
        if own < 0 or own > tx.amount:
            raise DomainError(
                "invalid_own_amount",
                f"own_amount must be between 0 and the transaction amount ({tx.amount}).",
                422,
            )
        return own, False
    if people_count is not None:
        if people_count < 1:
            raise DomainError("invalid_people_count", "people_count must be at least 1.", 422)
        return split_share(tx.amount, people_count).own, False
    shared = (
        others_will_repay
        or beneficiary in SHARED_BENEFICIARIES
        or purpose is Purpose.ON_BEHALF_OF_OTHERS
    )
    if not shared:
        return tx.amount, False
    estimate = to_money(await engine.own_share_estimate(db, user_id, tx))
    return min(max(estimate, Decimal("0.00")), tx.amount), True


async def apply_annotation(
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
    *,
    note: str | None = None,
    language: str = "ro",
    services: Services | None = None,
    engine: EnginePort | None = None,
    context: ContextPort | None = None,
) -> AnnotationResult:
    """Annotate one of the user's transactions; see the module docstring for the rules."""
    services = services_for(db) if services is None else services
    engine = LazyEngine() if engine is None else engine
    context = LazyContext() if context is None else context
    purpose, beneficiary = Purpose(purpose), Beneficiary(beneficiary)

    tx = await services.transactions.get(user_id, tx_id)  # not_found for another user's transaction
    if tx.direction is not Direction.DEBIT:
        raise DomainError("not_a_spend", "Only a spend (debit) can be annotated.", 422)
    own, estimated = await _own_share(
        db,
        user_id,
        tx,
        purpose=purpose,
        beneficiary=beneficiary,
        own_amount=own_amount,
        people_count=people_count,
        others_will_repay=others_will_repay,
        engine=engine,
    )
    others = tx.amount - own
    repay = others_will_repay and others > 0
    each = (
        share_each(others, people_count - 1)
        if repay and people_count is not None and people_count > 1
        else None
    )
    label = (debtor_label or "").strip() or DEFAULT_DEBTOR.get(language, DEFAULT_DEBTOR["ro"])

    receivable: Receivable | None = None
    cancelled: int | None = None
    old = await services.receivables.open_for_transaction(user_id, tx_id)
    if old is not None:
        if repay and old.amount == others and old.debtor_label == label:
            receivable = old  # the same answer again: keep it
        else:
            await services.receivables.cancel(user_id, old.id)
            cancelled = old.id
    if repay and receivable is None:
        receivable = await services.receivables.create(
            user_id,
            ReceivableDraft(
                debtor_label=label,
                amount=others,
                expected_by=clock.today() + timedelta(days=RECEIVABLE_DUE_DAYS),
                transaction_id=tx_id,
                people_count=people_count if each is not None else None,
                amount_each=each,
            ),
        )

    annotated = await services.transactions.annotate(
        user_id,
        tx_id,
        Annotation(
            purpose=purpose,
            beneficiary=beneficiary,
            effective_amount=own,
            source=source,
            estimated=estimated,
            confidence=ESTIMATED_CONFIDENCE if estimated else 1.0,
            receivable_id=None if receivable is None else receivable.id,
            note=note,
        ),
    )
    await engine.on_annotation_changed(
        db, user_id, tx_id, tx.effective_amount, own, before=tx, after=annotated
    )
    await context.learn_from_annotation(db, user_id, tx_id)
    question = await services.agent_events.open_question_for(user_id, tx_id)
    answered = None
    if question is not None:
        answered = int(question["id"])
        await services.agent_events.mark_answered(user_id, answered)

    return AnnotationResult(
        transaction_id=tx_id,
        purpose=purpose,
        beneficiary=beneficiary,
        amount=tx.amount,
        previous_effective_amount=tx.effective_amount,
        effective_amount=own,
        estimated=estimated,
        receivable_id=None if receivable is None else receivable.id,
        receivable_amount=None if receivable is None else receivable.amount,
        people_count=people_count if each is not None else None,
        amount_each=each,
        cancelled_receivable_id=cancelled,
        answered_event_id=answered,
        source=source,
    )


async def annotate_transaction(
    ctx: ToolContext, run: RunState, args: Mapping[str, Any]
) -> dict[str, Any]:
    result = await apply_annotation(
        ctx.db,
        ctx.user_id,
        args["transaction_id"],
        args["purpose"],
        args["beneficiary"],
        own_amount=args.get("own_amount"),
        people_count=args.get("people_count"),
        others_will_repay=bool(args.get("others_will_repay")),
        debtor_label=args.get("debtor_label"),
        source=AnnotationSource.ANSWER,
        note=args.get("note"),
        language=ctx.language,
        services=ctx.services,
        engine=ctx.engine,
        context=ctx.context,
    )
    body = result.model_dump(mode="json")
    run.pushes.append(("transaction.annotated", body))
    if result.receivable_id is not None or result.cancelled_receivable_id is not None:
        run.pushes.append(("receivable.updated", body))
    return {
        **body,
        "_plan_reason": (
            f"annotation: tx {result.transaction_id} "
            f"{result.previous_effective_amount} → {result.effective_amount}"
        ),
        "_trigger_ref": {"transaction_id": result.transaction_id},
    }


async def get_transaction(
    ctx: ToolContext, run: RunState, args: Mapping[str, Any]
) -> dict[str, Any]:
    tx = await ctx.services.transactions.get(ctx.user_id, args["transaction_id"])
    receivable = (
        None
        if tx.receivable_id is None
        else await ctx.services.receivables.get(ctx.user_id, tx.receivable_id)
    )
    return {"transaction": to_jsonable(tx), "receivable": to_jsonable(receivable)}
