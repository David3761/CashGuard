"""B2 step 2: money flow tables (transactions, day_ledger, plans, slips, reflections, transfers)."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.db import models as m
from tests import factories as f
from tests.db.test_schema_core import accepted, rejected


async def test_transaction_defaults(db, fixed_clock):
    u = await f.user(db)
    tx = await f.transaction(db, u.id)
    await db.refresh(tx)
    assert tx.status == "unresolved"
    assert tx.attempts == 0
    assert tx.direction == "debit"
    assert tx.source == "sim"
    assert tx.effective_amount == tx.amount == Decimal("500.00")  # = amount until annotated
    assert tx.created_at == fixed_clock.now()


@pytest.mark.parametrize("amount", ["0", "-0.01"])
async def test_transaction_amount_must_be_positive(db, amount):
    u = await f.user(db)
    await rejected(
        db,
        m.Transaction(
            user_id=u.id,
            amount=Decimal(amount),
            merchant_raw="x",
            occurred_at=datetime.fromisoformat("2026-06-15T10:00:00+03:00"),
        ),
    )


@pytest.mark.parametrize(
    ("effective", "ok"),
    [
        ("0", True),
        ("100.00", True),
        ("500.00", True),
        ("500.01", False),
        ("-1", False),
    ],
)
async def test_transaction_effective_amount_between_zero_and_amount(db, effective, ok):
    u = await f.user(db)
    row = m.Transaction(
        user_id=u.id,
        amount=Decimal("500.00"),
        merchant_raw="x",
        effective_amount=Decimal(effective),
        occurred_at=datetime.fromisoformat("2026-06-15T10:00:00+03:00"),
    )
    await (accepted(db, row) if ok else rejected(db, row))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "pending"),
        ("direction", "refund"),
        ("source", "bank"),
        ("category", "luxury"),
        ("purpose", "good_purchase"),
        ("beneficiary", "boss"),
        ("annotation_source", "guess"),
        ("decision", "maybe"),
    ],
)
async def test_transaction_unknown_enum_value_rejected(db, field, value):
    u = await f.user(db)
    await rejected(
        db,
        m.Transaction(
            user_id=u.id,
            amount=Decimal("1"),
            merchant_raw="x",
            occurred_at=datetime.fromisoformat("2026-06-15T10:00:00+03:00"),
            **{field: value},
        ),
    )


async def test_transaction_money_round_trips_exactly(db):
    u = await f.user(db)
    tx_id = (await f.transaction(db, u.id, amount=Decimal("0.30"))).id
    db.expunge_all()  # read back from the DB, not the identity map
    stored = await db.scalar(select(m.Transaction.amount).where(m.Transaction.id == tx_id))
    assert stored == Decimal("0.30")


async def test_transaction_items_jsonb_keeps_diacritics_and_quotes(db):
    u = await f.user(db)
    items = [{"name": 'Televizor 65" ăîșț', "qty": 1, "amount": 4500}]
    tx_id = (await f.transaction(db, u.id, items=items)).id
    db.expunge_all()
    assert await db.scalar(select(m.Transaction.items).where(m.Transaction.id == tx_id)) == items


async def test_transaction_queue_indexes_exist(db):
    rows = await db.execute(
        text("select indexdef from pg_indexes where tablename = 'transactions'")
    )
    defs = " ".join(r[0] for r in rows)
    assert "(user_id, status)" in defs
    assert "(user_id, occurred_at)" in defs


async def test_day_ledger_one_row_per_user_and_day(db):
    u = await f.user(db)
    await accepted(db, m.DayLedger(user_id=u.id, date=date(2026, 6, 15), budget=Decimal("120")))
    await rejected(db, m.DayLedger(user_id=u.id, date=date(2026, 6, 15), budget=Decimal("1")))
    await accepted(db, m.DayLedger(user_id=u.id, date=date(2026, 6, 16), budget=Decimal("1")))


async def test_day_ledger_defaults_and_status_check(db):
    u = await f.user(db)
    row = await accepted(db, m.DayLedger(user_id=u.id, date=date(2026, 6, 15)))
    await db.refresh(row)
    assert (row.budget, row.spent, row.status) == (Decimal("0"), Decimal("0"), "ok")
    await rejected(db, m.DayLedger(user_id=u.id, date=date(2026, 6, 17), status="terrible"))


async def test_plan_version_unique_per_user(db):
    a, b = await f.user(db), await f.user(db)
    await accepted(db, m.Plan(user_id=a.id, version=1, feasible=True, payload={}))
    await rejected(db, m.Plan(user_id=a.id, version=1, feasible=True, payload={}))
    await accepted(db, m.Plan(user_id=b.id, version=1, feasible=True, payload={}))


async def test_plan_keeps_reason_and_trigger_ref(db):
    u = await f.user(db)
    ref = {"tool": "annotate_transaction", "transaction_id": 918}
    p = await accepted(
        db,
        m.Plan(
            user_id=u.id,
            version=1,
            feasible=True,
            payload={"today_budget": 31.2},
            reason="Mega Image: 100 lei ai tăi",
            trigger_ref=ref,
        ),
    )
    plan_id = p.id
    db.expunge_all()
    query = select(m.Plan.reason, m.Plan.trigger_ref).where(m.Plan.id == plan_id)
    stored = (await db.execute(query)).one()
    assert stored == ("Mega Image: 100 lei ai tăi", ref)


async def test_slip_and_reflection_rows(db):
    u = await f.user(db)
    await accepted(
        db,
        m.Slip(
            user_id=u.id,
            date=date(2026, 6, 14),
            amount_over=Decimal("85"),
            reason="social",
            recurring=True,
        ),
    )
    await accepted(db, m.Reflection(user_id=u.id, week_start=date(2026, 6, 8), motivation=4))


@pytest.mark.parametrize("motivation", [0, 6])
async def test_reflection_motivation_is_one_to_five(db, motivation):
    u = await f.user(db)
    await rejected(
        db, m.Reflection(user_id=u.id, week_start=date(2026, 6, 8), motivation=motivation)
    )


async def test_transfer_defaults_and_checks(db):
    u = await f.user(db)
    t = await accepted(db, m.Transfer(user_id=u.id, amount=Decimal("760")))
    await db.refresh(t)
    assert t.kind == "manual" and t.undone_at is None
    await rejected(db, m.Transfer(user_id=u.id, amount=Decimal("0")))
    await rejected(db, m.Transfer(user_id=u.id, amount=Decimal("1"), kind="gift"))


async def test_one_auto_save_per_income_transaction(db):
    # payday auto-save must not run twice for the same salary (D37, B8 step 3)
    u = await f.user(db)
    salary = await f.transaction(db, u.id, amount=Decimal("7000"), direction="credit")
    await accepted(
        db,
        m.Transfer(
            user_id=u.id, amount=Decimal("760"), kind="auto_save", income_transaction_id=salary.id
        ),
    )
    await rejected(
        db,
        m.Transfer(
            user_id=u.id, amount=Decimal("760"), kind="auto_save", income_transaction_id=salary.id
        ),
    )
    # manual transfers are not limited
    await accepted(db, m.Transfer(user_id=u.id, amount=Decimal("50")))
    await accepted(db, m.Transfer(user_id=u.id, amount=Decimal("50")))
