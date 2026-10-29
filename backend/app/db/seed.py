"""Seed loader (B12): merchants, products and the demo personas from `backend/data/`.

    uv run python -m app.db.seed --reset      # delete all user data, then seed everything

File formats since the integration (the teams' real files; read strictly with `parse_json`):
- `merchants.json` {"merchants": [...]}, `products.json` {"products": [...]} (C1, David G.)
- `personas/<id>/profile.json` + `transactions.json`: danutu's E12 generator output
  (`user`, `account`, `income_sources`, `fixed_costs`, `goal` {hard_deadline}, `goal_pot`
  {name, saved}, `pots`, `plan_preferences`; transactions with an `annotation` object)
- `personas/<id>/facts.json` {"facts": [LifeFactDraft]}, `rules.json` {"rules": [PatternRule]}
  (David G., H-13)
- `personas/<id>/extras.json` (optional; Elena, the heavy persona, `scripts/build_elena.py`):
  {"transfers", "receivables", "life_events", "slips", "reflections", "messages",
  "notifications"}, each a list of rows for that table (a transfer names its pot by `pot`)
Every persona but Alex is onboarded (A20).

bomboe's original placeholder formats (`scripts/placeholder_data.py`), kept for reference:
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
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.clock import BUCHAREST, FixedClock
from app.config import get_settings
from app.db import models as m
from app.domain import models as dm
from app.domain.enums import (
    AnnotationSource,
    FactSource,
    PotKind,
    TransactionSource,
    TransactionStatus,
)
from app.domain.money import parse_json
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
PERSONAS = ("matei", "andrei", "bianca", "ioana", "alex", "elena")


def _read(path: Path) -> Any:
    """Strict JSON (Decimal numbers; duplicate keys, NaN, Infinity rejected: HANDOFFS H-7)."""
    return parse_json(path.read_text(encoding="utf-8")) if path.exists() else None


def _rows(path: Path, key: str) -> list[Any]:
    """The list under `key` of a {"<key>": [...]} file (or a bare list), [] when absent."""
    data = _read(path)
    if data is None:
        return []
    rows = data[key] if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise TypeError(f"seed file: {key!r} must be a list")
    return rows


def realm_subs(realm_file: Path = REALM_FILE) -> dict[str, str]:
    """username → fixed Keycloak user id."""
    realm = _read(realm_file) or {}
    return {u["username"]: u["id"] for u in realm.get("users", []) if "id" in u}


def persona_list(data_dir: Path = DATA_DIR) -> list[dict[str, Any]]:
    out = []
    for pid in PERSONAS:
        profile = _read(data_dir / "personas" / pid / "profile.json")
        if profile:
            user = profile.get("user", profile)
            out.append({"id": pid, "name": user["name"], "tagline": profile.get("tagline", "")})
    return out


def _at(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _json_items(items: Any) -> Any:
    """Items for the JSONB column: Decimal amounts become JSON numbers."""
    if items is None:
        return None
    return [
        {k: float(v) if isinstance(v, Decimal) else v for k, v in item.items()} for item in items
    ]


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
    db.add_all(m.Merchant(**row) for row in _rows(data_dir / "merchants.json", "merchants"))
    db.add_all(m.Product(**row) for row in _rows(data_dir / "products.json", "products"))
    await db.flush()


async def seed_persona(db: AsyncSession, pid: str, sub: str, data_dir: Path = DATA_DIR) -> int:
    folder = data_dir / "personas" / pid
    p = _read(folder / "profile.json")
    who = p.get("user", p)
    user = await users.create(
        db,
        keycloak_sub=sub,
        name=who["name"],
        age=who.get("age"),
        language=who.get("language", "ro"),
        city=who.get("city"),
    )
    uid = user.id
    await users.update(db, uid, household_scale=Decimal(str(p.get("household_scale", 1))))
    if p.get("onboarded", pid != "alex"):
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
            soft=goal.get("soft", not goal.get("hard_deadline", False)),
        )
        goal_pot = await pots.goal_pot(db, uid)
        saved = goal.get("saved") or (p.get("goal_pot") or {}).get("saved")
        if goal_pot and saved:
            await pots.add_saved(db, uid, goal_pot.id, Decimal(str(saved)))
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
    for raw in _rows(folder / "facts.json", "facts"):
        sigs = raw.pop("signatures", None)
        fact = await life_facts.create(
            db, uid, dm.LifeFactDraft.model_validate({"source": FactSource.SEED, **raw})
        )
        if fact.id is None:
            raise RuntimeError("seed: the saved fact has no id")
        made = (
            [dm.Signature(**s) for s in sigs]
            if sigs is not None
            else ports.signatures_for_fact(fact, None)
        )
        await signatures.replace_for_fact(db, uid, fact.id, made)
    for raw in _rows(folder / "rules.json", "rules"):
        await pattern_rules.create(
            db, uid, dm.PatternRule.model_validate({"created_at": clock.now(), **raw})
        )
    history = []
    for raw in _rows(folder / "transactions.json", "transactions"):
        amount = Decimal(str(raw["amount"]))
        note = raw.get("annotation") or {}  # danutu's E12 shape
        history.append(
            dict(
                user_id=uid,
                amount=amount,
                direction=raw.get("direction", "debit"),
                occurred_at=datetime.fromisoformat(raw["occurred_at"]),
                merchant_raw=raw["merchant_raw"],
                category=raw.get("category"),
                items=_json_items(raw.get("items")),
                mcc=str(raw["mcc"]) if raw.get("mcc") is not None else None,
                description=raw.get("description"),
                source=TransactionSource.SEED,
                status=TransactionStatus.RESOLVED,
                processed_at=clock.now(),
                effective_amount=Decimal(
                    str(note.get("effective_amount", raw.get("effective_amount", amount)))
                ),
                purpose=note.get("purpose", raw.get("purpose")),
                beneficiary=note.get("beneficiary", raw.get("beneficiary", "self")),
                annotation_source=note.get(
                    "source", raw.get("annotation_source", AnnotationSource.AUTO)
                ),
                explanation=note.get("label", raw.get("explanation")),
                decision="auto",
            )
        )
    if history:  # one Core bulk INSERT: Elena's 5 000+ rows as ORM objects take seconds to flush
        await db.execute(insert(m.Base.metadata.tables[m.Transaction.__tablename__]), history)
    await db.flush()
    await seed_extras(db, uid, folder)
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
    elif goal:
        # danutu's E13: the "last week" snapshot is a real forecast as of a week ago (history up
        # to that day; plan version 0), so Scene A's "față de săptămâna trecută" is computed.
        last_week = clock.today() - timedelta(days=7)
        with clock.use_clock(FixedClock(datetime.combine(last_week, time(9, 0), tzinfo=BUCHAREST))):
            await ports.forecast_goal(db, uid, 0)
    plan = await ports.recompute_plan(db, uid, reason="seed")
    if plan is not None:
        await ports.forecast_goal(db, uid, plan.version)
    return uid


async def seed_extras(db: AsyncSession, uid: int, folder: Path) -> None:
    """The optional `extras.json`: rows for the tables the E12 generator doesn't fill."""
    extras = _read(folder / "extras.json")
    if not extras:
        return
    pot_ids = {
        pot.name: pot.id for pot in await db.scalars(select(m.Pot).where(m.Pot.user_id == uid))
    }
    db.add_all(
        m.Transfer(
            user_id=uid,
            pot_id=pot_ids[t["pot"]],
            amount=Decimal(str(t["amount"])),
            kind=t["kind"],
            created_at=_at(t["created_at"]),
        )
        for t in extras.get("transfers", [])
    )
    db.add_all(
        m.Receivable(
            user_id=uid,
            amount=Decimal(str(r["amount"])),
            debtor_label=r["debtor_label"],
            people_count=r.get("people_count"),
            amount_each=Decimal(str(r["amount_each"])) if r.get("amount_each") else None,
            expected_by=date.fromisoformat(r["expected_by"]),
            status=r["status"],
            requested_at=_at(r.get("requested_at")),
            paid_at=_at(r.get("paid_at")),
            created_at=_at(r["created_at"]),
        )
        for r in extras.get("receivables", [])
    )
    db.add_all(
        m.LifeEvent(
            user_id=uid,
            name=e["name"],
            date=date.fromisoformat(e["date"]),
            est_cost=Decimal(str(e["est_cost"])),
            type=e["type"],
            source=FactSource.SEED,
            status=e["status"],
        )
        for e in extras.get("life_events", [])
    )
    db.add_all(
        m.Slip(
            user_id=uid,
            date=date.fromisoformat(s["date"]),
            amount_over=Decimal(str(s["amount_over"])),
            reason=s["reason"],
            detail=s.get("detail"),
            recurring=s.get("recurring", False),
        )
        for s in extras.get("slips", [])
    )
    db.add_all(
        m.Reflection(
            user_id=uid,
            week_start=date.fromisoformat(r["week_start"]),
            motivation=r.get("motivation"),
            answer=r.get("answer"),
            reason=r.get("reason"),
        )
        for r in extras.get("reflections", [])
    )
    db.add_all(
        m.Message(
            user_id=uid,
            role=msg["role"],
            content=msg["content"],
            quick_replies=msg.get("quick_replies") or [],
            input_mode=msg.get("input_mode"),
            speak=msg.get("speak", False),
            speak_text=msg.get("speak_text"),
            created_at=_at(msg["created_at"]),
        )
        for msg in extras.get("messages", [])
    )
    db.add_all(
        m.Notification(
            user_id=uid,
            type=n["type"],
            title=n["title"],
            body=n["body"],
            read=n.get("read", False),
            opens_chat=n.get("opens_chat", False),
            created_at=_at(n["created_at"]),
        )
        for n in extras.get("notifications", [])
    )
    await db.flush()


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
