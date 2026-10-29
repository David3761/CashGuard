"""B15: audit rows, no prompts stored, no secrets in logs or stored errors."""

import logging

import pytest
from sqlalchemy import select, text

from app.config import get_settings
from app.db import models as m
from app.logging import JsonFormatter, redact
from app.pipeline import ports
from tests import factories as f

KEY = "sk-ant-api03-SECRET-abcdef123"
FORBIDDEN_COLUMNS = {"prompt", "system", "system_prompt", "transcript", "messages", "content"}


@pytest.fixture
def anthropic_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    get_settings.cache_clear()
    yield KEY
    get_settings.cache_clear()


def test_redact_scrubs_the_key_and_key_shaped_strings(anthropic_key):
    assert KEY not in redact(f"auth failed for {KEY}")
    assert redact("x sk-ant-other-1234 y") == "x [REDACTED] y"  # ours: one marker for every secret (F1.5)


def test_log_lines_never_contain_the_key(anthropic_key):
    try:
        raise RuntimeError(f"401 with key {KEY}")
    except RuntimeError:
        record = logging.LogRecord(
            "t",
            logging.ERROR,
            __file__,
            1,
            "calling %s",
            (KEY,),
            exc_info=__import__("sys").exc_info(),
        )
    line = JsonFormatter().format(record)
    assert KEY not in line and "with key ***" in line


async def test_no_prompt_or_transcript_columns(db):
    rows = await db.execute(
        text(
            "select table_name, column_name from information_schema.columns "
            "where table_name in ('agent_runs', 'tool_calls')"
        )
    )
    assert not {c for _, c in rows} & FORBIDDEN_COLUMNS


async def test_failed_chat_run_keeps_a_redacted_error(
    as_committed_user, db_committed, anthropic_key, monkeypatch
):
    u = await f.user(db_committed)
    await db_committed.commit()

    async def leaky(*_a, **_k):
        raise RuntimeError(f"Anthropic said no for key {KEY}")

    monkeypatch.setattr(ports, "run_agent", leaky)
    r = await as_committed_user(u).post("/chat", json={"text": "hei"})
    run = await db_committed.get(m.AgentRun, r.json()["run_id"], populate_existing=True)
    assert (run.trigger, run.status, run.model) == ("chat", "failed", "claude-sonnet-5-5")
    assert KEY not in run.error and run.error.endswith("for key ***")
    rows = await db_committed.scalars(select(m.AgentRun).where(m.AgentRun.user_id == u.id))
    assert len(list(rows)) == 1  # one row per run
