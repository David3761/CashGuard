"""Agent run audit rows (B15 uses them; B9 uses `is_running` as the busy truth) (B3 step 3)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import AgentRunStatus, AgentTrigger


async def start(db: AsyncSession, user_id: int, *, trigger: AgentTrigger, model: str) -> int:
    """A running run; returns its id."""
    raise NotImplementedError("B3 step 3")


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
    raise NotImplementedError("B3 step 3")


async def is_running(db: AsyncSession, user_id: int) -> bool:
    """Is a run still `running` for this user (409 agent_busy after a restart)?"""
    raise NotImplementedError("B3 step 3")
