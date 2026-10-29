"""`POST /assistant/messages`: the same chat run as `/api/chat` (B9), streamed as SSE.

The order of work mirrors bomboe's `app/api/chat.py` (that file isn't changed here):
save the user message (+ language, the `agent_runs` row) → catch up on transactions →
`ports.run_agent(user_id, "chat", text, "text")` → save the reply + push the ws events. Any
failure in the run gives the arch §11 fallback reply (saved like a normal reply) and a failed
run. The one-at-a-time rule is shared with `/api/chat` through `agent_runs.is_running`.

The agent call is injected (`get_reply_runner`, a FastAPI dependency), so tests run it with a
fake and nothing in the test suite can reach a live LLM.

Streaming: `message` once the user message is stored → keep-alive comments while the agent
works → the reply in a few `delta` chunks → `done` with the stored reply. The run is a task of
its own: a client that disconnects, or a stream that hits `APP_API_REPLY_TIMEOUT_S` (→ an
`error` event), doesn't stop it; the reply still lands in the history and the lock is freed when
the run ends (cancelling it would leave `agent_runs` "running" and block the user).
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Final

from app import events
from app.app_api import sse
from app.app_api.mapping import message_json, reply_chunks
from app.db.session import unit_of_work
from app.domain import models as dm
from app.domain.enums import AgentRunStatus, InputMode
from app.domain.results import AgentResult
from app.logging import redact
from app.pipeline import ports
from app.pipeline.processor import process_user
from app.services import agent_runs, forecasts, messages, plans, users
from app.ws import push_after_commit

log = logging.getLogger(__name__)

ReplyRunner = Callable[[int, int, str], Awaitable[AgentResult]]
"""(user_id, run_id, text) → the agent's result."""

KEEP_ALIVE_S: Final = 15.0  # a comment line this often while the agent works (proxies, NATs)
DELTA_PAUSE_S: Final = 0.03  # between delta chunks: a typing effect in the app
FAILED_REPLY: Final = "The assistant couldn't answer right now. Please try again."
TIMED_OUT: Final = "The assistant is taking too long. Try again in a moment."

_tasks: set[asyncio.Task[dm.MessageView]] = set()  # strong refs: a running reply isn't GC'd


async def run_platform_agent(user_id: int, run_id: int, text: str) -> AgentResult:
    """The production runner: what `/api/chat`'s background task does before saving."""
    await process_user(user_id, "chat")
    token = agent_runs.CURRENT_RUN.set(run_id)
    try:
        return await ports.run_agent(user_id, "chat", text, InputMode.TEXT)
    finally:
        agent_runs.CURRENT_RUN.reset(token)


def get_reply_runner() -> ReplyRunner:
    """FastAPI dependency (tests override it with a fake runner)."""
    return run_platform_agent


async def complete_reply(
    user_id: int, run_id: int, text: str, runner: ReplyRunner
) -> dm.MessageView:
    """Run the agent and store its reply (or the fallback reply); returns the stored reply.
    Raises only if even the fallback couldn't be stored (the DB is down)."""
    try:
        async with unit_of_work() as db:
            before = await plans.latest(db, user_id)
        result = await runner(user_id, run_id, text)
        async with unit_of_work() as db:
            msg = await messages.save_assistant(
                db,
                user_id,
                text=result.text,
                speak_text=result.speak_text,
                quick_replies=result.quick_replies,
                action_cards=[card.model_dump(mode="json") for card in result.action_cards],
                ref_transaction_id=result.ref_transaction_id,
                speak=result.speak_text is not None,
            )
            await agent_runs.finish(
                db, user_id, run_id, status=AgentRunStatus.COMPLETED, iterations=0
            )
            push_after_commit(db, user_id, events.assistant_message(msg))
            after = await plans.latest(db, user_id)
            if after is not None and (before is None or after.version != before.version):
                push_after_commit(db, user_id, events.plan_updated(after))
                forecast = await forecasts.latest(db, user_id)
                if forecast is not None:
                    push_after_commit(db, user_id, events.forecast_updated(forecast))
        return msg
    except Exception as exc:
        log.exception("app chat run %s failed", run_id)
        async with unit_of_work() as db:
            profile = await users.get(db, user_id)
            msg = await messages.save_assistant(
                db, user_id, text=ports.fallback_reply(profile.language)
            )
            if await agent_runs.is_running(db, user_id):
                await agent_runs.finish(
                    db,
                    user_id,
                    run_id,
                    status=AgentRunStatus.FAILED,
                    iterations=0,
                    error=redact(str(exc))[:500],
                )
            push_after_commit(db, user_id, events.assistant_message(msg))
        return msg


def _retrieve(task: asyncio.Task[dm.MessageView]) -> None:
    _tasks.discard(task)
    if not task.cancelled() and task.exception() is not None:
        log.error("app chat reply could not be stored", exc_info=task.exception())


def start_reply(
    user_id: int,
    run_id: int,
    text: str,
    runner: ReplyRunner,
    *,
    release: Callable[[], None],
) -> asyncio.Task[dm.MessageView]:
    """The reply as a task of its own; `release` (the one-at-a-time claim) runs when it ends."""

    async def owned() -> dm.MessageView:
        try:
            return await complete_reply(user_id, run_id, text, runner)
        finally:
            release()

    task = asyncio.create_task(owned(), name=f"app-chat-{run_id}")
    _tasks.add(task)
    task.add_done_callback(_retrieve)
    return task


async def stream_reply(
    user_message: dm.MessageView,
    task: asyncio.Task[dm.MessageView],
    *,
    timeout_s: float,
    keep_alive_s: float | None = None,
    delta_pause_s: float | None = None,
) -> AsyncIterator[bytes]:
    """The SSE body: message → (keep-alive)* → delta* → done | error."""
    keep_alive_s = KEEP_ALIVE_S if keep_alive_s is None else keep_alive_s
    delta_pause_s = DELTA_PAUSE_S if delta_pause_s is None else delta_pause_s
    yield sse.frame("message", message_json(user_message))
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while not task.done():
        remaining = deadline - loop.time()
        if remaining <= 0:
            yield sse.frame("error", {"message": TIMED_OUT})
            return
        # asyncio.wait never cancels the task: a closed stream leaves the run going.
        await asyncio.wait({task}, timeout=min(keep_alive_s, remaining))
        if not task.done() and loop.time() < deadline:
            yield sse.KEEP_ALIVE
    if task.cancelled() or task.exception() is not None:
        yield sse.frame("error", {"message": FAILED_REPLY})
        return
    reply = task.result()
    for chunk in reply_chunks(reply.content):
        yield sse.frame("delta", {"text": chunk})
        if delta_pause_s:
            await asyncio.sleep(delta_pause_s)
    yield sse.frame("done", message_json(reply))
