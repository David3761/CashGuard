"""A8: live onboarding end to end (F8): A5's onboarding instructions, A4's checklist, the A6 loop,
A3's handlers (D46 set_goal with the motivation, `complete_onboarding`) on the fake services.

The rich demo message (arch F8) carries the goal, the why, the income, the fixed costs and the
life: Claude (FakeLLM, strict) calls every matching tool in one turn, then `complete_onboarding`.
"""

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from anthropic.types.beta import BetaMessageParam

from app.agent.handlers.common import ToolContext
from app.agent.loop import run_agent
from app.agent.ports import LazyContext
from app.agent.prompts import instructions_for
from app.agent.style import find_banned
from app.agent.wiring import AgentWiring
from app.clock import FixedClock, use_clock
from app.domain.enums import FactSource, FactType
from app.domain.user_context import UserContext
from tests.builders import ctx
from tests.fakes.fake_llm import FakeLLM, end_turn, tool_round, tool_use
from tests.fakes.fake_services import FakeLifeFacts, FakeRecords, FakeSignatures, FakeUsers, Harness

RICH_MESSAGE = (
    "Vreau să strâng 3.000 de lei până la 1 august, ca să merg la mare cu prietenii. "
    "Iau 2.400 de lei de la cafenea pe 10 și 500 de la părinți pe 1; chiria e 900 pe 5, "
    "telefonul 50 pe 20. Sunt barista part-time și studentă, stau cu o colegă în Iași."
)
REPLY = (
    "Gata! Azi poți cheltui 31 de lei, și șansa pentru 3.000 de lei până la 1 august e 77%. "
    "Știu că ești barista part-time și studentă și că stai cu o colegă în Iași."
)

GOAL = {"amount": 3000, "deadline": "2027-08-01", "motivation": "la mare cu prietenii"}
INCOME = [
    {"source": "Cafenea (barista)", "amount": 2400, "day_of_month": 10},
    {"source": "Părinți", "amount": 500, "day_of_month": 1},
]
COSTS = [
    {"name": "Chirie", "amount": 900, "day_of_month": 5},
    {"name": "Telefon", "amount": 50, "day_of_month": 20},
]
LIFE = [
    {
        "type": "occupation",
        "value": {"title": "barista", "work_mode": "part_time"},
        "text": "Sunt barista part-time",
        "persistence": "permanent",
    },
    {
        "type": "employment",
        "value": {"kind": "student"},
        "text": "Sunt studentă",
        "persistence": "permanent",
    },
    {
        "type": "housing",
        "value": {"kind": "shared_flat"},
        "text": "Stau cu o colegă",
        "persistence": "permanent",
    },
    {"type": "city", "value": {"name": "Iași"}, "text": "Stau în Iași", "persistence": "permanent"},
]
COLLECT = (
    [("set_goal", GOAL)]
    + [("add_income_source", i) for i in INCOME]
    + [("add_fixed_cost", c) for c in COSTS]
    + [("add_life_fact", f) for f in LIFE]
)


@pytest.fixture(autouse=True)
def _clock() -> Any:
    with use_clock(FixedClock(datetime(2026, 10, 29, 9, 0, tzinfo=UTC))) as c:
        yield c


def fresh() -> UserContext:
    """The live demo account: a profile and an account, nothing else (D30)."""
    return ctx(user_id=1, as_of=date(2026, 10, 29))


def wiring_for(harness: Harness) -> AgentWiring:
    context = fresh()

    async def load_context(user_id: int) -> UserContext:
        return context

    async def load_history(user_id: int, limit: int) -> list[BetaMessageParam]:
        return []

    # the real C4 library behind add_life_fact (LazyContext), the fake engine for D18
    tool_ctx = ToolContext(
        user_id=1, services=harness.services, engine=harness.engine, context=LazyContext()
    )
    return AgentWiring(
        load_context=load_context, tool_context=lambda user_id: tool_ctx, load_history=load_history
    )


def blocks(calls: list[tuple[str, dict[str, Any]]], start: int = 1) -> list[dict[str, Any]]:
    return [tool_use(name, args, tool_use_id=f"toolu_{start + i}") for i, (name, args) in
            enumerate(calls)]  # fmt: skip


def tool_results(fake: FakeLLM, request: int) -> dict[str, tuple[bool, dict[str, Any]]]:
    """tool_use_id → (is_error, the parsed result) of the tool results sent in `request`."""
    content = fake.requests[request].messages[-1]["content"]
    assert isinstance(content, list)
    return {
        block["tool_use_id"]: (bool(block.get("is_error")), json.loads(block["content"]))
        for block in content
        if isinstance(block, dict) and block.get("type") == "tool_result"
    }


async def test_the_rich_message_onboards_in_one_turn_then_completes() -> None:
    harness = Harness(trigger="onboarding")
    fake = FakeLLM(
        [
            tool_round(*blocks(COLLECT)),
            tool_round(tool_use("complete_onboarding", {}, tool_use_id="toolu_99")),
            end_turn(REPLY),
        ]
    )
    result = await run_agent(1, "onboarding", RICH_MESSAGE, llm=fake, services=wiring_for(harness))
    fake.assert_consumed()

    # the run used the onboarding instructions and the fresh checklist, built once (D46)
    first = fake.requests[0]
    assert first.system[1] == instructions_for("onboarding")
    assert (
        "goal MISSING; income MISSING; fixed costs MISSING; life context MISSING"
        in (first.system[2])
    )
    assert "set_goal" in first.tool_names
    assert "update_goal" not in first.tool_names  # no goal yet when the run started
    assert all(r.tools == first.tools for r in fake.requests)

    # every collecting tool succeeded, in the order Claude called them
    collected = tool_results(fake, 1)
    assert [k for k, (failed, _) in collected.items() if failed] == []
    assert list(collected) == [f"toolu_{i}" for i in range(1, len(COLLECT) + 1)]

    # D46: the motivation was saved with the goal, in the same call
    s = harness.services
    goal = s.goals.active(1)
    assert goal is not None
    assert goal.motivation == "la mare cu prietenii"
    assert goal.amount == Decimal("3000")
    income, costs = s.income_sources, s.fixed_costs
    assert isinstance(income, FakeRecords)
    assert isinstance(costs, FakeRecords)
    assert [r["amount"] for r in income.list(1)] == [Decimal("2400"), Decimal("500")]
    assert [r["name"] for r in costs.list(1)] == ["Chirie", "Telefon"]
    facts = s.life_facts.list_active(1)
    assert [f.type for f in facts] == [
        FactType.OCCUPATION,
        FactType.EMPLOYMENT,
        FactType.HOUSING,
        FactType.CITY,
    ]
    assert {f.source for f in facts} == {FactSource.ONBOARDING}
    signatures = s.signatures
    assert isinstance(signatures, FakeSignatures)
    assert set(signatures.by_fact) == {(1, f.id) for f in facts}  # C4 ran for each fact

    # complete_onboarding succeeded: onboarded + the first plan and forecast (D18)
    [(failed, done)] = tool_results(fake, 2).values()
    assert failed is False
    assert done["onboarded"] is True
    assert "plan" in done
    assert "forecast" in done
    users = s.users
    assert isinstance(users, FakeUsers)
    assert users.onboarded == {1}
    name, (user_id, reason, _) = harness.engine.calls[-2]
    assert (name, user_id, reason) == ("recompute_plan", 1, "onboarding completed: first plan")
    assert harness.engine.names()[-1] == "forecast_goal"
    assert result.plan_changed is True
    assert result.text == REPLY
    assert "Știu că" in result.text
    assert find_banned(result.text) == []


async def test_complete_onboarding_too_early_lists_life_context_then_succeeds() -> None:
    harness = Harness(trigger="onboarding")
    money_only = COLLECT[: 1 + len(INCOME) + len(COSTS)]
    fake = FakeLLM(
        [
            tool_round(*blocks(money_only)),
            tool_round(tool_use("complete_onboarding", {}, tool_use_id="toolu_50")),
            tool_round(*blocks([("add_life_fact", LIFE[0])], start=60)),
            tool_round(tool_use("complete_onboarding", {}, tool_use_id="toolu_70")),
            end_turn("Gata! Știu că ești barista part-time."),
        ]
    )
    await run_agent(
        1, "onboarding", "Vreau 3.000 de lei până în august…", llm=fake,
        services=wiring_for(harness),
    )  # fmt: skip
    fake.assert_consumed()

    [(failed, early)] = tool_results(fake, 2).values()
    assert failed is True
    assert early["error"]["code"] == "onboarding_incomplete"
    assert early["error"]["message"].startswith("Still missing: life_context.")
    assert isinstance(harness.services.users, FakeUsers)
    [(failed, late)] = tool_results(fake, 4).values()
    assert failed is False
    assert late["onboarded"] is True
    assert harness.services.users.onboarded == {1}


async def test_onboarding_facts_keep_the_chat_source_outside_onboarding() -> None:
    harness = Harness(trigger="chat")
    fake = FakeLLM([tool_round(*blocks([("add_life_fact", LIFE[0])])), end_turn("Am notat.")])
    await run_agent(1, "chat", "Sunt barista.", llm=fake, services=wiring_for(harness))
    life_facts = harness.services.life_facts
    assert isinstance(life_facts, FakeLifeFacts)
    assert [f.source for f in life_facts.list_active(1)] == [FactSource.CHAT]
