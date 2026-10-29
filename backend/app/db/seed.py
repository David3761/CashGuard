"""Seed loader (B12): merchants, products and the demo personas from `backend/data/`.

    uv run python -m app.db.seed --reset      # delete all user data, then seed everything

File formats (the contract with E12 / D1 / C1; `scripts/placeholder_data.py` writes examples):
- `merchants.json`: [{id, canonical_name, aliases, category, mcc, typical_basket, multi_category}]
- `products.json`: [{id, name, kind, rate, liquidity, min_months, max_months, mock, description}]
- `personas/<id>/profile.json`: {name, age, city, language, tagline, household_scale, onboarded,
  account: {current_balance}, income_sources: [...], fixed_costs: [...],
  goal: {amount, deadline, motivation, soft, saved} | absent, pots: [{name, kind, target,
  saved, deadline}], plan_preferences: {...}, last_week_probability: float | absent}
- `personas/<id>/facts.json`: [{type, value, text, persistence?, valid_from?, valid_to?,
  status?, confidence?, signatures?: [Signature]}] (no `signatures` → `signatures_for_fact`)
- `personas/<id>/rules.json` (optional): [PatternRule without id]
- `personas/<id>/transactions.json`: [{occurred_at, merchant_raw, amount, category, direction?,
  items?, purpose?, beneficiary?, effective_amount?, annotation_source?, explanation?}]
The persona's login is the realm user with the same username (keycloak_sub = its fixed id).
"""

import argparse
import asyncio
import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.clock import BUCHAREST, FixedClock
from app.config import get_settings
from app.db import models as m
from app.domain import models as dm
from app.domain.enums import AnnotationSource, PotKind, TransactionSource, TransactionStatus
from app.domain.results import Forecast
from app.pipeline import ports
from app.services import (
    accounts,
    fixed_costs,
    forecasts,
    goals,
    income_sources,
    life_facts,
    pattern_rules,
    plan_preferences,
    pots,
    signatures,
    users,
)

BACKEND = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND / "data"
REALM_FILE = BACKEND / "keycloak" / "realm-cashguard.json"
PERSONAS = ("matei", "andrei", "bianca", "ioana", "alex")


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def realm_subs(realm_file: Path = REALM_FILE) -> dict[str, str]:
    """username → fixed Keycloak user id."""
    realm = _read(realm_file) or {}
    return {u["username"]: u["id"] for u in realm.get("users", []) if "id" in u}


def persona_list(data_dir: Path = DATA_DIR) -> list[dict[str, Any]]:
    out = []
    for pid in PERSONAS:
        profile = _read(data_dir / "personas" / pid / "profile.json")
        if profile:
            out.append({"id": pid, "name": profile["name"], "tagline": profile.get("tagline", "")})
    return out


async def reset(db: AsyncSession) -> None:
    """Delete every user (and so all their rows), the catalogues and the sim clock."""
    await db.execute(delete(m.User))
    await db.execute(delete(m.Merchant))
    await db.execute(delete(m.Product))
    await db.execute(delete(m.SimClock))
    await db.flush()


async def seed_catalogues(db: AsyncSession, data_dir: Path = DATA_DIR) -> None:
    await db.execute(delete(m.Merchant))
    await db.execute(delete(m.Product))
    db.add_all(m.Merchant(**row) for row in _read(data_dir / "merchants.json") or [])
    db.add_all(m.Product(**row) for row in _read(data_dir / "products.json") or [])
    await db.flush()


async def seed_persona(db: AsyncSession, pid: str, sub: str, data_dir: Path = DATA_DIR) -> int:
    folder = data_dir / "personas" / pid
    p = _read(folder / "profile.json")
    user = await users.create(
        db,
        keycloak_sub=sub,
        name=p["name"],
        age=p.get("age"),
        language=p.get("language", "ro"),
        city=p.get("city"),
    )
    uid = user.id
    await users.update(db, uid, household_scale=Decimal(str(p.get("household_scale", 1))))
    if p.get("onboarded"):
        await users.set_onboarded(db, uid)
    await accounts.create(db, uid, current_balance=Decimal(str(p["account"]["current_balance"])))
    for i in p.get("income_sources", []):
        await income_sources.create(
            db,
            uid,
            source=i["source"],
            amount=Decimal(str(i["amount"])),
            day_of_month=i["day_of_month"],
        )
    for c in p.get("fixed_costs", []):
        await fixed_costs.create(
            db,
            uid,
            name=c["name"],
            amount=Decimal(str(c["amount"])),
            day_of_month=c["day_of_month"],
        )
    goal = p.get("goal")
    if goal:
        g = await goals.create(
            db,
            uid,
            amount=Decimal(str(goal["amount"])),
            deadline=date.fromisoformat(goal["deadline"]),
            motivation=goal.get("motivation"),
            soft=goal.get("soft", True),
        )
        goal_pot = await pots.goal_pot(db, uid)
        if goal_pot and goal.get("saved"):
            await pots.add_saved(db, uid, goal_pot.id, Decimal(str(goal["saved"])))
    for pot in p.get("pots", []):
        created = await pots.create(
            db,
            uid,
            name=pot["name"],
            kind=PotKind(pot["kind"]),
            target=Decimal(str(pot["target"])),
            deadline=date.fromisoformat(pot["deadline"]) if pot.get("deadline") else None,
        )
        if pot.get("saved"):
            await pots.add_saved(db, uid, created.id, Decimal(str(pot["saved"])))
    if p.get("plan_preferences"):
        await plan_preferences.update(db, uid, **p["plan_preferences"])
    for raw in _read(folder / "facts.json") or []:
        sigs = raw.pop("signatures", None)
        fact = await life_facts.create(db, uid, dm.LifeFact(source="seed", **raw))
        assert fact.id is not None
        made = (
            [dm.Signature(**s) for s in sigs]
            if sigs is not None
            else ports.signatures_for_fact(fact, None)
        )
        await signatures.replace_for_fact(db, uid, fact.id, made)
    for raw in _read(folder / "rules.json") or []:
        await pattern_rules.create(db, uid, dm.PatternRule(**raw))
    for raw in _read(folder / "transactions.json") or []:
        amount = Decimal(str(raw["amount"]))
        db.add(
            m.Transaction(
                user_id=uid,
                amount=amount,
                direction=raw.get("direction", "debit"),
                occurred_at=datetime.fromisoformat(raw["occurred_at"]),
                merchant_raw=raw["merchant_raw"],
                category=raw.get("category"),
                items=raw.get("items"),
                source=TransactionSource.SEED,
                status=TransactionStatus.RESOLVED,
                processed_at=clock.now(),
                effective_amount=Decimal(str(raw.get("effective_amount", amount))),
                purpose=raw.get("purpose"),
                beneficiary=raw.get("beneficiary", "self"),
                annotation_source=raw.get("annotation_source", AnnotationSource.AUTO),
                explanation=raw.get("explanation"),
                decision="auto",
            )
        )
    await db.flush()
    await ports.recompute_baselines(db, uid)
    if goal and p.get("last_week_probability") is not None:
        last_week = clock.today() - timedelta(days=7)
        await forecasts.save(
            db,
            uid,
            Forecast(
                probability=p["last_week_probability"],
                p10=Decimal("0"),
                p50=Decimal("0"),
                p90=Decimal("0"),
                plan_version=0,
                sim_date=last_week,
                is_weekly_snapshot=True,
            ),
            goal_id=g.id,
            reason="seed: last week",
        )
    plan = await ports.recompute_plan(db, uid, reason="seed")
    if plan is not None:
        await ports.forecast_goal(db, uid, plan.version)
    return uid


async def seed_all(
    db: AsyncSession, *, data_dir: Path = DATA_DIR, reset_first: bool = False
) -> dict[str, int]:
    """Catalogues + every persona at the sim start date; returns persona id → user id."""
    start = get_settings().SIM_START_DATE
    previous = clock.get_clock()
    clock.set_clock(FixedClock(datetime.combine(start, time(9, 0), tzinfo=BUCHAREST)))
    try:
        if reset_first:
            await reset(db)
        await seed_catalogues(db, data_dir)
        subs = realm_subs()
        seeded = {
            pid: await seed_persona(db, pid, subs[pid], data_dir)
            for pid in PERSONAS
            if (data_dir / "personas" / pid / "profile.json").exists()
        }
        await db.merge(m.SimClock(id=1, today=start))
        await db.flush()
        return seeded
    finally:
        clock.set_clock(previous)


async def counts(db: AsyncSession) -> dict[str, int]:
    return {
        t.name: await db.scalar(select(func.count()).select_from(t)) or 0
        for t in m.Base.metadata.sorted_tables
    }


async def _main(reset_first: bool) -> None:
    from app.db.session import unit_of_work

    async with unit_of_work() as db:
        seeded = await seed_all(db, reset_first=reset_first)
    print(f"seeded {len(seeded)} personas: {', '.join(seeded)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the demo data")
    parser.add_argument("--reset", action="store_true", help="delete all user data first")
    asyncio.run(_main(parser.parse_args().reset))
