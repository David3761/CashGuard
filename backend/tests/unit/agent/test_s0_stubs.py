"""S0: the agent's §15 stubs are importable and return the documented types."""

from datetime import UTC, datetime

import pytest

from app.agent.snapshot import build_snapshot
from app.clock import FixedClock, use_clock

# detect_language is A11's real one now (tests: test_language.py).


async def test_build_snapshot_is_the_async_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    # A4 replaced the stub: the shell loads the context (B4) and renders it (tests: test_snapshot).
    from app.agent import snapshot
    from tests.builders import matei_ctx

    async def load(db: object, user_id: int, today: object) -> object:
        return matei_ctx()

    monkeypatch.setattr(snapshot, "_load_context", load)
    with use_clock(FixedClock(datetime(2026, 6, 15, 9, 0, tzinfo=UTC))):
        text = await build_snapshot(None, 1, "chat", None)
    assert "2026-06-15" in text
    assert "run: chat" in text


# apply_annotation's stub tests moved to test_handlers_transactions.py (A3: the real one).
