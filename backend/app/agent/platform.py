"""The agent wired to bomboe's platform at startup (D42; the integration's B9/B8 glue).

`install()` (called from the app's lifespan) registers:
- the loop's `AgentServices`: our `AgentWiring` with bomboe's loaders. Each loader opens its own
  unit of work, because `/chat` and the pipeline run the agent in a background task after their
  own session committed. The `agent_runs` row is bomboe's: `/chat` creates and finishes it, so
  `record_run` stays None here (no double finish).
- the tool handlers' `Services` factory. TODO(INT): our handler ports are sync Protocols and
  bomboe's services are async; the async handler refactor (separate branch) replaces
  `_unwired_services` with the Postgres implementation. Until then a tool call returns an
  `is_error` result (`tools_unavailable`) and the agent still answers in text.
"""

from typing import Any, NoReturn

from anthropic.types.beta import BetaMessageParam

from app import clock
from app.agent import ports as agent_ports
from app.agent.handlers.common import ToolContext
from app.agent.loop import set_agent_services
from app.agent.ports import LazyContext, LazyEngine, Services
from app.agent.wiring import AgentWiring
from app.db.session import unit_of_work
from app.domain.enums import MessageRole
from app.domain.user_context import UserContext
from app.errors import DomainError
from app.services import messages
from app.services.context_loader import load_user_context


class _UnwiredPort:
    """Every method raises `tools_unavailable` (TODO(INT): the async Postgres ports)."""

    def __init__(self, name: str) -> None:
        self._name = name

    def __getattr__(self, method: str) -> Any:
        def unavailable(*_: object, **__: object) -> NoReturn:
            raise DomainError(
                "tools_unavailable",
                f"{self._name}.{method} isn't wired to the database yet.",
                status=503,
            )

        return unavailable


def _unwired_services(_db: Any = None) -> Services:
    ports: dict[str, Any] = {name: _UnwiredPort(name) for name in Services.__dataclass_fields__}
    return Services(**ports)


async def load_context(user_id: int) -> UserContext:
    async with unit_of_work() as db:
        return await load_user_context(db, user_id, clock.today())


async def load_history(user_id: int, limit: int) -> list[BetaMessageParam]:
    """The last `limit` chat messages, oldest first, as Claude message params."""
    async with unit_of_work() as db:
        recent = await messages.recent(db, user_id, limit)
    history: list[BetaMessageParam] = []
    for message in recent:
        if message.role == MessageRole.USER:
            history.append({"role": "user", "content": message.content})
        else:
            history.append({"role": "assistant", "content": message.content})
    return history


def _tool_context(user_id: int) -> ToolContext:
    return ToolContext(
        user_id=user_id,
        services=_unwired_services(),
        engine=LazyEngine(),
        context=LazyContext(),
        db=None,
    )


def platform_wiring() -> AgentWiring:
    return AgentWiring(
        load_context=load_context, tool_context=_tool_context, load_history=load_history
    )


def install() -> None:
    """Register the agent's services for this process (idempotent)."""
    set_agent_services(platform_wiring())
    agent_ports.set_services_factory(_unwired_services)
