"""Agent run audit rows (B15 uses them; B9 uses `is_running` as the busy truth) (B3 step 3)."""

from datetime import timedelta

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db import models as m
from app.domain.enums import AgentRunStatus, AgentTrigger
from app.services._common import as_enum, invalid_transition, owned

# A run still `running` after this long was lost (a crash, a restart): it no longer blocks
# the user (B9's 409 agent_busy). Real runs take seconds.
STALE_AFTER = timedelta(minutes=2)


async def start(db: AsyncSession, user_id: int, *, trigger: AgentTrigger, model: str) -> int:
    """A running run; returns its id."""
    row = m.AgentRun(
        user_id=user_id,
        trigger=as_enum(AgentTrigger, trigger, "invalid_trigger"),
        model=model,
        status=AgentRunStatus.RUNNING,
    )
    db.add(row)
    await db.flush()
    return row.id


async def finish(
    db: AsyncSession,
    user_id: int,
    run_id: int,
    *,
    status: AgentRunStatus,
    iterations: int,
    error: str | None = None,
) -> None:
    """running → completed | failed, `finished_at` = clock.now(). Never stores prompts (Q27)."""
    row = await owned(db, m.AgentRun, user_id, run_id, "Agent run")
    if row.status != AgentRunStatus.RUNNING:
        raise invalid_transition("The run", row.status, status)
    row.status = status
    row.iterations = iterations
    row.error = error
    row.finished_at = clock.now()
    await db.flush()


async def is_running(db: AsyncSession, user_id: int) -> bool:
    """Is a run still `running` for this user (409 agent_busy after a restart)? Runs older than
    2 minutes are treated as lost."""
    running = select(m.AgentRun.id).where(
        m.AgentRun.user_id == user_id,
        m.AgentRun.status == AgentRunStatus.RUNNING,
        m.AgentRun.started_at > clock.now() - STALE_AFTER,
    )
    return bool(await db.scalar(select(exists(running))))
