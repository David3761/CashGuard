"""A2 live check (`uv run pytest -m live tests/eval/test_tools_live.py`). Costs money.

One tiny request with the full chat tool list: proves the API accepts every schema and that the
strict tools stay within the per-request limits (20 strict tools, 24 optional, 16 union params).
Skips without ANTHROPIC_API_KEY.
"""

import pytest

from app.agent.llm import LLM
from app.agent.tools import ToolState, tools_for
from app.config import Settings

pytestmark = pytest.mark.live


@pytest.mark.parametrize("has_active_goal", [False, True], ids=["no goal", "active goal"])
async def test_live_the_full_tool_list_is_accepted(has_active_goal: bool) -> None:
    settings = Settings()
    if settings.ANTHROPIC_API_KEY is None:
        pytest.skip("ANTHROPIC_API_KEY is not set: live test skipped")
    llm = LLM.from_settings(settings)
    try:
        reply = await llm.create(
            ["Reply with one word. Do not call any tool."],
            [{"role": "user", "content": "Say OK."}],
            tools_for(ToolState(has_active_goal=has_active_goal), "chat"),
        )
    finally:
        await llm.aclose()

    assert reply.stop_reason in ("end_turn", "tool_use")
