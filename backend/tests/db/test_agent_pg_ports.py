"""The agent's tools on Postgres (`app/agent/pg_ports.py` + `platform.PlatformServices`).

Committed data (`db_committed`): the agent runs in its own units of work, like in the app. The
LLM is always `FakeLLM`; nothing here reaches Claude.
"""

import asyncio
import json
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select

from app import clock
from app.agent import platform
from app.agent.llm import set_llm
from app.agent.loop import run_agent, set_agent_services
from app.agent.proactive import set_proactive_services
from app.db import models as m
from app.db.seed import realm_subs, seed_catalogues, seed_persona
from app.domain.enums import AgentRunStatus, AgentTrigger
from app.pipeline.processor import process_user
from app.services import agent_runs, plans, receivables, signatures, transactions
from app.services.ingest import ingest
from app.ws import manager
from tests.fakes.fake_llm import FakeLLM, end_turn, tool_round, tool_use

D = Decimal
SCENE_A_ANSWER = "am luat și pentru colegi, suntem cinci"


class Sock:
    def __init__(self) -> None:
        self.got: list[dict[str, Any]] = []

    async def send_json(self, data: dict[str, Any]) -> None:
        self.got.append(data)

    def types(self) -> list[str]:
        return [event["type"] for event in self.got]


@pytest.fixture
async def matei(db_committed):
    await seed_catalogues(db_committed)
    uid = await seed_persona(db_committed, "matei", realm_subs()["matei"])
    await db_committed.commit()
    return uid


@pytest.fixture
def sock(matei):
    s = Sock()
    manager.connect(matei, s)
    yield s
    manager.disconnect(matei, s)


async def mega_500(db, uid: int, trigger: str = "chat") -> int:
    tx_id = await ingest(
        db,
        uid,
        {
            "merchant_raw": "MEGA IMAGE 0451 BUCURESTI",
            "amount": D("500"),
            "mcc": "5411",
            "occurred_at": clock.now() - timedelta(minutes=5),
        },
    )
    await db.commit()
    await process_user(uid, trigger)
    return tx_id


async def start_run(db, uid: int) -> int:
    run_id = await agent_runs.start(db, uid, trigger=AgentTrigger.CHAT, model="fake")
    await db.commit()
    return run_id


def tool_results(llm: FakeLLM, request: int) -> list[dict[str, Any]]:
    content = llm.requests[request].messages[-1]["content"]
    assert isinstance(content, list)
    return [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]


async def settle() -> None:
    for _ in range(5):  # push_after_commit sends in a task
        await asyncio.sleep(0)


# ── Scene A: the 500-lei Mega Image answer, end to end ──────────────────────────────────────


async def test_scene_a_annotates_in_postgres_with_a_receivable_and_a_new_plan(
    db_committed, matei, sock
):
    tx_id = await mega_500(db_committed, matei)
    before = await plans.latest(db_committed, matei)
    assert before is not None
    run_id = await start_run(db_committed, matei)
    args = {
        "transaction_id": tx_id,
        "purpose": "on_behalf_of_others",
        "beneficiary": "shared",
        "people_count": 5,
        "others_will_repay": True,
        "debtor_label": "colegi",
    }
    llm = FakeLLM(
        [
            tool_round(tool_use("annotate_transaction", args, tool_use_id="toolu_a1")),
            end_turn("Am notat: 100 lei sunt ai tăi, colegii îți dau 400."),
        ]
    )
    result = await run_agent(
        matei, "chat", SCENE_A_ANSWER, run_id=run_id, llm=llm, services=platform.platform_wiring()
    )
    await settle()

    [tool_result] = tool_results(llm, 1)
    assert not tool_result.get("is_error"), tool_result["content"]
    body = json.loads(tool_result["content"])
    assert body["ok"] is True and body["plan"]
    assert result.text.startswith("Am notat")

    db_committed.expire_all()
    tx = await transactions.get(db_committed, matei, tx_id)
    assert (tx.purpose, tx.beneficiary) == ("on_behalf_of_others", "shared")
    assert tx.effective_amount == D("100.00")
    assert tx.annotation_source == "answer"
    [owed] = await receivables.list_open(db_committed, matei)
    assert (owed.amount, owed.debtor_label, owed.transaction_id) == (D("400.00"), "colegi", tx_id)
    assert owed.people_count == 5 and tx.receivable_id == owed.id
    after = await plans.latest(db_committed, matei)
    assert after is not None and after.version > before.version
    logged = list(await db_committed.scalars(select(m.ToolCall).where(m.ToolCall.run_id == run_id)))
    assert [(c.tool_name, c.status) for c in logged] == [("annotate_transaction", "ok")]
    assert "transaction.annotated" in sock.types() and "receivable.updated" in sock.types()


async def test_an_error_result_rolls_the_tool_call_back(db_committed, matei):
    tx_id = await mega_500(db_committed, matei)
    run_id = await start_run(db_committed, matei)
    # own_amount above the amount: the handler fails after nothing was committed
    args = {
        "transaction_id": tx_id,
        "purpose": "personal",
        "beneficiary": "self",
        "own_amount": 900,
    }
    llm = FakeLLM(
        [
            tool_round(tool_use("annotate_transaction", args, tool_use_id="toolu_e1")),
            end_turn("Nu a mers."),
        ]
    )
    await run_agent(
        matei, "chat", "doar eu", run_id=run_id, llm=llm, services=platform.platform_wiring()
    )
    [tool_result] = tool_results(llm, 1)
    assert tool_result.get("is_error") is True
    db_committed.expire_all()
    tx = await transactions.get(db_committed, matei, tx_id)
    assert tx.effective_amount == D("500.00") and tx.purpose != "personal"
    logged = list(await db_committed.scalars(select(m.ToolCall).where(m.ToolCall.run_id == run_id)))
    assert [c.status for c in logged] == ["error"]


# ── C9: a new life fact propagates ──────────────────────────────────────────────────────────


async def test_add_life_fact_stores_it_and_runs_c9_then_replans(db_committed, matei):
    before = await plans.latest(db_committed, matei)
    assert before is not None
    run_id = await start_run(db_committed, matei)
    args = {
        "type": "household_member",
        "value": {"role": "adult", "relation": "partener"},
        "text": "Locuiesc cu partenera mea.",
        "persistence": "permanent",
    }
    llm = FakeLLM(
        [
            tool_round(tool_use("add_life_fact", args, tool_use_id="toolu_f1")),
            end_turn("Am notat că locuiești cu partenera ta."),
        ]
    )
    await run_agent(
        matei,
        "chat",
        "locuiesc cu partenera",
        run_id=run_id,
        llm=llm,
        services=platform.platform_wiring(),
    )
    [tool_result] = tool_results(llm, 1)
    assert not tool_result.get("is_error"), tool_result["content"]
    body = json.loads(tool_result["content"])
    fact_id = body["fact"]["id"]
    assert isinstance(body["reevaluated_transaction_ids"], list)

    db_committed.expire_all()
    row = await db_committed.get(m.LifeFact, fact_id)
    assert row is not None and row.user_id == matei and row.status == "confirmed"
    stored = await signatures.list_for_fact(db_committed, matei, fact_id)
    assert len(stored) == body["signatures"]
    after = await plans.latest(db_committed, matei)
    assert after is not None and after.version > before.version
    assert after.reason.startswith("fact: household_member")


# ── A7: the pipeline's proactive run ─────────────────────────────────────────────────────────


@pytest.fixture
def installed():
    platform.install()
    yield
    set_agent_services(None)
    set_proactive_services(None)
    set_llm(None)


async def test_a_new_transaction_triggers_a_saved_and_pushed_proactive_question(
    db_committed, matei, sock, installed
):
    question = "Ai dat 500 de lei la Mega Image. Pentru cine a fost?"
    set_llm(FakeLLM([end_turn(question)]))
    tx_id = await mega_500(db_committed, matei, trigger="sim")
    await settle()

    db_committed.expire_all()
    event = await db_committed.scalar(
        select(m.AgentEvent).where(
            m.AgentEvent.user_id == matei, m.AgentEvent.ref_transaction_id == tx_id
        )
    )
    assert event is not None and event.status == "asked"
    msg = await db_committed.scalar(
        select(m.Message).where(m.Message.user_id == matei, m.Message.agent_event_id == event.id)
    )
    assert msg is not None and msg.content == question
    assert msg.role == "assistant" and msg.speak is True and msg.ref_transaction_id == tx_id
    assert len(msg.quick_replies) >= 3
    note = await db_committed.scalar(
        select(m.Notification).where(m.Notification.agent_event_id == event.id)
    )
    assert note is not None and note.opens_chat is True
    assert "assistant.message" in sock.types() and "notification.new" in sock.types()


async def test_a_proactive_run_is_audited_in_agent_runs_with_its_tool_calls(
    db_committed, matei, sock, installed
):
    question = "Ai dat 500 de lei la Mega Image. Pentru cine a fost?"
    set_llm(
        FakeLLM(
            [tool_round(tool_use("get_plan_status", {}, tool_use_id="toolu_p")), end_turn(question)]
        )
    )
    await mega_500(db_committed, matei, trigger="sim")
    await settle()

    db_committed.expire_all()
    [run] = (
        await db_committed.scalars(select(m.AgentRun).where(m.AgentRun.user_id == matei))
    ).all()
    assert run.trigger == AgentTrigger.PROACTIVE and run.status == AgentRunStatus.COMPLETED
    assert run.finished_at is not None and run.error is None
    [call] = (
        await db_committed.scalars(select(m.ToolCall).where(m.ToolCall.run_id == run.id))
    ).all()
    assert call.tool_name == "get_plan_status" and call.status == "ok" and call.user_id == matei
    assert not await agent_runs.is_running(db_committed, matei)  # /chat isn't left busy


async def test_chat_endpoint_run_saves_the_reply_after_a_real_tool_call(
    as_committed_user, db_committed, matei, sock, installed
):
    tx_id = await mega_500(db_committed, matei)
    args = {
        "transaction_id": tx_id,
        "purpose": "on_behalf_of_others",
        "beneficiary": "shared",
        "people_count": 5,
        "others_will_repay": True,
        "debtor_label": "colegi",
    }
    set_llm(
        FakeLLM(
            [
                tool_round(tool_use("annotate_transaction", args, tool_use_id="toolu_c1")),
                end_turn("Gata: 100 lei ai tu, 400 îți dau colegii."),
            ]
        )
    )
    user = await db_committed.get(m.User, matei)
    r = await as_committed_user(user).post("/chat", json={"text": SCENE_A_ANSWER})
    assert r.status_code == 202
    await settle()
    db_committed.expire_all()
    run = await db_committed.get(m.AgentRun, r.json()["run_id"])
    assert run is not None and run.status == AgentRunStatus.COMPLETED
    last = await db_committed.scalar(
        select(m.Message).where(m.Message.user_id == matei).order_by(m.Message.id.desc()).limit(1)
    )
    assert last is not None and last.content.startswith("Gata")
    tx = await transactions.get(db_committed, matei, tx_id)
    assert tx.effective_amount == D("100.00")
    assert "assistant.message" in sock.types() and "plan.updated" in sock.types()


# ── every port against the DB, scoped by user ───────────────────────────────────────────────


async def test_every_port_works_for_its_user_and_hides_the_other_users_rows(db_committed, matei):
    from app.agent.pg_ports import pg_services
    from app.agent.ports import Annotation, ReceivableDraft
    from app.domain.enums import AnnotationSource, PotKind
    from app.services import life_facts, pattern_rules
    from tests import factories as f
    from tests.db.test_services_profile import fails

    other = (await f.user(db_committed)).id
    tx_id = await mega_500(db_committed, matei)
    s = pg_services(db_committed)
    today = clock.today()

    # transactions
    tx = await s.transactions.get(matei, tx_id)
    assert tx.amount == D("500.00")
    assert tx_id in [t.id for t in await s.transactions.list(matei, today, today)]
    assert await s.transactions.list(matei, today, today, "electronics") == []
    owed = await s.receivables.create(
        matei,
        ReceivableDraft(
            debtor_label="colegi",
            amount=D("400"),
            expected_by=today + timedelta(days=7),
            transaction_id=tx_id,
            people_count=5,
            amount_each=D("100"),
        ),
    )
    annotation = Annotation(
        purpose="on_behalf_of_others",
        beneficiary="shared",
        effective_amount=D("100"),
        source=AnnotationSource.ANSWER,
        receivable_id=owed.id,
    )
    tx = await s.transactions.annotate(matei, tx_id, annotation)
    assert (tx.effective_amount, tx.receivable_id) == (D("100.00"), owed.id)
    # receivables
    assert (await s.receivables.get(matei, owed.id)).amount == D("400.00")
    assert [r.id for r in await s.receivables.list_open(matei)] == [owed.id]
    assert (await s.receivables.open_for_transaction(matei, tx_id)).id == owed.id
    assert (await s.receivables.mark_paid(matei, owed.id)).status == "paid"
    second = await s.receivables.create(
        matei, ReceivableDraft(debtor_label="Ana", amount=D("50"), expected_by=today)
    )
    assert (await s.receivables.cancel(matei, second.id)).status == "cancelled"
    assert await s.receivables.open_for_transaction(matei, tx_id) is None
    # pots + set_pot
    pot = await s.pots.create(
        matei, {"name": "Vacanță", "kind": PotKind.EVENT, "target": D("1500"), "saved": D("0")}
    )
    assert (await s.pots.get(matei, pot.id)).name == "Vacanță"
    assert (await s.pots.update(matei, pot.id, {"name": "Mare"})).name == "Mare"
    assert (await s.transactions.set_pot(matei, tx_id, pot.id)).pot_id == pot.id
    assert (await s.pots.close(matei, pot.id)).status == "closed"
    # goals
    goal = await s.goals.active(matei)
    assert goal is not None
    assert (await s.goals.update(matei, goal.id, {"motivation": "Liniște"})).motivation == "Liniște"
    assert await s.goals.active(other) is None
    # life facts + signatures
    fact = (await life_facts.list_active(db_committed, matei, today))[0]
    assert (await s.life_facts.get(matei, fact.id)).id == fact.id
    assert fact.id in [x.id for x in await s.life_facts.list_active(matei)]
    draft = fact.model_dump(exclude={"id", "created_at"})
    updated = await s.life_facts.update(
        matei, fact.id, type(fact).model_validate({**fact.model_dump(), "text": "Altfel spus"})
    )
    assert updated.text == "Altfel spus" and draft
    await s.signatures.replace_for_fact(matei, fact.id, [])
    assert await signatures.list_for_fact(db_committed, matei, fact.id) == []
    assert (await s.life_facts.expire(matei, fact.id, today)).status == "expired"
    hypo = await life_facts.create(
        db_committed,
        matei,
        fact.model_copy(update={"status": "hypothesis", "confidence": 0.5}),
    )
    assert (await s.life_facts.confirm(matei, hypo.id)).status == "confirmed"
    hypo2 = await life_facts.create(
        db_committed, matei, fact.model_copy(update={"status": "hypothesis", "confidence": 0.5})
    )
    assert (await s.life_facts.reject(matei, hypo2.id)).status == "rejected"
    # pattern rules
    rule = (await pattern_rules.list_active(db_committed, matei))[0]
    made = await s.pattern_rules.create(matei, rule.model_copy(update={"id": None}))
    assert made.id is not None and made.id != rule.id
    # records
    inc = await s.income_sources.create(
        matei, {"source": "Bonus", "amount": D("500"), "day_of_month": 20}
    )
    assert (await s.income_sources.update(matei, inc["id"], {"amount": D("600")}))["amount"] == D(
        "600.00"
    )
    assert inc["id"] in [r["id"] for r in await s.income_sources.list(matei)]
    await s.income_sources.remove(matei, inc["id"])
    cost = await s.fixed_costs.create(
        matei, {"name": "Netflix", "amount": D("50"), "day_of_month": 9}
    )
    assert (await s.fixed_costs.get(matei, cost["id"]))["name"] == "Netflix"
    assert (await s.fixed_costs.update(matei, cost["id"], {"day_of_month": 10}))[
        "day_of_month"
    ] == 10
    await s.fixed_costs.remove(matei, cost["id"])
    event = await s.life_events.create(
        matei,
        {
            "name": "Nuntă",
            "date": today + timedelta(days=30),
            "est_cost": D("800"),
            "type": "social",
        },
    )
    assert (await s.life_events.update(matei, event["id"], {"est_cost": D("900")}))[
        "est_cost"
    ] == D("900.00")
    assert (await s.life_events.update(matei, event["id"], {"status": "cancelled"}))[
        "status"
    ] == "cancelled"
    slip = await s.slips.create(matei, {"date": today, "reason": "ieșire", "recurring": False})
    assert slip["amount_over"] >= 0 and (await s.slips.list(matei))[-1]["id"] == slip["id"]
    reflection = await s.reflections.create(matei, {"motivation": 4, "answer": "bine"})
    assert reflection["week_start"].weekday() == 0
    # preferences, profile, events, transfers, users, plans, forecasts, products
    prefs = await s.plan_preferences.get(matei)
    saved = await s.plan_preferences.save(matei, prefs.model_copy(update={"buffer_pct": D("0.15")}))
    assert (await s.plan_preferences.get(matei)).buffer_pct == saved.buffer_pct == D("0.15")
    assert (await s.life_profile.set_note(matei, "ton", "scurt"))["ton"] == "scurt"
    from app.services import agent_events as events_service

    question = (await events_service.pending_for(db_committed, matei))[0]
    assert (await s.agent_events.get(matei, question.id))["id"] == question.id
    await events_service.mark_asked(db_committed, matei, question.id)
    assert (await s.agent_events.open_question_for(matei, tx_id))["id"] == question.id
    assert (await s.agent_events.mark_answered(matei, question.id))["status"] == "answered"
    assert await s.agent_events.open_question_for(matei, tx_id) is None
    assert (await s.agent_events.mark_handled(matei, question.id))["status"] == "answered"
    pot_before = await db_committed.scalar(
        select(m.Pot.saved).where(m.Pot.user_id == matei, m.Pot.kind == "goal")
    )
    transfer = await s.transfers.to_savings(matei, D("100"))
    assert transfer["amount"] == D("100.00") and transfer["kind"] == "manual"
    pot_after = await db_committed.scalar(
        select(m.Pot.saved)
        .where(m.Pot.user_id == matei, m.Pot.kind == "goal")
        .execution_options(populate_existing=True)
    )
    assert pot_after == pot_before + D("100")
    assert (await s.users.mark_onboarded(other))["onboarded_at"] is not None
    assert (await s.plans.latest(matei))["version"] >= 1
    assert await s.plans.latest(other) is None
    assert (await s.forecasts.latest(matei))["probability"] > 0
    assert len(await s.products.list()) > 0
    run_id = await agent_runs.start(db_committed, matei, trigger=AgentTrigger.CHAT, model="fake")
    await db_committed.commit()
    await s.tool_calls.log(matei, run_id, "toolu_x", "get_plan", {"d": today}, '{"ok": true}', "ok")
    logged = await db_committed.scalar(select(m.ToolCall).where(m.ToolCall.run_id == run_id))
    assert logged is not None and logged.output == {"ok": True}
    await db_committed.commit()

    # the other user sees none of it: not_found, like a missing id
    hidden = [
        s.transactions.get(other, tx_id),
        s.transactions.annotate(other, tx_id, annotation),
        s.transactions.set_pot(other, tx_id, pot.id),
        s.receivables.get(other, owed.id),
        s.receivables.cancel(other, owed.id),
        s.receivables.mark_paid(other, owed.id),
        s.receivables.create(
            other,
            ReceivableDraft(
                debtor_label="x", amount=D("1"), expected_by=today, transaction_id=tx_id
            ),
        ),
        s.life_facts.get(other, fact.id),
        s.life_facts.update(other, fact.id, fact),
        s.life_facts.expire(other, fact.id, today),
        s.life_facts.confirm(other, hypo.id),
        s.life_facts.reject(other, hypo.id),
        s.signatures.replace_for_fact(other, fact.id, []),
        s.pots.get(other, pot.id),
        s.pots.update(other, pot.id, {"name": "x"}),
        s.pots.close(other, pot.id),
        s.goals.update(other, goal.id, {"motivation": "x"}),
        s.income_sources.get(other, inc["id"]),
        s.fixed_costs.update(other, cost["id"], {"name": "x"}),
        s.life_events.get(other, event["id"]),
        s.life_events.update(other, event["id"], {"name": "x"}),
        s.slips.get(other, slip["id"]),
        s.slips.remove(other, slip["id"]),
        s.reflections.update(other, reflection["id"], {"answer": "x"}),
        s.agent_events.get(other, question.id),
        s.agent_events.mark_handled(other, question.id),
    ]
    for call in hidden:
        await fails(call, "not_found", 404)
    assert await s.receivables.list_open(other) == []
    assert await s.transactions.list(other, today, today) == []
    assert await s.agent_events.open_question_for(other, tx_id) is None
    assert await s.slips.list(other) == []
