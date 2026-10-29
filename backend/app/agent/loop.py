"""The agent loop (A6): one run = Claude + tools until a reply (arch 6.3 v0.8, 6.8, 7, 11).

- The snapshot and the tool list are built ONCE per run (D46): the setup port returns both.
- `tool_use` → `resp.content` is appended unchanged (thinking included), then ONE user message
  with every tool result, in call order. `end_turn` → the reply. Any other stop reason
  (`refusal`, `max_tokens`, `pause_turn`, …) → a template; so do the loop limit and LLM errors.
- A tool the run didn't offer is refused here, before the executor (D22 defence in depth).
- The final text is checked with `find_banned`: one regeneration, then the template (6.9).
- Quick replies and action cards come from the UI tools; `speak_text` (A11's `make_speak_text`)
  is the plain ≤ 2-sentence spoken version for voice input and proactive runs.
- Cost and abuse bounds (docs/ai-safety.md): a user message is cut to `MAX_USER_MESSAGE_CHARS`;
  a run executes at most `MAX_TOOL_CALLS_PER_RUN` tools (the calls over it get `is_error` "tool
  budget exceeded"; Claude gets one more call to reply, and another tool call there ends the run
  with the loop-limit template); a chat run waits for Claude at most `CHAT_RUN_TIMEOUT_S` in
  total. The deadline bounds the Claude calls, so a tool call is never cancelled halfway through
  its writes. A timeout or any other failure is a template reply, never an exception or a
  traceback.

What the loop needs from the rest of the backend is the `AgentServices` port: B9/A3 wire the real
one (`set_agent_services`), tests pass a fake.
"""

import asyncio
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal, Protocol

from anthropic.types.beta import (
    BetaMessage,
    BetaMessageParam,
    BetaToolParam,
    BetaToolResultBlockParam,
    BetaToolUseBlock,
)

from app.agent.fallbacks import OpenQuestion, PotRef, answer_without_llm
from app.agent.language import make_speak_text
from app.agent.llm import LLMBadRequest, LLMClient, LLMUnavailable, get_llm
from app.agent.prompts import instructions_for, system_rules
from app.agent.style import find_banned
from app.agent.templates import FallbackReason, fallback_reply
from app.config import get_settings
from app.domain.results import ActionCard, AgentResult

log = logging.getLogger(__name__)

HISTORY_LIMIT: Final = 20
MAX_TEXT: Final = 4000  # AgentResult.text (F2 Text4000)
MAX_CHIP: Final = 80  # a quick reply (F2 Text80)
MAX_CHIPS: Final = 4
MAX_USER_MESSAGE_CHARS: Final = 4000  # LLM10: a longer message is cut (history included)
# Per run, across iterations: one response may hold any number of parallel calls (LLM06/10).
MAX_TOOL_CALLS_PER_RUN: Final = 16
CHAT_RUN_TIMEOUT_S: Final = 60.0  # the chat run's whole wait for Claude (proactive: 15 s, D54)
TOOL_BUDGET_EXCEEDED: Final = (
    "tool budget exceeded: this run already made its {limit} tool calls, so nothing more was "
    "run. Reply to the user now with what was done and what is left."
)
PromptKind = Literal["chat", "onboarding", "transaction_question"]
RunStatus = Literal["completed", "failed"]

# The user turn of a run that has no user message (a proactive run): the API needs one.
PROACTIVE_TURN: Final = (
    "(No message from the user: you are starting the conversation because of the event "
    "described in the snapshot.)"
)


@dataclass(frozen=True, slots=True)
class RunSetup:
    """Everything a run needs, built ONCE at its start (D46)."""

    language: str  # "ro" | "en"
    snapshot: str  # A4 build_snapshot
    tools: Sequence[BetaToolParam]  # A2 tools_for(state, trigger)
    open_question: OpenQuestion | None = None  # → ref_transaction_id, A9 fallbacks
    pots: Sequence[PotRef] = ()  # active pots (A9 "Ceva plănuit")


class AgentServices(Protocol):
    """The loop's port. TODO(A3 ports / B9): the real adapter over bomboe's services."""

    async def setup(self, user_id: int, trigger: str, event_id: int | None) -> RunSetup:
        """The snapshot, the tool list, the language: computed once per run."""
        ...

    async def history(self, user_id: int, limit: int) -> list[BetaMessageParam]:
        """The last `limit` chat messages, oldest first, as API message params."""
        ...

    async def execute_tool(
        self, user_id: int, run_id: int | None, block: BetaToolUseBlock
    ) -> BetaToolResultBlockParam:
        """A3 `execute_tool`: validate, run, log; errors come back with `is_error: true`."""
        ...

    async def finish_run(self, run_id: int | None, status: RunStatus, reason: str | None) -> None:
        """Mark the `agent_runs` row (arch 11: a fallback = a failed run)."""
        ...


_services: AgentServices | None = None


def get_agent_services() -> AgentServices:
    if _services is None:
        raise RuntimeError("agent services not wired: call set_agent_services() at startup")
    return _services


def set_agent_services(services: AgentServices | None) -> None:
    global _services
    _services = services


@dataclass
class Turn:
    """What a run produced so far; filled in place, so a timeout or an error keeps it."""

    text: str | None = None
    fallback: FallbackReason | None = None
    quick_replies: list[str] = field(default_factory=list)
    action_cards: list[ActionCard] = field(default_factory=list)
    plan_changed: bool = False
    tools_ran: int = 0
    without_llm: bool = False  # answered by the A9 fallbacks
    over_budget: bool = False  # a call was refused: MAX_TOOL_CALLS_PER_RUN


def system_parts(kind: PromptKind, snapshot: str) -> list[str]:
    """Frozen rules → run instructions → snapshot (6.8 cache order)."""
    return [system_rules(), instructions_for(kind), snapshot]


def cap_user_text(text: str) -> str:
    """At most `MAX_USER_MESSAGE_CHARS` characters (a hard cut: a long word can't hide the rest)."""
    if len(text) <= MAX_USER_MESSAGE_CHARS:
        return text
    log.warning("user message cut to %d characters (was %d)", MAX_USER_MESSAGE_CHARS, len(text))
    return text[: MAX_USER_MESSAGE_CHARS - 1] + "…"


def _capped(message: BetaMessageParam) -> BetaMessageParam:
    content = message["content"]
    if message["role"] == "user" and isinstance(content, str):
        return {"role": "user", "content": cap_user_text(content)}
    return message


def conversation(
    history: Sequence[BetaMessageParam], user_message: str | None
) -> list[BetaMessageParam]:
    """The last 20 messages + this turn. Starts with a user message and ends with one (no
    prefill). B9 saves the user's message before the run, so it isn't appended twice. Every
    user text is capped, the saved copy too (so the comparison still matches)."""
    messages = [_capped(each) for each in list(history)[-HISTORY_LIMIT:]]
    if user_message is not None:
        user_message = cap_user_text(user_message)
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    last = messages[-1] if messages else None
    already_saved = last is not None and last["role"] == "user" and last["content"] == user_message
    if user_message is not None and not already_saved:
        messages.append({"role": "user", "content": user_message})
    elif user_message is None:
        messages.append({"role": "user", "content": PROACTIVE_TURN})
    return messages


def _refused(block: BetaToolUseBlock, reason: str) -> BetaToolResultBlockParam:
    return {"type": "tool_result", "tool_use_id": block.id, "content": reason, "is_error": True}


def _result_data(result: BetaToolResultBlockParam) -> dict[str, Any]:
    content = result.get("content")
    if not isinstance(content, str):
        return {}
    try:
        data = json.loads(content)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _collect_ui(turn: Turn, block: BetaToolUseBlock, result: BetaToolResultBlockParam) -> None:
    """Quick replies (the call's `options`), action cards and plan changes (the result JSON).
    TODO(A3): handlers return `action_card` for offer_payment_request and `plan` after D18."""
    if result.get("is_error"):
        return
    if block.name == "show_quick_replies" and isinstance(block.input, dict):
        options = block.input.get("options")
        if isinstance(options, list):
            chips = [str(o).strip() for o in options]
            turn.quick_replies = [c for c in chips if 0 < len(c) <= MAX_CHIP][:MAX_CHIPS]
    data = _result_data(result)
    card = data.get("action_card")
    if isinstance(card, dict):
        try:
            turn.action_cards.append(ActionCard.model_validate(card))
        except ValueError:
            log.warning("tool %s returned an invalid action card", block.name)
    if data.get("plan"):
        turn.plan_changed = True


async def run_tool(
    services: AgentServices,
    user_id: int,
    run_id: int | None,
    block: BetaToolUseBlock,
    offered: frozenset[str],
    turn: Turn,
) -> BetaToolResultBlockParam:
    if block.name not in offered:
        log.warning("refused tool %s: not offered in this run", block.name[:64])
        return _refused(block, f"Tool {block.name[:64]!r} is not available in this run.")
    if turn.tools_ran >= MAX_TOOL_CALLS_PER_RUN:
        log.warning("refused tool %s: the tool budget is exceeded", block.name[:64])
        turn.over_budget = True
        return _refused(block, TOOL_BUDGET_EXCEEDED.format(limit=MAX_TOOL_CALLS_PER_RUN))
    try:
        result = await services.execute_tool(user_id, run_id, block)
    except Exception:  # an executor bug must not break the tool_result pairing
        log.exception("tool %s crashed", block.name)
        result = {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": "Internal error while running the tool; nothing was changed by it.",
            "is_error": True,
        }
    result["tool_use_id"] = block.id
    turn.tools_ran += 1
    _collect_ui(turn, block, result)
    return result


def _nudge(phrases: Sequence[str], lang: str) -> str:
    language = "Romanian" if lang == "ro" else "English"
    quoted = ", ".join(f'"{p}"' for p in dict.fromkeys(phrases))
    return (
        f"(Style check: your last reply used phrases CashGuard never uses: {quoted}. "
        f"Write the same reply again, same facts and numbers, without them, in {language}.)"
    )


async def _ask(
    llm: LLMClient,
    system: Sequence[str],
    messages: list[BetaMessageParam],
    tools: Sequence[BetaToolParam],
    deadline: float | None,
) -> BetaMessage:
    """One Claude call, bounded by the run's deadline (the event loop's clock), if any."""
    if deadline is None:
        return await llm.create(system, messages, tools)
    async with asyncio.timeout_at(deadline):
        return await llm.create(system, messages, tools)


async def converse(
    llm: LLMClient,
    services: AgentServices,
    user_id: int,
    run_id: int | None,
    setup: RunSetup,
    system: Sequence[str],
    messages: list[BetaMessageParam],
    turn: Turn,
    *,
    max_iterations: int,
    deadline: float | None = None,
) -> None:
    """The loop proper. Raises the LLM errors (and `TimeoutError` past `deadline`); fills `turn`
    (text, or a fallback reason)."""
    offered = frozenset(tool["name"] for tool in setup.tools)
    regenerated = False
    for _ in range(max_iterations):
        resp = await _ask(llm, system, messages, setup.tools, deadline)
        if resp.stop_reason == "tool_use" and turn.over_budget:
            log.warning("tool calls after the tool budget was exceeded: template reply")
            turn.fallback = "loop_limit"
            return
        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            results = [
                await run_tool(services, user_id, run_id, block, offered, turn)
                for block in resp.content
                if block.type == "tool_use"
            ]
            messages.append({"role": "user", "content": results})
            continue
        if resp.stop_reason != "end_turn":
            log.warning("stop_reason %s: template reply", resp.stop_reason)
            turn.fallback = "refusal" if resp.stop_reason == "refusal" else "llm_down"
            return
        text = "".join(block.text for block in resp.content if block.type == "text").strip()
        if not text:
            turn.fallback = "llm_down"
            return
        banned = find_banned(text)
        if not banned:
            turn.text = text
            return
        if regenerated:
            log.warning("banned phrase after regeneration: template reply")
            turn.fallback = "loop_limit" if turn.tools_ran else "llm_down"
            return
        regenerated = True
        messages.append({"role": "assistant", "content": resp.content})
        messages.append(
            {"role": "user", "content": _nudge([m.phrase for m in banned], setup.language)}
        )
    log.warning("loop limit (%d iterations) reached", max_iterations)
    turn.fallback = "loop_limit"


# ── speak_text (A11: `app.agent.language.make_speak_text`) ──────────────────────────────────


def speak_text_for(text: str, lang: str) -> str:
    """At most 2 sentences, no markdown or emoji, "77 la sută", "cam", amounts read aloud."""
    return make_speak_text(text, lang)


def _clip(text: str, limit: int) -> str:
    """At most `limit` characters, cut at a word boundary."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{cut}…"


def build_result(
    turn: Turn, setup: RunSetup, *, speak: bool, fallback_text: str | None = None
) -> AgentResult:
    """The §15 result. A fallback carries no chips or cards (they belonged to the failed run)."""
    lang = setup.language
    if turn.text is not None and turn.fallback is None:
        text = _clip(turn.text, MAX_TEXT)
        replies, cards = tuple(turn.quick_replies), tuple(turn.action_cards)
    else:
        text = fallback_text or fallback_reply(turn.fallback or "llm_down", lang)
        replies, cards = (), ()
    ref = setup.open_question.transaction_id if setup.open_question else None
    return AgentResult(
        text=text,
        speak_text=speak_text_for(text, lang) if speak else None,
        quick_replies=replies,
        action_cards=cards,
        plan_changed=turn.plan_changed,
        ref_transaction_id=ref,
    )


def _prompt_kind(trigger: str) -> PromptKind:
    return "onboarding" if trigger == "onboarding" else "chat"


async def run_agent(
    user_id: int,
    trigger: str,
    user_message: str | None,
    input_mode: str = "text",
    *,
    run_id: int | None = None,
    event_id: int | None = None,
    llm: LLMClient | None = None,
    services: AgentServices | None = None,
) -> AgentResult:
    """One chat run (§15). Never raises for an LLM failure, a timeout or a bug in the loop: the
    user gets a template, the run is marked failed, pending events stay pending (arch 11)."""
    services = services or get_agent_services()
    llm = llm or get_llm()
    if user_message is not None:
        user_message = cap_user_text(user_message)
    setup = await services.setup(user_id, trigger, event_id)
    history = await services.history(user_id, HISTORY_LIMIT)
    messages = conversation(history, user_message)
    system = system_parts(_prompt_kind(trigger), setup.snapshot)
    turn = Turn()
    speak = input_mode == "voice" or trigger == "proactive"
    try:
        await converse(
            llm,
            services,
            user_id,
            run_id,
            setup,
            system,
            messages,
            turn,
            max_iterations=get_settings().MAX_AGENT_ITERATIONS,
            deadline=asyncio.get_running_loop().time() + CHAT_RUN_TIMEOUT_S,
        )
    except (LLMUnavailable, TimeoutError) as err:
        log.warning("Claude unavailable: %s", type(err).__name__)
        if user_message is not None and turn.tools_ran == 0:
            turn = await _without_llm(services, user_id, run_id, setup, user_message)
        else:
            turn.fallback = "llm_down"
    except LLMBadRequest as err:
        log.error("Claude rejected the request: %s", err)
        turn.fallback = "llm_down"
    except Exception:  # a bug: the user still gets a template, the traceback only the log
        log.exception("agent run failed: template reply")
        turn.fallback = "llm_down"
    result = build_result(turn, setup, speak=speak)
    failed = turn.fallback is not None or turn.without_llm
    await services.finish_run(run_id, "failed" if failed else "completed", turn.fallback)
    return result


async def _without_llm(
    services: AgentServices, user_id: int, run_id: int | None, setup: RunSetup, user_message: str
) -> Turn:
    """A9: the demo's chips still work without Claude (the same executor, so the same state)."""
    offered = frozenset(tool["name"] for tool in setup.tools)
    turn = Turn(without_llm=True)
    scratch = Turn()  # the answer brings its own chips and cards; keep only plan_changed

    async def execute(block: BetaToolUseBlock) -> BetaToolResultBlockParam:
        return await run_tool(services, user_id, run_id, block, offered, scratch)

    answer = await answer_without_llm(
        user_message,
        open_question=setup.open_question,
        pots=setup.pots,
        lang=setup.language,
        execute=execute,
    )
    turn.text = answer.text
    turn.quick_replies = list(answer.quick_replies)
    turn.action_cards = list(answer.action_cards)
    turn.plan_changed = scratch.plan_changed
    turn.tools_ran = scratch.tools_ran
    return turn
