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

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, NoReturn

from anthropic.types.beta import BetaMessageParam

from app import clock, events
from app.agent import ports as agent_ports
from app.agent.handlers.common import ToolContext
from app.agent.loop import set_agent_services
from app.agent.ports import LazyContext, LazyEngine, Services
from app.agent.proactive import ProactiveEvent, set_proactive_services
from app.agent.wiring import AgentWiring
from app.db.session import unit_of_work
from app.domain.enums import MessageRole
from app.domain.results import ActionCard
from app.domain.user_context import UserContext
from app.errors import DomainError
from app.services import agent_events, messages, notifications, transactions
from app.services.context_loader import load_user_context
from app.ws import push_after_commit


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


@dataclass
class PlatformServices(AgentWiring):
    """`AgentWiring` + what a proactive run writes (A7's `ProactiveServices`, bomboe's B8/B13):
    the event, the assistant message (+ `assistant.message` after commit), the asked mark and
    the notification. Each write is its own unit of work."""

    _event_users: dict[int, int] = field(default_factory=dict)

    async def get_event(self, user_id: int, event_id: int) -> ProactiveEvent | None:
        async with unit_of_work() as db:
            try:
                event = await agent_events.get(db, user_id, event_id)
            except DomainError:
                return None
            amount: Decimal | None = None
            merchant: str | None = None
            if event.ref_transaction_id is not None:
                tx = await transactions.get(db, user_id, event.ref_transaction_id)
                amount, merchant = tx.amount, tx.merchant or tx.merchant_raw
        self._event_users[event_id] = user_id
        reason = event.payload.get("reason")
        return ProactiveEvent(
            event_id=event.id,
            type=str(event.type),
            status=str(event.status),
            ref_transaction_id=event.ref_transaction_id,
            amount=amount,
            merchant=merchant,
            ask_what_item=bool(event.payload.get("ask_what_item")),
            reason=reason if isinstance(reason, str) else None,
        )

    async def save_assistant_message(
        self,
        user_id: int,
        *,
        text: str,
        speak: bool,
        speak_text: str | None,
        quick_replies: tuple[str, ...],
        action_cards: tuple[ActionCard, ...],
        ref_transaction_id: int | None,
        agent_event_id: int,
    ) -> int:
        async with unit_of_work() as db:
            message = await messages.save_assistant(
                db,
                user_id,
                text=text,
                speak_text=speak_text,
                quick_replies=quick_replies,
                action_cards=[card.model_dump(mode="json") for card in action_cards],
                ref_transaction_id=ref_transaction_id,
                agent_event_id=agent_event_id,
                speak=speak,
            )
            push_after_commit(db, user_id, events.assistant_message(message))
        return message.id

    async def mark_event_asked(self, event_id: int) -> None:
        user_id = self._event_users.get(event_id)
        if user_id is None:
            raise RuntimeError(f"event {event_id}: get_event must run first")
        async with unit_of_work() as db:
            await agent_events.mark_asked(db, user_id, event_id)

    async def create_notification(
        self, user_id: int, *, text: str, opens_chat: bool, agent_event_id: int
    ) -> None:
        async with unit_of_work() as db:
            created = await notifications.create(
                db,
                user_id,
                type="agent_message",
                title="CashGuard",
                body=text[:500],
                opens_chat=opens_chat,
                agent_event_id=agent_event_id,
            )
            push_after_commit(db, user_id, events.notification_new(created))


def platform_wiring() -> PlatformServices:
    return PlatformServices(
        load_context=load_context, tool_context=_tool_context, load_history=load_history
    )


def install() -> None:
    """Register the agent's services for this process (idempotent): `/chat`'s `run_agent` and
    the pipeline's `run_proactive` then run against Postgres."""
    wiring = platform_wiring()
    set_agent_services(wiring)
    set_proactive_services(wiring)
    agent_ports.set_services_factory(_unwired_services)
