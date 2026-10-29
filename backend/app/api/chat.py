"""POST /chat (arch F1, B9): save the message, answer 202, run the agent in the background."""

import logging

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field, field_validator

from app import events
from app.api.deps import CurrentUser, Db
from app.config import get_settings
from app.db.session import unit_of_work
from app.domain.enums import AgentRunStatus, AgentTrigger, InputMode
from app.errors import DomainError
from app.logging import redact
from app.pipeline import ports
from app.pipeline.processor import process_user
from app.services import agent_runs, forecasts, messages, plans, users
from app.ws import manager, push_after_commit

log = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

_busy: set[int] = set()  # fast path; agent_runs.is_running is the truth after a restart


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    input_mode: InputMode = InputMode.TEXT

    @field_validator("text", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ChatAccepted(BaseModel):
    message_id: int
    run_id: int


@router.post("/chat", status_code=202)
async def chat(
    body: ChatIn, user: CurrentUser, db: Db, background: BackgroundTasks
) -> ChatAccepted:
    if user.id in _busy or await agent_runs.is_running(db, user.id):
        raise DomainError(
            "agent_busy", "The assistant is still answering your previous message.", 409
        )
    _busy.add(user.id)
    try:
        msg = await messages.save_user(db, user.id, body.text, body.input_mode)
        language = ports.detect_language(body.text, user.language)
        if language != user.language:
            await users.update(db, user.id, language=language)
        run_id = await agent_runs.start(
            db, user.id, trigger=AgentTrigger.CHAT, model=get_settings().ANTHROPIC_MODEL
        )
        await db.commit()
    except BaseException:
        _busy.discard(user.id)
        raise
    background.add_task(run_chat, user.id, run_id, body.text, body.input_mode)
    return ChatAccepted(message_id=msg.id, run_id=run_id)


async def run_chat(user_id: int, run_id: int, text: str, input_mode: InputMode) -> None:
    """agent.typing → catch up on transactions → run_agent → save + push the reply (+ plan /
    forecast if the plan changed). Any failure → the fallback reply, run failed."""
    try:
        await manager.push(user_id, events.agent_typing())
        async with unit_of_work() as db:
            before = await plans.latest(db, user_id)
        await process_user(user_id, "chat")
        token = agent_runs.CURRENT_RUN.set(run_id)
        try:
            result = await ports.run_agent(user_id, "chat", text, input_mode)
        finally:
            agent_runs.CURRENT_RUN.reset(token)
        async with unit_of_work() as db:
            msg = await messages.save_assistant(
                db,
                user_id,
                text=result.text,
                speak_text=result.speak_text,
                quick_replies=result.quick_replies,
                action_cards=result.action_cards,
                ref_transaction_id=result.ref_transaction_id,
                speak=input_mode == InputMode.VOICE or result.speak_text is not None,
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
    except Exception as exc:
        log.exception("chat run %s failed", run_id)
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
    finally:
        _busy.discard(user_id)
