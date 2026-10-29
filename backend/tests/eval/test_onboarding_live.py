"""A8 live eval row (`uv run pytest -m live tests/eval/test_onboarding_live.py`). Costs money.

The demo's rich onboarding message (arch F8) with the real system parts, snapshot and tool list:
Claude should call every collecting tool in the first turn (D46: set_goal with the motivation),
before `complete_onboarding`. One request. Skips without a configured provider.
"""

from datetime import date

import pytest

from app.agent.llm import LLM
from app.agent.loop import system_parts
from app.agent.snapshot import render_snapshot
from app.agent.tools import ToolState, tools_for
from app.config import Settings
from tests.builders import ctx

pytestmark = pytest.mark.live

RICH_MESSAGE = (
    "Vreau să strâng 3.000 de lei până la 1 august 2027, ca să merg la mare cu prietenii. "
    "Iau 2.400 de lei de la cafenea pe 10 și 500 de la părinți pe 1; chiria e 900 pe 5, "
    "telefonul 50 pe 20. Sunt barista part-time și studentă, stau cu o colegă în Iași."
)


def _configured(settings: Settings) -> bool:
    if settings.LLM_PROVIDER == "bedrock":
        return settings.AWS_BEARER_TOKEN_BEDROCK is not None or (
            settings.AWS_ACCESS_KEY_ID is not None
        )
    return settings.ANTHROPIC_API_KEY is not None


async def test_live_the_rich_message_calls_every_collecting_tool() -> None:
    settings = Settings()
    if not _configured(settings):
        pytest.skip("no LLM provider configured: live test skipped")
    fresh = ctx(user_id=1, as_of=date(2026, 10, 29))
    llm = LLM.from_settings(settings)
    try:
        reply = await llm.create(
            system_parts("onboarding", render_snapshot(fresh, "onboarding")),
            [{"role": "user", "content": RICH_MESSAGE}],
            tools_for(ToolState(has_active_goal=False), "onboarding"),
        )
    finally:
        await llm.aclose()

    calls = [b for b in reply.content if b.type == "tool_use"]
    names = [b.name for b in calls]
    assert reply.stop_reason == "tool_use"
    assert {"set_goal", "add_income_source", "add_fixed_cost", "add_life_fact"} <= set(names)
    assert names.count("add_income_source") == 2
    assert names.count("add_fixed_cost") == 2
    [goal] = [b.input for b in calls if b.name == "set_goal"]
    assert isinstance(goal, dict)
    assert goal.get("motivation")
    assert "complete_onboarding" not in names  # only after the results come back
