"""The agent wired to bomboe's platform at startup (D42; the integration's B9/B8 glue).

`install()` (called from the app's lifespan) registers:
- the loop's `AgentServices`: our `AgentWiring` with bomboe's loaders. Each loader opens its own
  unit of work, because `/chat` and the pipeline run the agent in a background task after their
  own session committed. The `agent_runs` row is bomboe's: `/chat` creates and finishes it, so
  `record_run` stays None here (no double finish).
- the tool handlers' `Services` factory: `pg_ports.pg_services(db)`, bomboe's Postgres services.
  Each tool call is its own unit of work (`PlatformServices.execute_tool`): one session for the
  handler, danutu's engine (the D18 recompute) and the context layer; committed when the result
  is ok, rolled back when it is an `is_error` result (a half-done write never sticks). The WS
  pushes the handler queued (`RunState.pushes`) go out only after that commit.
- the proactive services (A7): the same wiring plus the event, the message, the asked mark and
  the notification, each in its own unit of work.
"""

import json
import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from anthropic.types.beta import BetaMessageParam, BetaToolResultBlockParam, BetaToolUseBlock
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock, events
from app.agent import pg_ports
from app.agent import ports as agent_ports
from app.agent.handlers.common import ToolContext
from app.agent.loop import set_agent_services
from app.agent.ports import LazyContext, LazyEngine
from app.agent.proactive import ProactiveEvent, set_proactive_services
from app.agent.wiring import AgentWiring
from app.db.session import unit_of_work
from app.domain.enums import MessageRole
from app.domain.results import ActionCard
from app.domain.user_context import UserContext
from app.errors import DomainError
from app.pipeline import ports as pipeline_ports
from app.services import agent_events, messages, notifications, receivables, transactions, users
from app.services.context_loader import load_user_context
from app.ws import push_after_commit

log = logging.getLogger(__name__)


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


_TOOL_DB: ContextVar[AsyncSession | None] = ContextVar("agent_tool_db", default=None)
"""The session of the tool call running in this task (set by `PlatformServices.execute_tool`)."""


class _Rollback(Exception):
    """Leave the tool call's unit of work with a rollback (an `is_error` result)."""


def _tool_context(user_id: int) -> ToolContext:
    db = _TOOL_DB.get()
    if db is None:
        raise RuntimeError("a tool call runs inside PlatformServices.execute_tool")
    return ToolContext(
        user_id=user_id,
        services=pg_ports.pg_services(db),
        engine=LazyEngine(),
        context=LazyContext(),
        db=db,
    )


async def _queue_pushes(
    db: AsyncSession, user_id: int, pushes: list[tuple[str, dict[str, Any]]]
) -> None:
    """The WS events a handler asked for, sent once the tool call commits."""
    for kind, body in pushes:
        if kind == "transaction.annotated" and isinstance(body.get("transaction_id"), int):
            tx = await transactions.get(db, user_id, body["transaction_id"])
            language = (await users.get(db, user_id)).language
            label = pipeline_ports.label(tx.purpose, language)
            push_after_commit(db, user_id, events.transaction_annotated(tx, label))
        elif kind == "receivable.updated":
            for key in ("receivable_id", "cancelled_receivable_id"):
                if isinstance(body.get(key), int):
                    receivable = await receivables.get(db, user_id, body[key])
                    push_after_commit(db, user_id, events.receivable_updated(receivable))


def _internal_error(block: BetaToolUseBlock) -> BetaToolResultBlockParam:
    content = json.dumps(
        {
            "ok": False,
            "error": {
                "code": "internal_error",
                "message": "The change couldn't be saved. Tell the user it didn't work.",
            },
        }
    )
    return {"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": True}


@dataclass
class PlatformServices(AgentWiring):
    """`AgentWiring` + what a proactive run writes (A7's `ProactiveServices`, bomboe's B8/B13):
    the event, the assistant message (+ `assistant.message` after commit), the asked mark and
    the notification. Each write is its own unit of work."""

    _event_users: dict[int, int] = field(default_factory=dict)

    async def execute_tool(
        self, user_id: int, run_id: int | None, block: BetaToolUseBlock
    ) -> BetaToolResultBlockParam:
        """One tool call = one unit of work: commit on an ok result, rollback on `is_error`."""
        try:
            async with unit_of_work() as db:
                token = _TOOL_DB.set(db)
                try:
                    run = self._runs.get(user_id)
                    pushed = len(run.pushes) if run is not None else 0
                    result = await super().execute_tool(user_id, run_id, block)
                    if result.get("is_error"):
                        raise _Rollback
                    run = self._runs.get(user_id)
                    if run is not None:
                        await _queue_pushes(db, user_id, run.pushes[pushed:])
                finally:
                    _TOOL_DB.reset(token)
        except _Rollback:
            return result
        except Exception:
            log.exception("tool %s: the unit of work failed", block.name)
            return _internal_error(block)
        return result

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
    agent_ports.set_services_factory(pg_ports.pg_services)
