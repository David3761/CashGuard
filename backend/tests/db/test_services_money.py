"""B3 step 2: money-flow services (transactions, ledger, plans, transfers)."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db import models as m
from app.db.session import unit_of_work
from app.domain.enums import (
    AnnotationSource,
    Beneficiary,
    Category,
    Decision,
    LedgerStatus,
    Purpose,
    TransactionStatus,
    TransferKind,
)
from app.domain.results import DayBudget, Evaluation, PlanResult, QuestionHint
from app.services import ledger, plans, transactions, transfers
from tests import factories as f
from tests.db.test_services_profile import fails, two  # noqa: F401  (fixture)

D = Decimal


def at(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def plan_result(today_budget: str, feasible: bool = True) -> PlanResult:
    return PlanResult(
        today_budget=D(today_budget),
        feasible=feasible,
        next_7_days=(DayBudget(date=date(2026, 6, 16), budget=D("44.70"), weight=1.5),),
    )


# ── transactions ─────────────────────────────────────────────────────────────────────────


async def test_transaction_get_and_list_newest_first(db):
    u = await f.user(db)
    old = await f.transaction(db, u.id, occurred_at=at("2026-06-10T12:00:00+03:00"))
    new = await f.transaction(db, u.id, occurred_at=at("2026-06-15T13:05:00+03:00"))
    t = await transactions.get(db, u.id, new.id)
    assert t.amount == D("500.00") and t.effective_amount == D("500.00")
    assert [x.id for x in await transactions.list_all(db, u.id)] == [new.id, old.id]


async def test_transaction_list_bounds_are_inclusive_bucharest_days(db):
    u = await f.user(db)
    late_utc = await f.transaction(db, u.id, occurred_at=at("2026-06-14T23:30:00+00:00"))  # 15th
    first = await f.transaction(db, u.id, occurred_at=at("2026-06-14T00:00:00+03:00"))
    last = await f.transaction(db, u.id, occurred_at=at("2026-06-15T23:59:00+03:00"))
    await f.transaction(db, u.id, occurred_at=at("2026-06-16T00:00:00+03:00"))  # outside
    await f.transaction(db, u.id, occurred_at=at("2026-06-13T23:59:00+03:00"))  # outside
    got = await transactions.list_all(db, u.id, since=date(2026, 6, 14), until=date(2026, 6, 15))
    assert {x.id for x in got} == {late_utc.id, first.id, last.id}
    only_15 = await transactions.list_all(
        db, u.id, since=date(2026, 6, 15), until=date(2026, 6, 15)
    )
    assert {x.id for x in only_15} == {late_utc.id, last.id}


async def test_transaction_list_by_status(db):
    u = await f.user(db)
    done = await f.transaction(db, u.id, status="resolved")
    await f.transaction(db, u.id)
    got = await transactions.list_all(db, u.id, status=TransactionStatus.RESOLVED)
    assert [x.id for x in got] == [done.id]


async def test_list_effective_only_resolved_oldest_first_by_category(db):
    u = await f.user(db)
    a = await f.transaction(
        db,
        u.id,
        status="resolved",
        category="groceries",
        occurred_at=at("2026-06-01T10:00:00+03:00"),
    )
    b = await f.transaction(
        db,
        u.id,
        status="resolved",
        category="restaurants",
        occurred_at=at("2026-06-02T10:00:00+03:00"),
    )
    for status in ("unresolved", "processing", "failed"):
        await f.transaction(
            db,
            u.id,
            status=status,
            category="groceries",
            occurred_at=at("2026-06-03T10:00:00+03:00"),
        )
    got = await transactions.list_effective(db, u.id, date(2026, 6, 1), date(2026, 6, 30))
    assert [x.id for x in got] == [a.id, b.id]
    groceries = await transactions.list_effective(
        db, u.id, date(2026, 6, 1), date(2026, 6, 30), Category.GROCERIES
    )
    assert [x.id for x in groceries] == [a.id]
    assert await transactions.list_effective(db, u.id, date(2026, 6, 2), date(2026, 6, 2)) == [
        await transactions.get(db, u.id, b.id)
    ]


async def test_save_evaluation_stores_the_reading(db):
    u = await f.user(db)
    t = await f.transaction(db, u.id)
    ev = Evaluation(  # our F2 Evaluation: beneficiary, annotation_source and confidence required
        category=Category.GROCERIES,
        merchant="Mega Image",
        purpose=Purpose.UNKNOWN,
        beneficiary=Beneficiary.SELF,
        annotation_source=AnnotationSource.AUTO,
        confidence=0.5,
        effective_amount=D("500"),
        life_fit=0.10,
        anomaly_score=0.80,
        unexplained=0.72,
        decision=Decision.ASK,
        goal_impact=0.1,
        explanation="~6× coșul obișnuit",
        question_hint=QuestionHint(reason="basket_ratio", params={"ratio": 6}),
    )
    saved = await transactions.save_evaluation(db, u.id, t.id, ev)
    assert (saved.category, saved.decision, saved.purpose) == (
        Category.GROCERIES,
        Decision.ASK,
        Purpose.UNKNOWN,
    )
    assert (saved.life_fit, saved.unexplained, saved.annotation_source) == (
        0.1,
        0.72,
        AnnotationSource.AUTO,
    )
    assert saved.merchant == "Mega Image" and saved.explanation == "~6× coșul obișnuit"


async def test_save_evaluation_rejects_effective_above_amount(db):
    u = await f.user(db)
    t = await f.transaction(db, u.id, amount=D("100"))
    ev = Evaluation(
        category=Category.GROCERIES,
        purpose=Purpose.UNKNOWN,
        beneficiary=Beneficiary.SELF,
        annotation_source=AnnotationSource.AUTO,
        confidence=0.5,
        effective_amount=D("100.01"),
        life_fit=0,
        anomaly_score=0,
        unexplained=0,
        decision=Decision.AUTO,
    )
    await fails(transactions.save_evaluation(db, u.id, t.id, ev), "invalid_effective_amount", 422)


async def test_annotate_answer_500_to_100(db):
    u = await f.user(db)
    t = await f.transaction(db, u.id)
    a = await transactions.annotate(
        db,
        u.id,
        t.id,
        purpose=Purpose.ON_BEHALF_OF_OTHERS,
        beneficiary=Beneficiary.SHARED,
        effective_amount=D("100"),
        source=AnnotationSource.ANSWER,
        explanation="Ai luat și pentru 4 colegi",
        confidence=1.0,
    )
    assert (a.effective_amount, a.amount, a.purpose, a.annotation_source) == (
        D("100.00"),
        D("500.00"),
        Purpose.ON_BEHALF_OF_OTHERS,
        AnnotationSource.ANSWER,
    )


@pytest.mark.parametrize("effective", [D("500.01"), D("-1")])
async def test_annotate_rejects_effective_outside_zero_and_amount(db, effective):
    u = await f.user(db)
    t = await f.transaction(db, u.id)
    await fails(
        transactions.annotate(
            db,
            u.id,
            t.id,
            purpose=Purpose.UNKNOWN,
            beneficiary=Beneficiary.SELF,
            effective_amount=effective,
            source=AnnotationSource.USER_EDIT,
        ),
        "invalid_effective_amount",
        422,
    )


async def test_queue_transitions(db, fixed_clock):
    u = await f.user(db)
    t = await f.transaction(db, u.id, status="processing")
    r = await transactions.mark_resolved(db, u.id, t.id)
    assert r.status == TransactionStatus.RESOLVED
    t2 = await f.transaction(db, u.id, status="processing")
    assert (await transactions.mark_failed(db, u.id, t2.id, "boom")).status == "failed"


async def test_bump_attempts_retries_twice_then_fails(db):
    u = await f.user(db)
    t = await f.transaction(db, u.id, status="processing")
    first = await transactions.bump_attempts(db, u.id, t.id, "engine error")
    assert first.status == TransactionStatus.UNRESOLVED
    await transactions.bump_attempts(db, u.id, t.id, "engine error")
    third = await transactions.bump_attempts(db, u.id, t.id, "engine error again")
    assert third.status == TransactionStatus.FAILED
    row = await db.get(m.Transaction, t.id)
    assert (row.attempts, row.error) == (3, "engine error again")


async def test_set_pot_and_receivable_links(db):
    u = await f.user(db)
    t = await f.transaction(db, u.id)
    pot = m.Pot(user_id=u.id, name="Vacanță", kind="event", target=D("3000"))
    rcv = m.Receivable(
        user_id=u.id, amount=D("400"), debtor_label="colegi", expected_by=date(2026, 6, 29)
    )
    db.add_all([pot, rcv])
    await db.flush()
    assert (await transactions.set_pot(db, u.id, t.id, pot.id)).pot_id == pot.id
    assert (await transactions.set_receivable(db, u.id, t.id, rcv.id)).receivable_id == rcv.id
    assert (await transactions.set_pot(db, u.id, t.id, None)).pot_id is None


async def test_transactions_isolation(two, db):  # noqa: F811
    a, b = two
    t = await f.transaction(db, b.id)
    for call in (
        transactions.get(db, a.id, t.id),
        transactions.annotate(
            db,
            a.id,
            t.id,
            purpose=Purpose.UNKNOWN,
            beneficiary=Beneficiary.SELF,
            effective_amount=D("1"),
            source=AnnotationSource.USER_EDIT,
        ),
        transactions.set_pot(db, a.id, t.id, None),
        transactions.mark_resolved(db, a.id, t.id),
        transactions.bump_attempts(db, a.id, t.id, "x"),
    ):
        await fails(call, "not_found", 404)
    assert await transactions.list_all(db, a.id) == []


# ── ledger ───────────────────────────────────────────────────────────────────────────────


async def test_ledger_get_or_create_update_add_spent(db):
    u = await f.user(db)
    day = date(2026, 6, 15)
    assert await ledger.get(db, u.id, day) is None
    created = await ledger.get_or_create(db, u.id, day)
    assert (created.budget, created.spent, created.status) == (D("0"), D("0"), LedgerStatus.OK)
    assert await ledger.get_or_create(db, u.id, day) == created  # twice → same row
    await ledger.update(db, u.id, day, budget=D("120"))
    assert (await ledger.add_spent(db, u.id, day, D("500"))).spent == D("500.00")
    assert (await ledger.add_spent(db, u.id, day, D("-400"))).spent == D("100.00")  # 500 → 100
    assert (await ledger.add_spent(db, u.id, day, D("-999"))).spent == D("0.00")  # never < 0
    closed = await ledger.update(db, u.id, day, status=LedgerStatus.UNDER)
    assert (closed.budget, closed.status) == (D("120.00"), LedgerStatus.UNDER)


async def test_ledger_add_spent_creates_a_missing_past_day(db):
    u = await f.user(db)
    day = await ledger.add_spent(db, u.id, date(2026, 6, 10), D("85"))
    assert day.spent == D("85.00")


async def test_ledger_between_inclusive_and_isolated(two, db):  # noqa: F811
    a, b = two
    for d in (14, 15, 16):
        await ledger.get_or_create(db, a.id, date(2026, 6, d))
    await ledger.get_or_create(db, b.id, date(2026, 6, 15))
    got = await ledger.between(db, a.id, date(2026, 6, 14), date(2026, 6, 15))
    assert [x.date for x in got] == [date(2026, 6, 14), date(2026, 6, 15)]


# ── plans ────────────────────────────────────────────────────────────────────────────────


async def test_plans_versions_latest_history(db):
    u = await f.user(db)
    assert await plans.latest(db, u.id) is None and await plans.next_version(db, u.id) == 1
    p1 = await plans.save(db, u.id, plan_result("31.20"), reason="seed")
    p2 = await plans.save(
        db,
        u.id,
        plan_result("29.80"),
        reason="Concert",
        trigger_ref={"tool": "add_life_event", "event_id": 42},
    )
    assert (p1.version, p2.version) == (1, 2)
    latest = await plans.latest(db, u.id)
    assert latest is not None
    assert (latest.version, latest.today_budget, latest.previous_today_budget, latest.reason) == (
        2,
        D("29.80"),
        D("31.20"),
        "Concert",
    )
    assert latest.next_7_days[0].budget == D("44.70")
    assert [p.version for p in await plans.history(db, u.id)] == [2, 1]
    assert (await plans.by_version(db, u.id, 1)).today_budget == D("31.20")
    await fails(plans.by_version(db, u.id, 9), "not_found", 404)
    assert await plans.next_version(db, u.id) == 3


async def test_plans_isolation(two, db):  # noqa: F811
    a, b = two
    await plans.save(db, b.id, plan_result("10"), reason="x")
    assert await plans.latest(db, a.id) is None
    await fails(plans.by_version(db, a.id, 1), "not_found")
    assert (await plans.save(db, a.id, plan_result("5"), reason="x")).version == 1


async def test_two_concurrent_plan_saves_get_consecutive_versions(db_committed):
    u = await f.user(db_committed)
    await db_committed.commit()

    async def save(budget: str) -> int:
        async with unit_of_work() as s:
            return (await plans.save(s, u.id, plan_result(budget), reason="race")).version

    assert sorted(await asyncio.gather(save("10"), save("11"))) == [1, 2]


# ── transfers ────────────────────────────────────────────────────────────────────────────


async def test_transfer_create_and_undo_once(db, fixed_clock):
    u = await f.user(db)
    t = await transfers.create(db, u.id, amount=D("760"))
    assert t.kind == TransferKind.MANUAL and t.undone_at is None
    undone = await transfers.undo(db, u.id, t.id)
    assert undone.undone_at == fixed_clock.now()
    await fails(transfers.undo(db, u.id, t.id), "already_undone", 409)
    assert await transfers.get(db, u.id, t.id) == undone


async def test_auto_save_once_per_salary(db):
    u = await f.user(db)
    salary = await f.transaction(db, u.id, amount=D("7000"), direction="credit")
    assert await transfers.for_income(db, u.id, salary.id) is None
    t = await transfers.create(
        db, u.id, amount=D("760"), kind=TransferKind.AUTO_SAVE, income_transaction_id=salary.id
    )
    assert await transfers.for_income(db, u.id, salary.id) == t
    await fails(
        transfers.create(
            db, u.id, amount=D("760"), kind=TransferKind.AUTO_SAVE, income_transaction_id=salary.id
        ),
        "already_saved",
        409,
    )


async def test_transfer_rejects_non_positive_amount(db):
    u = await f.user(db)
    await fails(transfers.create(db, u.id, amount=D("0")), "invalid_amount", 422)


async def test_check_funds_refuses_more_than_the_balance(db):
    u, other = await f.user(db), await f.user(db)
    db.add(m.Account(user_id=u.id, current_balance=D("150.00")))
    await db.flush()
    await transfers.check_funds(db, u.id, D("150.00"))  # all of it is fine
    await fails(transfers.check_funds(db, u.id, D("150.01")), "insufficient_funds", 409)
    await fails(transfers.check_funds(db, other.id, D("1")), "not_found", 404)


async def test_agent_transfer_above_the_balance_writes_nothing(db):
    from app.agent.pg_ports import pg_services

    u = await f.user(db)
    db.add(m.Account(user_id=u.id, current_balance=D("150.00")))
    await db.flush()
    await fails(pg_services(db).transfers.to_savings(u.id, D("200")), "insufficient_funds", 409)
    assert await db.scalar(select(func.count()).where(m.Transfer.user_id == u.id)) == 0
    assert (await db.get(m.Account, u.id, populate_existing=True)).current_balance == D("150.00")


async def test_transfers_isolation(two, db):  # noqa: F811
    a, b = two
    t = await transfers.create(db, b.id, amount=D("5"))
    await fails(transfers.get(db, a.id, t.id), "not_found")
    await fails(transfers.undo(db, a.id, t.id), "not_found")


def test_utc_helper_sanity():
    assert at("2026-06-14T23:30:00+00:00").astimezone(UTC).hour == 23
