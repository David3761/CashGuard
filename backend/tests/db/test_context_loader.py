"""B4: load_user_context (the AI's and the engine's view of one user)."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import event

from app.agent import snapshot
from app.db import models as m
from app.services import context_loader
from app.services.context_loader import load_user_context
from tests import factories as f

TODAY = date(2026, 6, 15)


async def test_every_field_is_filled_for_a_full_user(db):
    u = await f.everything(db)
    tx = (
        await db.execute(m.Transaction.__table__.select().where(m.Transaction.user_id == u.id))
    ).first()
    await db.execute(
        m.Transaction.__table__.update().where(m.Transaction.id == tx.id).values(status="resolved")
    )
    ctx = await load_user_context(db, u.id, TODAY)
    assert ctx.profile.id == u.id and ctx.as_of == TODAY  # our UserContext: as_of
    assert ctx.account.current_balance == Decimal("5200.00")
    assert ctx.goal is not None and ctx.goal_pot is not None and ctx.goal_pot in ctx.pots
    assert len(ctx.income_sources) == len(ctx.fixed_costs) == len(ctx.life_events) == 1
    assert len(ctx.receivables) == 1 and len(ctx.facts) == 1 and len(ctx.signatures) == 1
    assert len(ctx.rules) == 1 and len(ctx.transactions) == 1 and len(ctx.agent_events) == 1
    assert ctx.plan is not None and ctx.plan.version == 1
    assert ctx.forecast is not None and ctx.forecast.probability == 0.78
    assert list(ctx.baselines) == ["groceries"]
    with pytest.raises(ValidationError):
        ctx.today = TODAY  # frozen


async def test_exclusions(db):
    u, other = await f.user(db), await f.user(db)
    for status in ("hypothesis", "rejected"):
        db.add(
            m.LifeFact(
                user_id=u.id,
                type="pet",
                value={"kind": "câine"},
                source="inferred",
                status=status,
                confidence=Decimal("0.5"),
            )
        )
    db.add(
        m.LifeFact(
            user_id=u.id,
            type="occupation",
            value={"title": "x"},
            source="seed",
            valid_to=TODAY - timedelta(days=1),
            valid_from=date(2026, 1, 1),
        )
    )
    old = datetime.fromisoformat("2025-12-01T12:00:00+02:00")
    await f.transaction(db, u.id, status="resolved", occurred_at=old)  # > 180 days
    await f.transaction(db, u.id, status="unresolved")
    await f.transaction(db, u.id, status="failed")
    await f.transaction(db, other.id, status="resolved")
    await db.flush()
    ctx = await load_user_context(db, u.id, TODAY)
    assert ctx.facts == () and [h.status for h in ctx.hypotheses] == ["hypothesis"]
    assert ctx.transactions == () and ctx.goal is None and ctx.plan is None
    assert ctx.account.current_balance == Decimal("0")  # no account row yet → zero


async def test_another_users_data_never_appears(db):
    a, b = await f.everything(db), await f.everything(db)
    ctx = await load_user_context(db, a.id, TODAY)
    assert ctx.profile.id == a.id
    assert all(p.id != 0 for p in ctx.pots)
    other = await load_user_context(db, b.id, TODAY)
    assert {p.id for p in ctx.pots}.isdisjoint({p.id for p in other.pots})


async def test_question_budget_counts_todays_questions(db):
    u = await f.everything(db)
    await db.execute(
        m.AgentEvent.__table__.update()
        .where(m.AgentEvent.user_id == u.id)
        .values(status="asked", asked_at=datetime.fromisoformat("2026-06-15T13:06:00+03:00"))
    )
    ctx = await load_user_context(db, u.id, TODAY)
    assert ctx.questions_asked_today == 1


async def test_statement_budget(db, engine):
    u = await f.everything(db)
    count = {"n": 0}

    def on_exec(*_):
        count["n"] += 1

    sync_engine = engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", on_exec)
    try:
        await load_user_context(db, u.id, TODAY)
    finally:
        event.remove(sync_engine, "before_cursor_execute", on_exec)
    assert count["n"] <= 25  # 20 + the 5 snapshot extras: one bounded query each, no N+1


def _product(slug: str) -> m.Product:
    return m.Product(
        id=slug, name=slug, kind="savings_account", rate=Decimal("0.05"), liquidity="instant",
        min_months=0, max_months=12,
    )  # fmt: skip


async def _history(db, user_id: int, *, days: int, reason: str = "livrări") -> None:
    """`days` daily ledger rows, slips and weekly reflections ending on TODAY, plus one of each
    after TODAY (a sim date before the seeded data must not see the future)."""
    for back in range(-1, days):
        day = TODAY - timedelta(days=back)
        db.add(
            m.DayLedger(user_id=user_id, date=day, budget=Decimal("100"), spent=Decimal(abs(back)))
        )
        db.add(m.Slip(user_id=user_id, date=day, amount_over=Decimal(abs(back)), reason=reason))
        week = TODAY - timedelta(days=TODAY.weekday() + 7 * back)
        db.add(m.Reflection(user_id=user_id, week_start=week, motivation=3, answer=f"w{back}"))
    await db.flush()


def test_the_bounds_are_the_snapshots():
    assert context_loader.RECENT_DAYS == snapshot.RECENT_DAYS
    assert context_loader.MAX_HISTORY == snapshot.MAX_HISTORY


async def test_the_snapshot_extras_are_filled_and_bounded(db):
    u = await f.user(db)
    await _history(db, u.id, days=30)
    db.add(m.Slip(user_id=u.id, date=TODAY, amount_over=Decimal("1")))  # no reason: left out
    db.add(m.LifeProfile(user_id=u.id, data={"what_works": ["gătit acasă"]}))
    db.add_all([_product("cg_b"), _product("cg_a")])
    await db.flush()
    ctx = await load_user_context(db, u.id, TODAY)
    days = [d.date for d in ctx.recent_days]  # the last 14 days up to TODAY, oldest first
    assert days == [TODAY - timedelta(days=n) for n in range(13, -1, -1)]
    assert [s.date for s in ctx.slips] == [TODAY - timedelta(days=n) for n in range(4, -1, -1)]
    assert all(s.reason == "livrări" for s in ctx.slips)
    weeks = [r.week_start for r in ctx.reflections]
    assert len(weeks) == 5 and weeks == sorted(weeks) and weeks[-1] <= TODAY
    assert [r.answer for r in ctx.reflections] == ["w4", "w3", "w2", "w1", "w0"]
    assert ctx.life_notes == {"what_works": ["gătit acasă"]}
    ids = [p.id for p in ctx.products]
    assert {"cg_a", "cg_b"} <= set(ids) and ids == sorted(ids)
    text = snapshot.render_snapshot(ctx, "chat", None)
    assert text.count("\n- slip ") == 5 and text.count("\n- reflection week of ") == 5
    assert "[product cg_a]" in text and '"what_works"' in text


async def test_the_extras_are_the_users_own(db):
    a, b = await f.user(db), await f.user(db)
    await _history(db, b.id, days=10, reason="al altcuiva")
    db.add(m.LifeProfile(user_id=b.id, data={"secret": "b"}))
    await db.flush()
    ctx = await load_user_context(db, a.id, TODAY)
    assert ctx.recent_days == ctx.slips == ctx.reflections == ()
    assert ctx.life_notes == {}
    other = await load_user_context(db, b.id, TODAY)
    assert len(other.slips) == 5 and other.life_notes == {"secret": "b"}


async def test_blank_and_long_texts_are_normalised(db):
    u = await f.user(db)
    db.add_all(
        [
            m.Slip(user_id=u.id, date=TODAY, amount_over=Decimal("5"), reason="  "),
            m.Slip(
                user_id=u.id, date=TODAY, amount_over=Decimal("7"), reason="haine", detail="x" * 900
            ),
            m.Reflection(user_id=u.id, week_start=TODAY, answer="", reason="r" * 900),
        ]
    )
    await db.flush()
    ctx = await load_user_context(db, u.id, TODAY)
    assert [(s.reason, len(s.detail or "")) for s in ctx.slips] == [("haine", 500)]
    (r,) = ctx.reflections
    assert r.answer is None and r.reason == "r" * 300
