"""Proactive runs (A7): the agent speaks first, because of a pending `agent_event` (arch F4, F10).

- Read-only tools (D22): the setup port returns them for `trigger="proactive"`, and the loop
  refuses any other tool Claude tries.
- Claude gets 15 s (`asyncio.timeout`; D54: 5 s was too short for Bedrock). A timeout or any
  LLM error → the template question
  (A5.3 `transaction_question`, "Ce ți-ai luat de la eMAG?" when `ask_what_item`) with the
  default chips. A non-question event without Claude is left pending (arch 11), to retry later.
- The message is saved with `speak = true`, `speak_text`, `ref_transaction_id` and
  `agent_event_id`; the event is marked asked; a notification opens the chat.
- An event that isn't pending (already asked, or being run right now) → nothing (no duplicate).
"""

import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Protocol

from app.agent.llm import LLMClient, LLMError, get_llm
from app.agent.loop import (
    HISTORY_LIMIT,
    AgentServices,
    PromptKind,
    Turn,
    build_result,
    conversation,
    converse,
    system_parts,
)
from app.agent.templates import QUESTION_REPLY_KEYS, quick_replies, transaction_question
from app.config import get_settings
from app.domain.results import ActionCard, AgentResult

log = logging.getLogger(__name__)

PROACTIVE_TIMEOUT_S: Final = 15.0  # D54: Bedrock answers in 3-13 s (live, 2026-10-29)
MAX_QUESTION_WORDS: Final = 18  # arch 6.9: longer is logged, not refused
MIN_QUESTION_CHIPS: Final = 3
QUESTION_EVENTS: Final = frozenset({"transaction_question"})


@dataclass(frozen=True, slots=True)
class ProactiveEvent:
    """The `agent_events` row a proactive run is about (+ its transaction for a question)."""

    event_id: int
    type: str  # AgentEventType
    status: str  # AgentEventStatus
    ref_transaction_id: int | None = None
    amount: Decimal | None = None
    merchant: str | None = None
    ask_what_item: bool = False
    reason: str | None = None


class ProactiveServices(AgentServices, Protocol):
    """The loop's port + what a proactive run writes. The real adapter is
    `app.agent.platform.PlatformServices` (bomboe's services, one unit of work per write)."""

    async def get_event(self, user_id: int, event_id: int) -> ProactiveEvent | None: ...

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
        """`messages.save_assistant` (§15); returns the message id."""
        ...

    async def mark_event_asked(self, event_id: int) -> None: ...

    async def create_notification(
        self, user_id: int, *, text: str, opens_chat: bool, agent_event_id: int
    ) -> None: ...


_services: ProactiveServices | None = None
_in_flight: set[int] = set()  # event ids being run in this process


def get_proactive_services() -> ProactiveServices:
    if _services is None:
        raise RuntimeError("proactive services not wired: call set_proactive_services()")
    return _services


def set_proactive_services(services: ProactiveServices | None) -> None:
    global _services
    _services = services


def _template_question(
    event: ProactiveEvent, fallback_amount: Decimal | None, lang: str
) -> str | None:
    amount = event.amount if event.amount is not None else fallback_amount
    if amount is None or amount <= 0:
        return None
    return transaction_question(
        amount, event.merchant or "", lang, ask_what_item=event.ask_what_item
    )


async def run_proactive(
    user_id: int,
    event_id: int,
    *,
    run_id: int | None = None,
    llm: LLMClient | None = None,
    services: ProactiveServices | None = None,
) -> AgentResult | None:
    """Speak up about one pending event. None when nothing was said (duplicate, not pending,
    or a non-question event while Claude is down)."""
    if event_id in _in_flight:
        log.info("event %d is already being run", event_id)
        return None
    _in_flight.add(event_id)
    try:
        return await _run(user_id, event_id, run_id, llm, services or get_proactive_services())
    finally:
        _in_flight.discard(event_id)


async def _run(
    user_id: int,
    event_id: int,
    run_id: int | None,
    llm: LLMClient | None,
    services: ProactiveServices,
) -> AgentResult | None:
    event = await services.get_event(user_id, event_id)
    if event is None or event.status != "pending":
        log.info("event %d is not pending: nothing to say", event_id)
        return None
    is_question = event.type in QUESTION_EVENTS
    setup = await services.setup(user_id, "proactive", event_id)
    lang = setup.language
    kind: PromptKind = "transaction_question" if is_question else "chat"
    messages = conversation(await services.history(user_id, HISTORY_LIMIT), None)
    turn = Turn()
    try:
        async with asyncio.timeout(PROACTIVE_TIMEOUT_S):
            await converse(
                llm or get_llm(),
                services,
                user_id,
                run_id,
                setup,
                system_parts(kind, setup.snapshot),
                messages,
                turn,
                max_iterations=get_settings().MAX_AGENT_ITERATIONS,
            )
    except TimeoutError:
        log.warning("proactive run for event %d timed out: template", event_id)
        turn.fallback = "llm_down"
    except LLMError as err:
        log.warning("proactive run for event %d: %s, template", event_id, type(err).__name__)
        turn.fallback = "llm_down"
    except Exception:  # any other failure: the question still gets asked
        log.exception("proactive run for event %d failed: template", event_id)
        turn.fallback = "llm_down"

    failed = turn.fallback is not None or turn.text is None
    template: str | None = None
    if failed:
        question_amount = setup.open_question.amount if setup.open_question else None
        template = _template_question(event, question_amount, lang) if is_question else None
        if template is None:  # nothing sensible to say without Claude: retry later (arch 11)
            await services.finish_run(run_id, "failed", turn.fallback or "llm_down")
            return None
    result = build_result(turn, setup, speak=True, fallback_text=template)
    update: dict[str, object] = {
        "ref_transaction_id": event.ref_transaction_id or result.ref_transaction_id
    }
    if is_question and len(result.quick_replies) < MIN_QUESTION_CHIPS:
        update["quick_replies"] = tuple(quick_replies(QUESTION_REPLY_KEYS, lang))
    result = result.model_copy(update=update)
    if is_question and len(result.text.split()) > MAX_QUESTION_WORDS:
        log.warning(
            "question for event %d has %d words (> %d)",
            event_id,
            len(result.text.split()),
            MAX_QUESTION_WORDS,
        )

    await services.save_assistant_message(
        user_id,
        text=result.text,
        speak=True,
        speak_text=result.speak_text,
        quick_replies=result.quick_replies,
        action_cards=result.action_cards,
        ref_transaction_id=result.ref_transaction_id,
        agent_event_id=event_id,
    )
    await services.mark_event_asked(event_id)
    await services.create_notification(
        user_id, text=result.text, opens_chat=True, agent_event_id=event_id
    )
    await services.finish_run(run_id, "failed" if failed else "completed", turn.fallback)
    return result
