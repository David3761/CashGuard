"""B2 step 4: life-context tables, the golden schema, enum CHECKs everywhere, cascades."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select, text

from app.db import models as m
from app.domain import enums as e
from tests import factories as f
from tests.db.test_schema_core import accepted, rejected

# Copied from arch §4 (4.1 tables, 4.2 additions, 4.4 tables + column additions, 6.7
# plan_preferences) + the two B2 additions: users.city, agent_events.event_date.
GOLDEN_SCHEMA = {
    "users": "id name age coach_style timezone created_at keycloak_sub onboarded_at language "
    "household_scale city",
    "accounts": "user_id current_balance savings_pot",
    "income_sources": "id user_id source amount day_of_month",
    "fixed_costs": "id user_id name amount day_of_month",
    "goals": "id user_id amount deadline motivation status created_at",
    "life_events": "id user_id name date est_cost type source status",
    "life_profile": "user_id data updated_at",
    "transactions": "id user_id amount merchant category occurred_at status attempts locked_at "
    "processed_at error source created_at merchant_raw merchant_id mcc items description "
    "direction effective_amount purpose beneficiary annotation_source annotation_confidence "
    "explanation life_fit anomaly_score unexplained decision matched_fact_id matched_rule_id "
    "pot_id receivable_id",
    "day_ledger": "user_id date budget spent status",
    "plans": "id user_id version created_at feasible payload reason trigger_ref",
    "slips": "id user_id date amount_over reason detail recurring",
    "reflections": "id user_id week_start motivation answer reason",
    "agent_events": "id user_id type payload status created_at handled_at ref_transaction_id "
    "asked_at answered_at event_date",
    "messages": "id user_id role content quick_replies created_at input_mode speak speak_text "
    "agent_event_id ref_transaction_id action_cards",
    "notifications": "id user_id type title body read opens_chat created_at agent_event_id "
    "message_id",
    "products": "id name rate liquidity description kind min_months max_months mock",
    "sim_clock": "id today",
    "plan_preferences": "user_id weekday_weights pinned_days category_caps buffer_pct updated_at",
    "transfers": "id user_id amount created_at undone_at kind pot_id income_transaction_id",
    "agent_runs": "id user_id trigger model started_at finished_at iterations status error",
    "tool_calls": "id run_id user_id tool_name input output status created_at",
    "life_facts": "id user_id type value text source status confidence persistence valid_from "
    "valid_to evidence created_at updated_at",
    "spending_signatures": "id user_id fact_id effect category merchant_hints item_keywords "
    "amount_min amount_max multiplier time_window expected_date expected_amount "
    "replacement_cycle_days purpose strength origin active created_at",
    "pattern_rules": "id user_id kind match outcome confidence hits misses source active "
    "created_at last_hit_at",
    "receivables": "id user_id transaction_id amount debtor_label people_count amount_each "
    "expected_by status requested_at paid_at created_at",
    "pots": "id user_id name kind goal_id life_event_id fact_id target saved deadline "
    "monthly_contribution status created_at",
    "goal_forecasts": "id user_id goal_id plan_version sim_date computed_at probability p10 p50 "
    "p90 expected_reach_date drivers options is_weekly_snapshot reason",
    "category_baselines": "user_id category personal_median personal_mad n prior_median "
    "household_multiplier expected_median monthly_expected updated_at",
    "merchants": "id canonical_name aliases category mcc typical_basket multi_category",
}

# Every column holding a fixed-list value, and the list it must be checked against.
ENUM_COLUMNS = {
    ("users", "language"): e.Language,
    ("users", "coach_style"): e.CoachStyle,
    ("goals", "status"): e.GoalStatus,
    ("life_events", "type"): e.LifeEventType,
    ("life_events", "status"): e.LifeEventStatus,
    ("products", "kind"): e.ProductKind,
    ("products", "liquidity"): e.Liquidity,
    ("transactions", "status"): e.TransactionStatus,
    ("transactions", "source"): e.TransactionSource,
    ("transactions", "direction"): e.Direction,
    ("transactions", "category"): e.Category,
    ("transactions", "purpose"): e.Purpose,
    ("transactions", "beneficiary"): e.Beneficiary,
    ("transactions", "annotation_source"): e.AnnotationSource,
    ("transactions", "decision"): e.Decision,
    ("day_ledger", "status"): e.LedgerStatus,
    ("transfers", "kind"): e.TransferKind,
    ("agent_events", "type"): e.AgentEventType,
    ("agent_events", "status"): e.AgentEventStatus,
    ("messages", "role"): e.MessageRole,
    ("messages", "input_mode"): e.InputMode,
    ("agent_runs", "trigger"): e.AgentTrigger,
    ("agent_runs", "status"): e.AgentRunStatus,
    ("tool_calls", "status"): e.ToolCallStatus,
    ("life_facts", "type"): e.FactType,
    ("life_facts", "source"): e.FactSource,
    ("life_facts", "status"): e.FactStatus,
    ("life_facts", "persistence"): e.Persistence,
    ("spending_signatures", "effect"): e.SignatureEffect,
    ("spending_signatures", "category"): e.Category,
    ("spending_signatures", "purpose"): e.Purpose,
    ("spending_signatures", "origin"): e.SignatureOrigin,
    ("pattern_rules", "kind"): e.RuleKind,
    ("pattern_rules", "source"): e.RuleSource,
    ("receivables", "status"): e.ReceivableStatus,
    ("pots", "kind"): e.PotKind,
    ("pots", "status"): e.PotStatus,
    ("category_baselines", "category"): e.Category,
    ("merchants", "category"): e.Category,
}

GLOBAL_TABLES = {"products", "sim_clock", "merchants"}  # not owned by a user


async def test_golden_schema_matches_arch_doc(db):
    rows = await db.execute(
        text(
            "select table_name, column_name from information_schema.columns "
            "where table_schema = current_schema() and table_name <> 'alembic_version'"
        )
    )
    actual: dict[str, set[str]] = {}
    for table, column in rows:
        actual.setdefault(table, set()).add(column)
    expected = {table: set(cols.split()) for table, cols in GOLDEN_SCHEMA.items()}
    assert actual == expected


async def test_every_enum_column_has_a_check_listing_every_value(db):
    rows = await db.execute(
        text("select conname, pg_get_constraintdef(oid) from pg_constraint where contype = 'c'")
    )
    checks = dict(rows.all())
    for (table, column), enum in ENUM_COLUMNS.items():
        definition = checks.get(f"ck_{table}_{column}")
        assert definition is not None, f"{table}.{column} has no CHECK"
        for member in enum:
            assert f"'{member.value}'" in definition, f"{table}.{column} misses {member.value}"


async def test_every_user_foreign_key_cascades(db):
    rows = await db.execute(
        text(
            "select conrelid::regclass::text, confdeltype from pg_constraint "
            "where contype = 'f' and confrelid = 'users'::regclass"
        )
    )
    fks = dict(rows.all())
    assert set(fks) == set(GOLDEN_SCHEMA) - GLOBAL_TABLES - {"users"}
    assert set(fks.values()) == {"c"}


async def test_deleting_a_user_removes_every_row_it_owns(db):
    victim, bystander = await f.everything(db), await f.everything(db)
    owned = sorted(set(GOLDEN_SCHEMA) - GLOBAL_TABLES - {"users"})
    for table in owned:
        n = await db.scalar(
            text(f"select count(*) from {table} where user_id = :u"), {"u": victim.id}
        )
        assert n >= 1, f"factory left {table} empty"
    await db.execute(delete(m.User).where(m.User.id == victim.id))
    for table in owned:
        assert (
            await db.scalar(
                text(f"select count(*) from {table} where user_id = :u"), {"u": victim.id}
            )
            == 0
        ), table
        assert (
            await db.scalar(
                text(f"select count(*) from {table} where user_id = :u"), {"u": bystander.id}
            )
            >= 1
        ), table


def fact(user_id, **kw):
    return m.LifeFact(
        user_id=user_id,
        **({"type": "occupation", "source": "chat", "value": {"title": "analist sportiv"}} | kw),
    )


async def test_life_fact_defaults(db):
    u = await f.user(db)
    row = await accepted(db, fact(u.id))
    await db.refresh(row)
    assert (row.status, row.persistence, row.evidence) == ("confirmed", "permanent", [])


@pytest.mark.parametrize(
    "kw",
    [
        {"type": "religion"},
        {"source": "rumour"},
        {"status": "maybe"},
        {"persistence": "forever"},
        {"confidence": Decimal("1.01")},
        {"confidence": Decimal("-0.1")},
        {"valid_from": date(2026, 7, 31), "valid_to": date(2026, 7, 1)},
        {"persistence": "temporary"},  # temporary needs valid_to
    ],
)
async def test_life_fact_invalid_rows_rejected(db, kw):
    u = await f.user(db)
    await rejected(db, fact(u.id, **kw))


async def test_life_fact_temporary_with_window_ok(db):
    u = await f.user(db)
    await accepted(
        db,
        fact(
            u.id,
            type="household_member",
            value={"role": "adult"},
            persistence="temporary",
            valid_from=date(2026, 7, 1),
            valid_to=date(2026, 7, 31),
        ),
    )


def signature(user_id, fact_id, **kw):
    return m.SpendingSignature(
        user_id=user_id,
        fact_id=fact_id,
        **(
            {
                "effect": "explains",
                "category": "electronics",
                "purpose": "work_tool",
                "origin": "library",
                "strength": Decimal("0.9"),
            }
            | kw
        ),
    )


@pytest.mark.parametrize(
    "kw",
    [
        {"effect": "predicts"},
        {"category": "luxury"},
        {"purpose": "good_purchase"},
        {"origin": "guess"},
        {"strength": Decimal("1.2")},
        {"multiplier": Decimal("0")},
        {"amount_min": Decimal("9000"), "amount_max": Decimal("1500")},
        {"replacement_cycle_days": 0},
    ],
)
async def test_signature_invalid_rows_rejected(db, kw):
    u = await f.user(db)
    fa = await accepted(db, fact(u.id))
    await rejected(db, signature(u.id, fa.id, **kw))


async def test_signature_keeps_hints_and_window(db):
    u = await f.user(db)
    fa = await accepted(db, fact(u.id))
    s = await accepted(
        db,
        signature(
            u.id,
            fa.id,
            merchant_hints=["eMAG", "Altex"],
            item_keywords=["televizor", "TV"],
            amount_min=Decimal("1500"),
            amount_max=Decimal("9000"),
            replacement_cycle_days=900,
            time_window={"weekdays": [5], "from": "12:00"},
        ),
    )
    await db.refresh(s)
    assert s.active is True and s.item_keywords == ["televizor", "TV"]


async def test_deleting_a_fact_removes_its_signatures(db):
    u = await f.user(db)
    fa = await accepted(db, fact(u.id))
    await accepted(db, signature(u.id, fa.id))
    await db.execute(delete(m.LifeFact).where(m.LifeFact.id == fa.id))
    count = select(func.count()).select_from(m.SpendingSignature)
    assert await db.scalar(count.where(m.SpendingSignature.user_id == u.id)) == 0


@pytest.mark.parametrize(
    "kw", [{"kind": "ignore"}, {"source": "magic"}, {"confidence": Decimal("2")}]
)
async def test_pattern_rule_invalid_rows_rejected(db, kw):
    u = await f.user(db)
    await rejected(
        db,
        m.PatternRule(
            user_id=u.id,
            **(
                {"kind": "classify", "source": "answer", "match": {}, "confidence": Decimal("0.7")}
                | kw
            ),
        ),
    )


async def test_pattern_rule_defaults(db):
    u = await f.user(db)
    r = await accepted(
        db,
        m.PatternRule(
            user_id=u.id,
            kind="suppress",
            source="explicit",
            match={"category": "restaurants", "amount_max": 30},
            confidence=Decimal("0.9"),
        ),
    )
    await db.refresh(r)
    assert (r.hits, r.misses, r.active, r.outcome) == (0, 0, True, {})


def receivable(user_id, **kw):
    return m.Receivable(
        user_id=user_id,
        **(
            {"amount": Decimal("400"), "debtor_label": "colegi", "expected_by": date(2026, 6, 29)}
            | kw
        ),
    )


@pytest.mark.parametrize(
    "kw", [{"amount": Decimal("0")}, {"status": "forgotten"}, {"people_count": 0}]
)
async def test_receivable_invalid_rows_rejected(db, kw):
    u = await f.user(db)
    await rejected(db, receivable(u.id, **kw))


async def test_receivable_and_transaction_unlink_when_either_is_deleted(db):
    u = await f.user(db)
    tx = await f.transaction(db, u.id)
    rcv = await accepted(
        db, receivable(u.id, transaction_id=tx.id, people_count=4, amount_each=Decimal("100"))
    )
    tx.receivable_id = rcv.id
    await db.flush()
    rcv_id, tx_id = rcv.id, tx.id
    await db.execute(delete(m.Transaction).where(m.Transaction.id == tx_id))
    db.expunge_all()
    assert (await db.get(m.Receivable, rcv_id)).transaction_id is None
    tx2 = await f.transaction(db, u.id, receivable_id=rcv_id)
    tx2_id = tx2.id
    await db.execute(delete(m.Receivable).where(m.Receivable.id == rcv_id))
    db.expunge_all()
    assert (await db.get(m.Transaction, tx2_id)).receivable_id is None


def pot(user_id, **kw):
    return m.Pot(
        user_id=user_id,
        **({"name": "Vacanță august", "kind": "event", "target": Decimal("3000")} | kw),
    )


@pytest.mark.parametrize(
    "kw",
    [
        {"kind": "piggy"},
        {"status": "gone"},
        {"saved": Decimal("-0.01")},
        {"target": Decimal("0")},
        {"monthly_contribution": Decimal("-1")},
    ],
)
async def test_pot_invalid_rows_rejected(db, kw):
    u = await f.user(db)
    await rejected(db, pot(u.id, **kw))


async def test_pot_defaults_and_one_pot_per_goal(db):
    u = await f.user(db)
    g = await f.goal(db, u.id)
    p = await accepted(db, pot(u.id, kind="goal", goal_id=g.id, name="Fond 10.000"))
    await db.refresh(p)
    assert (p.saved, p.monthly_contribution, p.status) == (Decimal("0"), Decimal("0"), "active")
    await rejected(db, pot(u.id, kind="goal", goal_id=g.id, name="Al doilea"))


def forecast(user_id, goal_id, **kw):
    return m.GoalForecast(
        user_id=user_id,
        goal_id=goal_id,
        **(
            {
                "plan_version": 1,
                "sim_date": date(2026, 6, 15),
                "probability": Decimal("0.78"),
                "p10": Decimal("8650"),
                "p50": Decimal("10900"),
                "p90": Decimal("12400"),
            }
            | kw
        ),
    )


@pytest.mark.parametrize(
    "kw",
    [
        {"probability": Decimal("1.01")},
        {"probability": Decimal("-0.01")},
        {"p10": Decimal("11000")},
        {"p90": Decimal("10000")},
    ],
)
async def test_forecast_invalid_rows_rejected(db, kw):
    u = await f.user(db)
    g = await f.goal(db, u.id)
    await rejected(db, forecast(u.id, g.id, **kw))


async def test_forecast_defaults(db, fixed_clock):
    u = await f.user(db)
    g = await f.goal(db, u.id)
    fc = await accepted(db, forecast(u.id, g.id))
    await db.refresh(fc)
    assert fc.is_weekly_snapshot is False and fc.drivers == []
    assert fc.computed_at == fixed_clock.now()


async def test_baseline_one_row_per_user_and_category(db):
    u = await f.user(db)
    await accepted(db, m.CategoryBaseline(user_id=u.id, category="groceries"))
    await rejected(db, m.CategoryBaseline(user_id=u.id, category="groceries"))
    await rejected(db, m.CategoryBaseline(user_id=u.id, category="luxury"))


async def test_merchant_slug_id_unique_name_and_category_check(db):
    await accepted(
        db,
        m.Merchant(
            id="emag",
            canonical_name="eMAG",
            category="electronics",
            aliases=["PAYU*EMAG.RO"],
            multi_category=True,
        ),
    )
    await rejected(db, m.Merchant(id="emag2", canonical_name="eMAG", category="electronics"))
    await rejected(db, m.Merchant(id="x", canonical_name="X", category="luxury"))


async def test_transaction_links_to_merchant_fact_rule_and_pot(db):
    u = await f.user(db)
    await accepted(
        db, m.Merchant(id="mega_image", canonical_name="Mega Image", category="groceries")
    )
    tx = await f.transaction(db, u.id, merchant_id="mega_image")
    assert tx.merchant_id == "mega_image"
    await rejected(
        db,
        m.Transaction(
            user_id=u.id,
            amount=Decimal("1"),
            merchant_raw="x",
            occurred_at=tx.occurred_at,
            merchant_id="no_such_shop",
        ),
    )
