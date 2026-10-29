"""Life-fact tool handlers (A3 step 3; arch 5.3.3, 5.3.9, 6.6, 15.2).

Every change runs the same chain: validate with F2's `LifeFactDraft` → save → C4
`signatures_for_fact` (the library first, Claude's `signatures` for the rest) →
`signatures.replace_for_fact` → C9 `on_fact_changed` (baselines, re-evaluation); then the
executor's D18 recompute.
"""

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from app import clock
from app.agent.handlers.common import RunState, ToolContext, changes, need_changes, to_jsonable
from app.domain.enums import FactSource, FactStatus
from app.domain.models import LifeFact, LifeFactDraft
from app.errors import DomainError

_EDITABLE = ("value", "text", "persistence", "valid_from", "valid_to")


def _draft(data: Mapping[str, Any]) -> LifeFactDraft:
    try:
        return LifeFactDraft.model_validate(dict(data))
    except ValidationError as error:
        reasons = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'fact'}: {e['msg']}"
            for e in error.errors(include_url=False, include_input=False, include_context=False)
        )
        raise DomainError("invalid_fact", f"Invalid life fact: {reasons}"[:1000], 422) from None


def _propagate(
    ctx: ToolContext, fact: LifeFact, llm_signatures: list[dict[str, Any]] | None, *, active: bool
) -> dict[str, Any]:
    signatures = ctx.context.signatures_for_fact(fact, llm_signatures) if active else []
    ctx.services.signatures.replace_for_fact(ctx.user_id, fact.id, signatures)
    propagation = ctx.context.on_fact_changed(ctx.db, ctx.user_id, fact.id)
    changed = () if propagation is None else propagation.changed_transaction_ids
    return {
        "fact": to_jsonable(fact),
        "signatures": len(signatures),
        "reevaluated_transaction_ids": list(changed),
        "_plan_reason": f"fact: {fact.type} {fact.text}"[:300],
        "_trigger_ref": {"fact_id": fact.id},
    }


def add_life_fact(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    draft = _draft(
        {
            "type": args["type"],
            "value": args["value"],
            "text": args["text"],
            "persistence": args["persistence"],
            "valid_from": args.get("valid_from") or clock.today(),
            "valid_to": args.get("valid_to"),
            "source": FactSource.CHAT,
            "status": FactStatus.CONFIRMED,
            "confidence": 1.0,
        }
    )
    fact = ctx.services.life_facts.create(ctx.user_id, draft)
    return _propagate(ctx, fact, args.get("signatures"), active=True)


def update_life_fact(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    old = ctx.services.life_facts.get(ctx.user_id, args["fact_id"])
    found = {k: v for k, v in changes(args, "fact_id", "signatures").items() if k in _EDITABLE}
    need_changes(found, "life fact")
    draft = _draft({**old.model_dump(exclude={"id", "created_at"}), **found})
    fact = ctx.services.life_facts.update(ctx.user_id, old.id, draft)
    return _propagate(ctx, fact, args.get("signatures"), active=True)


def expire_life_fact(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    old = ctx.services.life_facts.get(ctx.user_id, args["fact_id"])
    valid_to = args.get("valid_to") or clock.today()
    if valid_to < old.valid_from:
        raise DomainError("invalid_fact", "valid_to must not be before the fact's valid_from.", 422)
    fact = ctx.services.life_facts.expire(ctx.user_id, old.id, valid_to)
    return _propagate(ctx, fact, None, active=False)


def confirm_hypothesis(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    old = ctx.services.life_facts.get(ctx.user_id, args["fact_id"])
    if old.status is not FactStatus.HYPOTHESIS:
        raise DomainError("not_a_hypothesis", f"Fact {old.id} is {old.status}, not a hypothesis.")
    if args["accepted"]:
        fact = ctx.services.life_facts.confirm(ctx.user_id, old.id)
        return _propagate(ctx, fact, None, active=True)
    fact = ctx.services.life_facts.reject(ctx.user_id, old.id)
    return _propagate(ctx, fact, None, active=False)
