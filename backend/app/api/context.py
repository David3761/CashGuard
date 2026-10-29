"""/forecast, /pots, /products, /life-facts, /life-profile (arch 9.2, B6b steps 2–3)."""

from typing import Any

from fastapi import APIRouter, Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock, events
from app.api import schemas as s
from app.api.deps import CurrentUser, Db
from app.domain import models as dm
from app.domain.enums import FactSource, FactStatus
from app.pipeline import ports
from app.services import (
    fixed_costs,
    forecasts,
    goals,
    income_sources,
    life_events,
    life_facts,
    life_profile,
    plan_preferences,
    pots,
    products,
    signatures,
)
from app.services._common import invalid, not_found
from app.services.context_loader import load_user_context
from app.ws import push_after_commit

router = APIRouter(tags=["context"])
SOFT_NOTES = {"motivation_trend", "what_works", "what_doesnt"}  # arch 4.3: facts go elsewhere


# ── forecast, pots, products ─────────────────────────────────────────────────────────────


@router.get("/forecast")
async def get_forecast(user: CurrentUser, db: Db) -> s.ForecastDetail:
    f = await forecasts.latest(db, user.id)
    if f is None:
        raise not_found("Forecast")
    return s.ForecastDetail(
        **f.model_dump(include=set(s.ForecastOut.model_fields)),
        drivers=[
            s.DriverOut(
                category=d.category,
                pp_per_100_lei=d.pp_per_100_lei,
                category_label=ports.label(d.category, user.language),
            )
            for d in f.drivers
        ],
        options=[
            s.OptionOut(**o.model_dump(include={"label", "probability", "apply_hint"}))
            for o in f.options
        ]
        if f.options is not None
        else None,
        history=[
            s.HistoryPoint(date=h.sim_date, probability=h.probability)
            for h in await forecasts.weekly_history(db, user.id)
            if h.sim_date
        ],
    )


@router.get("/pots")
async def list_pots(user: CurrentUser, db: Db) -> s.PotsOut:
    return s.PotsOut(
        pots=[
            s.PotOut(**p.model_dump(include=set(s.PotOut.model_fields)))
            for p in await pots.list_active(db, user.id)
        ]
    )


@router.get("/products")
async def list_products(user: CurrentUser, db: Db) -> s.ProductsOut:
    ctx = await load_user_context(db, user.id, clock.today(), history_days=1)
    ranked = ports.rank_products(ctx, list(await products.list_all(db)))
    return s.ProductsOut(
        products=[
            s.ProductOut(
                id=p.id,
                name=p.name,
                kind=p.kind,
                rate=float(p.rate),
                liquidity=p.liquidity,
                why_for_you=why,
            )
            for p, why in ranked
        ]
    )


# ── life facts ───────────────────────────────────────────────────────────────────────────


async def fact_out(db: AsyncSession, user_id: int, fact: dm.LifeFact, lang: str) -> s.LifeFactOut:
    assert fact.id is not None
    explains = [
        f"{ports.label(sig.category, lang) or sig.category} → {ports.label(sig.purpose, lang)}"
        for sig in await signatures.list_for_fact(db, user_id, fact.id)
    ]
    return s.LifeFactOut(
        id=fact.id,
        type=fact.type,
        text=fact.text,
        value=fact.value.model_dump(mode="json"),
        status=fact.status,
        source=fact.source,
        confidence=fact.confidence,
        persistence=fact.persistence,
        valid_from=fact.valid_from,
        valid_to=fact.valid_to,
        explains=explains,
    )


async def _propagate(db: AsyncSession, user_id: int, fact: dm.LifeFact) -> None:
    """New signatures for the fact, then the rest of the propagation (C9)."""
    assert fact.id is not None
    await signatures.replace_for_fact(db, user_id, fact.id, ports.signatures_for_fact(fact, None))
    await ports.on_fact_changed(db, user_id, fact.id)


@router.get("/life-facts")
async def list_facts(user: CurrentUser, db: Db, status: FactStatus | None = None) -> s.LifeFactsOut:
    return s.LifeFactsOut(
        facts=[
            await fact_out(db, user.id, f, user.language)
            for f in await life_facts.list_all(db, user.id, status)
        ]
    )


@router.post("/life-facts", status_code=201)
async def create_fact(body: s.LifeFactIn, user: CurrentUser, db: Db) -> s.LifeFactOut:
    try:
        # Our F2 draft: confidence 1 (the user said it), text = the user's words (or the
        # type when the profile screen sends none), valid from today unless given.
        fields = body.model_dump()
        fact = dm.LifeFactDraft.model_validate(
            {
                **fields,
                "text": fields["text"] or fields["type"],
                "valid_from": fields["valid_from"] or clock.today(),
                "source": FactSource.USER_EDIT,
                "status": FactStatus.CONFIRMED,
                "confidence": 1.0,
            }
        )
    except ValidationError as exc:
        raise invalid("invalid_fact", str(exc.errors()[0]["msg"])) from exc
    created = await life_facts.create(db, user.id, fact)
    await _propagate(db, user.id, created)
    await db.commit()
    return await fact_out(db, user.id, created, user.language)


@router.patch("/life-facts/{fact_id}")
async def patch_fact(
    fact_id: int, body: s.LifeFactPatch, user: CurrentUser, db: Db
) -> s.LifeFactOut:
    fact = await life_facts.update(db, user.id, fact_id, **body.model_dump())
    await _propagate(db, user.id, fact)
    await db.commit()
    return await fact_out(db, user.id, fact, user.language)


@router.delete("/life-facts/{fact_id}", status_code=204)
async def delete_fact(fact_id: int, user: CurrentUser, db: Db) -> Response:
    await life_facts.delete(db, user.id, fact_id)  # its signatures go with it
    plan = await ports.recompute_plan(
        db, user.id, reason="life fact removed", trigger_ref={"fact_id": fact_id}
    )
    if plan is not None:
        push_after_commit(db, user.id, events.plan_updated(plan))
    await db.commit()
    return Response(status_code=204)


@router.post("/life-facts/{fact_id}/confirm")
async def confirm_fact(fact_id: int, user: CurrentUser, db: Db) -> s.LifeFactOut:
    fact = await life_facts.confirm(db, user.id, fact_id)
    await _propagate(db, user.id, fact)
    await db.commit()
    return await fact_out(db, user.id, fact, user.language)


@router.post("/life-facts/{fact_id}/reject")
async def reject_fact(fact_id: int, user: CurrentUser, db: Db) -> s.LifeFactOut:
    fact = await life_facts.reject(db, user.id, fact_id)
    await db.commit()
    return await fact_out(db, user.id, fact, user.language)


# ── life profile ─────────────────────────────────────────────────────────────────────────


@router.get("/life-profile")
async def get_life_profile(user: CurrentUser, db: Db) -> s.LifeProfileOut:
    goal = await goals.get_active(db, user.id)
    return s.LifeProfileOut(
        life_profile=await life_profile.get(db, user.id),
        plan_preferences=(await plan_preferences.get(db, user.id)).model_dump(mode="json"),
        goal=goal.model_dump(mode="json") if goal else None,
        events=[
            s.EventOut(**e.model_dump(include={"id", "name", "date", "est_cost"}))
            for e in await life_events.list_planned(db, user.id)
        ],
        income_sources=[
            i.model_dump(mode="json") for i in await income_sources.list_all(db, user.id)
        ],
        fixed_costs=[c.model_dump(mode="json") for c in await fixed_costs.list_all(db, user.id)],
    )


def _soft(key: str) -> str:
    if key not in SOFT_NOTES:
        raise invalid(
            "not_a_soft_note", f"Only {sorted(SOFT_NOTES)} live here; life facts go to /life-facts."
        )
    return key


@router.patch("/life-profile/{key}")
async def set_note(key: str, body: s.NoteIn, user: CurrentUser, db: Db) -> dict[str, Any]:
    notes = await life_profile.set_key(db, user.id, _soft(key), body.value)
    await db.commit()
    return notes


@router.delete("/life-profile/{key}", status_code=204)
async def delete_note(key: str, user: CurrentUser, db: Db) -> Response:
    await life_profile.delete_key(db, user.id, _soft(key))
    await db.commit()
    return Response(status_code=204)
