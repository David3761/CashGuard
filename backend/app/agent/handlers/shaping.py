"""Plan-shaping and coaching tool handlers (A3 step 3; arch 6.6, 6.7 D19, F8)."""

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from app.agent.handlers.common import RunState, ToolContext, to_jsonable
from app.domain.enums import FactType
from app.domain.models import WEEKDAY_NAMES, PlanPreferences
from app.domain.money import to_money
from app.errors import DomainError

RECURRING_SLIP_STEP = Decimal("0.25")  # a recurring slip day gets this much more budget weight
MAX_WEIGHT = Decimal("3")


def _pins(value: Any) -> dict[Any, Any]:
    """`pin_days` as {date: amount}, from a mapping or a list of {date, amount}."""
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    return {item["date"]: item["amount"] for item in value}


def _weights(value: Any) -> dict[str, Any]:
    """`weekday_weights` as {"Mon": w}, from A2's [{weekday: 1-7 (ISO), weight}] or a mapping."""
    if not value:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    return {WEEKDAY_NAMES[item["weekday"] - 1]: item["weight"] for item in value}


def _caps(current: Mapping[Any, Any], value: Any) -> dict[Any, Any]:
    """The caps after A2's [{category, amount_per_week}] (null removes that cap)."""
    caps = dict(current)
    items = (
        value.items()
        if isinstance(value, Mapping)
        else [(item["category"], item["amount_per_week"]) for item in value or []]
    )
    for category, amount in items:
        if amount is None:
            caps.pop(category, None)
        else:
            caps[category] = amount
    return caps


def _save(ctx: ToolContext, data: Mapping[str, Any]) -> PlanPreferences:
    try:
        preferences = PlanPreferences.model_validate(dict(data))
    except ValidationError as error:
        reasons = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'preferences'}: {e['msg']}"
            for e in error.errors(include_url=False, include_input=False, include_context=False)
        )
        raise DomainError("invalid_preferences", f"Invalid shape: {reasons}"[:1000], 422) from None
    return ctx.services.plan_preferences.save(ctx.user_id, preferences)


def shape_budget(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    current = ctx.services.plan_preferences.get(ctx.user_id)
    pinned = {**current.pinned_days, **_pins(args.get("pin_days"))}
    for day in args.get("unpin_days") or []:
        pinned.pop(day, None)
    saved = _save(
        ctx,
        {
            "weekday_weights": {**current.weekday_weights, **_weights(args.get("weekday_weights"))},
            "pinned_days": pinned,
            "category_caps": _caps(current.category_caps, args.get("category_caps")),
            "buffer_pct": current.buffer_pct
            if args.get("buffer_pct") is None
            else args["buffer_pct"],
        },
    )
    return {"preferences": to_jsonable(saved), "_plan_reason": "budget shaped"}


def record_slip_reason(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    day, recurring = args["date"], bool(args.get("recurring"))
    slip = ctx.services.slips.create(
        ctx.user_id,
        {
            "date": day,
            "reason": args["reason"],
            "detail": args.get("detail"),
            "recurring": recurring,
        },
    )
    result: dict[str, Any] = {"slip": slip, "_trigger_ref": {"slip_id": slip["id"]}}
    if recurring:
        current = ctx.services.plan_preferences.get(ctx.user_id)
        weekday = WEEKDAY_NAMES[day.weekday()]
        weights = dict(current.weekday_weights)
        weights[weekday] = min(MAX_WEIGHT, Decimal(weights.get(weekday, 1)) + RECURRING_SLIP_STEP)
        saved = _save(ctx, {**current.model_dump(), "weekday_weights": weights})
        result["weekday_weights"] = to_jsonable(saved.weekday_weights)
    return result


def record_reflection(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    row = ctx.services.reflections.create(
        ctx.user_id,
        {
            "motivation": args.get("motivation"),
            "answer": args["answer"],
            "reason": args.get("reason"),
        },
    )
    return {"reflection": row}


def update_life_profile(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    key, value = str(args["key"]).strip(), str(args["value"]).strip()
    if key in set(FactType):
        raise DomainError(
            "use_add_life_fact",
            f"'{key}' is a life fact: save it with add_life_fact (the profile keeps notes only).",
        )
    if not key or not value:
        raise DomainError("invalid_input", "Give a key and a value.", 422)
    ctx.services.life_profile.set_note(ctx.user_id, key, value)
    return {"key": key, "value": value}


def transfer_to_savings(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    amount = to_money(args["amount"])
    if amount <= 0:
        raise DomainError("invalid_input", "The amount must be above 0.", 422)
    transfer = ctx.services.transfers.to_savings(ctx.user_id, amount)
    return {
        "transfer": transfer,
        "undo_available": True,
        "_trigger_ref": {"transfer_id": transfer["id"]},
    }


def complete_onboarding(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    s, uid = ctx.services, ctx.user_id
    checklist = {
        "goal": s.goals.active(uid) is not None,
        "income": bool(s.income_sources.list(uid)),
        "fixed_costs": bool(s.fixed_costs.list(uid)),
        "life_context": bool(s.life_facts.list_active(uid)),
    }
    missing = [item for item, done in checklist.items() if not done]
    if missing:
        raise DomainError(
            "onboarding_incomplete",
            f"Still missing: {', '.join(missing)}. Ask the user for these first.",
            409,
        )
    s.users.mark_onboarded(uid)
    return {"onboarded": True, "_plan_reason": "onboarding completed: first plan"}
