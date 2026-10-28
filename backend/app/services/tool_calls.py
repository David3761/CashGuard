"""One row per tool the agent called (arch 6.4 rule 4) (B3 step 3)."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ToolCallStatus


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
    raise NotImplementedError("B3 step 3")
