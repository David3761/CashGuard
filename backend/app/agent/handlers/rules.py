"""`create_pattern_rule` (A3 step 3; arch 5.3.7, 6.6): an explicit rule starts at 0.9 (C8)."""

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from app import clock
from app.agent.handlers.common import RunState, ToolContext, to_jsonable
from app.domain.enums import RuleSource
from app.domain.models import PatternRule
from app.errors import DomainError

EXPLICIT_CONFIDENCE = 0.9


async def create_pattern_rule(
    ctx: ToolContext, run: RunState, args: Mapping[str, Any]
) -> dict[str, Any]:
    try:
        rule = PatternRule.model_validate(
            {
                "kind": args["kind"],
                "match": args["match"],
                "outcome": args.get("outcome") or {},
                "confidence": EXPLICIT_CONFIDENCE,
                "source": RuleSource.EXPLICIT,
                "created_at": clock.now(),
            }
        )
    except ValidationError as error:
        reasons = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'rule'}: {e['msg']}"
            for e in error.errors(include_url=False, include_input=False, include_context=False)
        )
        raise DomainError("invalid_rule", f"Invalid rule: {reasons}"[:1000], 422) from None
    saved = await ctx.services.pattern_rules.create(ctx.user_id, rule)
    return {"rule": to_jsonable(saved)}
