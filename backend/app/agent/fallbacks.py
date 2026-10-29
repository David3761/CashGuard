"""Deterministic fallbacks (A9): the demo's quick replies still work when Claude is down.

A known chip label (RO or EN) becomes the same tool calls Claude would make, run through the same
executor (A3), so the end state matches the LLM path (arch 11, F11):

- "Doar pentru mine" → annotate_transaction(self, purpose by category)
- "Și pentru alții"  → "Câți ați fost?" + chips [2] [3] [4] [5] [6+]  (nothing changes yet)
- "5"               → annotate_transaction(people_count=5, others_will_repay, debtor "colegi")
                      + offer_payment_request (the tap card)
- "Ceva plănuit"    → link to the only active pot; several → "Pentru care plan?" + pot chips;
                      a pot name → link to it; no pot → annotate(planned_event)
- "Prefer să nu spun" → annotate(unknown) + a suppress rule for similar payments

Anything else (or no open question) → the polite LLM-down reply, and nothing is changed.
"""

import json
import logging
import unicodedata
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Final

from anthropic.types.beta import BetaToolResultBlockParam, BetaToolUseBlock

from app.agent.templates import (
    HOW_MANY_OPTIONS,
    QUESTION_REPLY_KEYS,
    QUICK_REPLIES,
    fallback_reply,
    how_many_followup,
)
from app.domain.results import ActionCard
from app.i18n.format import format_money, format_money_in_sentence

log = logging.getLogger(__name__)

Execute = Callable[[BetaToolUseBlock], Awaitable[BetaToolResultBlockParam]]


@dataclass(frozen=True, slots=True)
class OpenQuestion:
    """The transaction the user is being asked about (the snapshot's OPEN QUESTION block)."""

    transaction_id: int
    amount: Decimal
    merchant: str
    category: str
    merchant_id: str | None = None
    agent_event_id: int | None = None
    ask_what_item: bool = False


@dataclass(frozen=True, slots=True)
class PotRef:
    pot_id: int
    name: str


@dataclass(frozen=True, slots=True)
class FallbackAnswer:
    text: str
    quick_replies: tuple[str, ...] = ()
    action_cards: tuple[ActionCard, ...] = field(default=())


# "Doar pentru mine": the everyday categories are living costs, the rest a treat (no judgement).
_ESSENTIAL: Final = frozenset(
    {
        "groceries",
        "transport",
        "fuel",
        "health_pharmacy",
        "utilities",
        "telecom",
        "housing_rent",
        "household_goods",
        "personal_care",
        "kids",
        "pets",
        "education",
    }
)
DEBTOR_LABEL: Final[Mapping[str, str]] = MappingProxyType({"ro": "colegi", "en": "colleagues"})

_TEXTS: Final[Mapping[str, Mapping[str, str]]] = MappingProxyType(
    {
        "just_me": {
            "ro": "Am notat: {amount} la {merchant}, doar pentru tine. Planul tău e la zi.",
            "en": "Noted: {amount} at {merchant}, just for you. Your plan is up to date.",
        },
        "split": {
            "ro": "Am înțeles! Partea ta e {share}. Ai {owed} de recuperat de la {debtor}.",
            "en": "Got it! Your share is {share}. You have {owed} to get back from {debtor}.",
        },
        "split_plain": {
            "ro": "Am notat că ați fost {count}. Planul tău e la zi.",
            "en": "Noted that there were {count} of you. Your plan is up to date.",
        },
        "card": {
            "ro": "Trimite cererea ({count} \u00d7 {share})",
            "en": "Send the request ({count} \u00d7 {share})",
        },
        "linked": {
            "ro": "Am legat plata de {amount} de „{pot}”. Planul tău e la zi.",
            "en": "I linked the {amount} payment to “{pot}”. Your plan is up to date.",
        },
        "which_pot": {"ro": "Pentru care plan a fost?", "en": "Which plan was it for?"},
        "planned": {
            "ro": "Am notat-o ca ceva plănuit. Planul tău e la zi.",
            "en": "Noted it as something planned. Your plan is up to date.",
        },
        "rather_not_say": {
            "ro": "Sigur, nicio problemă. N-o să te mai întreb de plăți ca asta.",
            "en": "Sure, no problem. I won't ask about payments like this one.",
        },
    }
)


def _norm(text: str) -> str:
    """Case-, diacritics- and punctuation-insensitive form of a chip label."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    bare = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(bare.replace("\u2019", "'").split()).strip(" .!?,;:")


_LABEL_KEYS: Final[Mapping[str, str]] = MappingProxyType(
    {_norm(QUICK_REPLIES[key][lang]): key for key in QUESTION_REPLY_KEYS for lang in ("ro", "en")}
)


def chip_key(user_message: str) -> str | None:
    """The chip a message is: a QUESTION_REPLY_KEYS key, "count:N", or None."""
    norm = _norm(user_message)
    if norm in _LABEL_KEYS:
        return _LABEL_KEYS[norm]
    if norm in HOW_MANY_OPTIONS:
        return f"count:{norm.rstrip('+')}"
    return None


def _data(result: BetaToolResultBlockParam) -> dict[str, Any]:
    content = result.get("content")
    try:
        data = json.loads(content) if isinstance(content, str) else None
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _money(value: object) -> Decimal | None:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return amount if amount.is_finite() and amount >= 0 else None


class _Calls:
    """Synthesised tool calls with ids no real response uses."""

    def __init__(self, execute: Execute) -> None:
        self._execute = execute
        self._n = 0

    async def __call__(self, name: str, args: dict[str, object]) -> dict[str, Any] | None:
        """The result data, or None when the tool failed."""
        self._n += 1
        block = BetaToolUseBlock(
            id=f"toolu_fallback_{self._n}", name=name, input=args, type="tool_use"
        )
        result = await self._execute(block)
        if result.get("is_error"):
            log.warning("fallback tool %s failed", name)
            return None
        return _data(result)


async def answer_without_llm(
    user_message: str,
    *,
    open_question: OpenQuestion | None,
    pots: Sequence[PotRef],
    lang: str,
    execute: Execute,
) -> FallbackAnswer:
    """The deterministic answer to a chip while Claude is down (see the module docstring)."""
    sorry = FallbackAnswer(fallback_reply("llm_down", lang))
    key = chip_key(user_message)
    pot = _pot_named(user_message, pots)
    if open_question is None or (key is None and pot is None):
        return sorry
    q, call = open_question, _Calls(execute)
    texts = {name: forms[lang] for name, forms in _TEXTS.items()}
    tx = q.transaction_id

    if key == "for_others":
        return FallbackAnswer(how_many_followup(lang), tuple(HOW_MANY_OPTIONS))

    if key is not None and key.startswith("count:"):
        count = int(key.removeprefix("count:"))
        debtor = DEBTOR_LABEL[lang]
        data = await call(
            "annotate_transaction",
            {
                "transaction_id": tx,
                "purpose": "on_behalf_of_others",
                "beneficiary": "shared",
                "people_count": count,
                "others_will_repay": True,
                "debtor_label": debtor,
            },
        )
        if data is None:
            return sorry
        return await _split_answer(call, data, count, debtor, texts, lang)

    if key == "just_me":
        purpose = "essential_living" if q.category in _ESSENTIAL else "unplanned_discretionary"
        data = await call(
            "annotate_transaction",
            {"transaction_id": tx, "purpose": purpose, "beneficiary": "self"},
        )
        if data is None:
            return sorry
        amount = format_money_in_sentence(q.amount, lang)
        return FallbackAnswer(
            texts["just_me"].format_map({"amount": amount, "merchant": q.merchant})
        )

    if key == "planned" and len(pots) > 1 and pot is None:
        return FallbackAnswer(texts["which_pot"], tuple(p.name for p in pots))

    if key == "planned" or pot is not None:
        target = pot or (pots[0] if pots else None)
        if target is None:
            data = await call(
                "annotate_transaction",
                {"transaction_id": tx, "purpose": "planned_event", "beneficiary": "self"},
            )
            return sorry if data is None else FallbackAnswer(texts["planned"])
        data = await call(
            "link_transaction_to_pot", {"transaction_id": tx, "pot_id": target.pot_id}
        )
        if data is None:
            return sorry
        amount = format_money_in_sentence(q.amount, lang)
        return FallbackAnswer(texts["linked"].format_map({"amount": amount, "pot": target.name}))

    # rather_not_say: no reading, and don't ask about similar payments
    data = await call(
        "annotate_transaction", {"transaction_id": tx, "purpose": "unknown", "beneficiary": "self"}
    )
    if data is None:
        return sorry
    match: dict[str, object] = (
        {"merchant_id": q.merchant_id} if q.merchant_id else {"category": q.category}
    )
    if (
        await call("create_pattern_rule", {"kind": "suppress", "match": match, "outcome": {}})
        is None
    ):
        log.warning("suppress rule not created; the annotation stands")
    return FallbackAnswer(texts["rather_not_say"])


def _pot_named(user_message: str, pots: Sequence[PotRef]) -> PotRef | None:
    norm = _norm(user_message)
    return next((p for p in pots if _norm(p.name) == norm), None)


async def _split_answer(
    call: _Calls,
    data: dict[str, Any],
    count: int,
    debtor: str,
    texts: Mapping[str, str],
    lang: str,
) -> FallbackAnswer:
    """The F11 reply with the code's numbers, plus the payment-request card. TODO(A3): the
    annotate result carries `effective_amount` and `receivable: {id, amount}`."""
    share = _money(data.get("effective_amount"))
    raw = data.get("receivable")
    receivable: dict[str, Any] = raw if isinstance(raw, dict) else {}
    owed = _money(receivable.get("amount"))
    rcv_id = receivable.get("id") or data.get("receivable_id")
    if share is None or owed is None:
        return FallbackAnswer(texts["split_plain"].format_map({"count": count}))
    text = texts["split"].format_map(
        {
            "share": format_money_in_sentence(share, lang),
            "owed": format_money_in_sentence(owed, lang),
            "debtor": debtor,
        }
    )
    cards: tuple[ActionCard, ...] = ()
    if isinstance(rcv_id, int) and rcv_id > 0:
        offered = await call("offer_payment_request", {"receivable_id": rcv_id})
        card = offered.get("action_card") if offered else None
        label = texts["card"].format_map({"count": count - 1, "share": format_money(share, lang)})
        if offered is not None:
            cards = (
                ActionCard.model_validate(card)
                if isinstance(card, dict)
                else ActionCard(type="request_payment", receivable_id=rcv_id, label=label),
            )
    return FallbackAnswer(text, (), cards)
