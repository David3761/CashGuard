"""One row per tool the agent called (arch 6.4 rule 4) (B3 step 3)."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain.enums import ToolCallStatus
from app.services._common import owned


async def log(
    db: AsyncSession,
    user_id: int,
    run_id: int,
    *,
    tool_name: str,
    input: dict[str, Any],
    output: Any,
    status: ToolCallStatus,
) -> None:
    """Record the call (input as Claude sent it, output or the error text)."""
    await owned(db, m.AgentRun, user_id, run_id, "Agent run")
    db.add(
        m.ToolCall(
            run_id=run_id,
            user_id=user_id,
            tool_name=tool_name,
            input=input,
            output=output,
            status=status,
        )
    )
    await db.flush()
