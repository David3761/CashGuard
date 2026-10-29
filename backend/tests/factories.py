"""Insert ORM rows with sensible defaults for db/api tests (`await factories.user(db)`).

Not to be confused with `tests/builders.py` (F2, David G.): those build pure domain objects.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m


async def add[T](db: AsyncSession, row: T) -> T:
    db.add(row)
    await db.flush()
    return row


async def user(db: AsyncSession, **kw: Any) -> m.User:
    defaults: dict[str, Any] = {"name": "Test User", "keycloak_sub": str(uuid.uuid4())}
    return await add(db, m.User(**(defaults | kw)))


async def goal(db: AsyncSession, user_id: int, **kw: Any) -> m.Goal:
    defaults: dict[str, Any] = {
        "amount": Decimal("10000.00"),
        "deadline": date(2026, 12, 31),
        "motivation": "Fond de urgență",
    }
    return await add(db, m.Goal(user_id=user_id, **(defaults | kw)))


async def transaction(db: AsyncSession, user_id: int, **kw: Any) -> m.Transaction:
    defaults: dict[str, Any] = {
        "amount": Decimal("500.00"),
        "merchant_raw": "MEGA IMAGE 0451 BUCURESTI",
        "occurred_at": datetime.fromisoformat("2026-06-15T13:05:00+03:00"),
    }
    return await add(db, m.Transaction(user_id=user_id, **(defaults | kw)))


async def everything(db: AsyncSession) -> m.User:
    """A user with at least one row in every per-user table (cascade tests, B4 loader tests)."""
    u = await user(db, city="București")
    g = await goal(db, u.id)
    tx = await transaction(db, u.id)
    day = date(2026, 6, 15)
    fact = await add(
        db,
        m.LifeFact(
            user_id=u.id,
            type="occupation",
            source="seed",
            value={"title": "junior developer"},
            text="Sunt developer",
        ),
    )
    rule = await add(
        db,
        m.PatternRule(
            user_id=u.id,
            kind="classify",
            source="answer",
            match={"category": "restaurants", "weekdays": [5]},
            outcome={"purpose": "social_connection"},
            confidence=Decimal("0.7"),
        ),
    )
    pot = await add(
        db,
        m.Pot(user_id=u.id, name="Fond 10.000", kind="goal", goal_id=g.id, target=Decimal("10000")),
    )
    rcv = await add(
        db,
        m.Receivable(
            user_id=u.id,
            transaction_id=tx.id,
            amount=Decimal("400"),
            debtor_label="colegi",
            expected_by=date(2026, 6, 29),
        ),
    )
    event = await add(
        db,
        m.AgentEvent(
            user_id=u.id, type="transaction_question", event_date=day, ref_transaction_id=tx.id
        ),
    )
    msg = await add(db, m.Message(user_id=u.id, role="assistant", content="Ce a fost?"))
    run = await add(db, m.AgentRun(user_id=u.id, trigger="chat", model="claude-sonnet-5-5"))
    rows: list[Any] = [
        m.Account(user_id=u.id, current_balance=Decimal("5200")),
        m.IncomeSource(user_id=u.id, source="Salariu", amount=Decimal("7000"), day_of_month=10),
        m.FixedCost(user_id=u.id, name="Chirie", amount=Decimal("2000"), day_of_month=1),
        m.LifeEvent(
            user_id=u.id,
            name="Vacanță",
            date=date(2026, 8, 15),
            est_cost=Decimal("3000"),
            type="trip",
        ),
        m.LifeProfile(user_id=u.id, data={"what_works": ["gătit acasă"]}),
        m.PlanPreferences(user_id=u.id),
        m.DayLedger(user_id=u.id, date=day, budget=Decimal("120")),
        m.Plan(
            user_id=u.id, version=1, feasible=True, payload={"today_budget": 31.2, "feasible": True}
        ),
        m.Slip(user_id=u.id, date=day, amount_over=Decimal("10")),
        m.Reflection(user_id=u.id, week_start=date(2026, 6, 8), motivation=4),
        m.Transfer(user_id=u.id, amount=Decimal("760"), pot_id=pot.id),
        m.Notification(
            user_id=u.id,
            type="overspend",
            title="t",
            body="b",
            agent_event_id=event.id,
            message_id=msg.id,
        ),
        m.ToolCall(run_id=run.id, user_id=u.id, tool_name="get_plan_status", input={}, status="ok"),
        m.SpendingSignature(
            user_id=u.id,
            fact_id=fact.id,
            effect="explains",
            category="electronics",
            purpose="work_tool",
            origin="library",
            strength=Decimal("0.9"),
        ),
        m.GoalForecast(
            user_id=u.id,
            goal_id=g.id,
            plan_version=1,
            sim_date=day,
            probability=Decimal("0.78"),
            p10=Decimal("8650"),
            p50=Decimal("10900"),
            p90=Decimal("12400"),
        ),
        m.CategoryBaseline(
            user_id=u.id,
            category="groceries",
            personal_median=Decimal("85"),
            expected_median=Decimal("85"),
        ),
    ]
    db.add_all(rows)
    tx.matched_fact_id, tx.matched_rule_id, tx.pot_id, tx.receivable_id = (
        fact.id,
        rule.id,
        pot.id,
        rcv.id,
    )
    await db.flush()
    return u
