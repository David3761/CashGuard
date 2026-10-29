"""Receivable tool handlers (A3 step 2; arch 6.6, F11, D31).

`offer_payment_request` sends nothing: it attaches a tap card to the reply and leaves the
status `open`; the user's tap calls `POST /receivables/{id}/request-payment` (bomboe).
"""

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from app import clock
from app.agent.handlers.common import RunState, ToolContext, to_jsonable
from app.agent.handlers.transactions import DEFAULT_DEBTOR, RECEIVABLE_DUE_DAYS
from app.agent.ports import ReceivableDraft
from app.domain.enums import ReceivableStatus
from app.domain.money import share_each, split_share, to_money
from app.domain.results import ActionCard
from app.errors import DomainError
from app.i18n.format import format_money

_LIVE = (ReceivableStatus.OPEN, ReceivableStatus.REQUESTED)
TIMES = "\u00d7"  # the multiplication sign on the card ("4 [x] 100 lei")
_CARD = {"ro": "Trimite cererea ({what})", "en": "Send the request ({what})"}


async def create_receivable(
    ctx: ToolContext, run: RunState, args: Mapping[str, Any]
) -> dict[str, Any]:
    tx_id, people = args.get("transaction_id"), args.get("people_count")
    amount = args.get("amount")
    if tx_id is not None:
        await ctx.services.transactions.get(ctx.user_id, tx_id)  # the transaction is the user's
    if amount is None:
        if tx_id is None or people is None or people < 2:
            raise DomainError(
                "invalid_input",
                "Give the amount, or a transaction_id with people_count ≥ 2 to split it.",
                422,
            )
        tx = await ctx.services.transactions.get(ctx.user_id, tx_id)
        amount = split_share(tx.amount, people).others
    amount = to_money(amount)
    if amount <= 0:
        raise DomainError("invalid_input", "The receivable amount must be above 0.", 422)
    each = share_each(amount, people - 1) if people is not None and people > 1 else None
    label = (args.get("debtor_label") or "").strip() or DEFAULT_DEBTOR.get(ctx.language, "alții")
    receivable = await ctx.services.receivables.create(
        ctx.user_id,
        ReceivableDraft(
            debtor_label=label,
            amount=amount,
            expected_by=args.get("expected_by")
            or clock.today() + timedelta(days=RECEIVABLE_DUE_DAYS),
            transaction_id=tx_id,
            people_count=people if each is not None else None,
            amount_each=each,
        ),
    )
    run.pushes.append(("receivable.updated", {"receivable_id": receivable.id}))
    return {"receivable": to_jsonable(receivable), "_trigger_ref": {"receivable_id": receivable.id}}


async def cancel_receivable(
    ctx: ToolContext, run: RunState, args: Mapping[str, Any]
) -> dict[str, Any]:
    receivable = await ctx.services.receivables.get(ctx.user_id, args["receivable_id"])
    if receivable.status not in _LIVE:
        raise DomainError(
            "receivable_closed", f"This receivable is already {receivable.status}.", 409
        )
    receivable = await ctx.services.receivables.cancel(ctx.user_id, receivable.id)
    run.pushes.append(("receivable.updated", {"receivable_id": receivable.id}))
    return {"receivable": to_jsonable(receivable), "_trigger_ref": {"receivable_id": receivable.id}}


async def mark_receivable_paid(
    ctx: ToolContext, run: RunState, args: Mapping[str, Any]
) -> dict[str, Any]:
    receivable = await ctx.services.receivables.get(ctx.user_id, args["receivable_id"])
    if receivable.status not in _LIVE:
        raise DomainError(
            "receivable_closed", f"This receivable is already {receivable.status}.", 409
        )
    receivable = await ctx.services.receivables.mark_paid(ctx.user_id, receivable.id)
    run.pushes.append(("receivable.updated", {"receivable_id": receivable.id}))
    return {"receivable": to_jsonable(receivable), "_trigger_ref": {"receivable_id": receivable.id}}


async def offer_payment_request(
    ctx: ToolContext, run: RunState, args: Mapping[str, Any]
) -> dict[str, Any]:
    receivable = await ctx.services.receivables.get(ctx.user_id, args["receivable_id"])
    if receivable.status is not ReceivableStatus.OPEN:
        raise DomainError(
            "receivable_not_open",
            f"Only an open receivable can get a payment request; this one is {receivable.status}.",
            409,
        )
    lang = ctx.language if ctx.language in _CARD else "ro"
    if receivable.people_count and receivable.people_count > 1 and receivable.amount_each:
        each = format_money(receivable.amount_each, lang)
        what = f"{receivable.people_count - 1} {TIMES} {each}"
    else:
        what = format_money(receivable.amount, lang)
    card = ActionCard(
        type="request_payment", receivable_id=receivable.id, label=_CARD[lang].format(what=what)
    ).model_dump(mode="json")
    if card not in run.action_cards:
        run.action_cards.append(card)
    return {"receivable_id": receivable.id, "status": receivable.status, "card": card}
