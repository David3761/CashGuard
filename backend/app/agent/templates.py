"""Deterministic agent texts, RO + EN (arch 6.9, 7, 11): the question used when Claude is slow
or down (A7, 5 s), the follow-ups, the fallback replies (A6) and the quick-reply chips (A9 maps
them to actions by key, never by re-typed label).

Amounts go through C1's `format_money_in_sentence` ("80 de lei", "19 lei", EN "80 lei"). A
merchant name is data: it's put on one line and inserted as is, never re-expanded. A filled
template is final: A6/A7 don't re-check it with `find_banned`, because the merchant itself may
contain a banned word ("Din Nou SRL"). No template contains one (tested).
"""

import unicodedata
from collections.abc import Sequence
from decimal import Decimal
from types import MappingProxyType
from typing import Final, Literal

from app.i18n.format import format_money_in_sentence

TEMPLATES: Final = MappingProxyType(
    {
        "question.transaction": {
            "ro": "Am văzut {amount} la {merchant}. A fost ceva diferit de obicei?",
            "en": "I saw {amount} at {merchant}. Was it something different from usual?",
        },
        "question.transaction_no_merchant": {
            "ro": "Am văzut o plată de {amount}. A fost ceva diferit de obicei?",
            "en": "I saw a payment of {amount}. Was it something different from usual?",
        },
        "question.what_item": {
            "ro": "Ce ți-ai luat de la {merchant}?",
            "en": "What did you get from {merchant}?",
        },
        "followup.own_share": {
            "ro": "Partea ta a fost ~{amount}?",
            "en": "Was your share about {amount}?",
        },
        "followup.how_many": {
            "ro": "Câți ați fost, cu tot cu tine?",
            "en": "How many of you were there, including you?",
        },
        "fallback.llm_down": {
            "ro": "Am o mică problemă tehnică acum, dar planul tău e la zi. "
            "Mai încearcă peste un minut.",
            "en": "I'm having trouble right now, but your plan is still up to date. "
            "Try me in a minute.",
        },
        "fallback.loop_limit": {
            "ro": "N-am reușit să termin tot ce mi-ai cerut. Verifică în aplicație ce s-a "
            "actualizat și spune-mi ce mai lipsește.",
            "en": "I couldn't finish everything you asked. Check the app for what got updated "
            "and tell me what's still missing.",
        },
        "fallback.refusal": {
            "ro": "La asta nu te pot ajuta acum. Hai să ne uităm la plan, la obiectiv sau la "
            "cheltuielile tale.",
            "en": "I can't help with that one right now. We can look at your plan, your goal "
            "or your spending instead.",
        },
    }
)

QUICK_REPLIES: Final = MappingProxyType(
    {
        "just_me": {"ro": "Doar pentru mine", "en": "Just for me"},
        "for_others": {"ro": "Și pentru alții", "en": "For others too"},
        "planned": {"ro": "Ceva plănuit", "en": "Something planned"},
        "rather_not_say": {"ro": "Prefer să nu spun", "en": "I'd rather not say"},
        "yes": {"ro": "Da", "en": "Yes"},
        "other_amount": {"ro": "Altă sumă", "en": "A different amount"},
    }
)
QUESTION_REPLY_KEYS: Final = ("just_me", "for_others", "planned", "rather_not_say")
OWN_SHARE_REPLY_KEYS: Final = ("yes", "other_amount")
HOW_MANY_OPTIONS: Final = ("2", "3", "4", "5", "6+")  # the same in both languages (A9)

FallbackReason = Literal["llm_down", "loop_limit", "refusal"]
# A6: refusal → "refusal"; max_tokens, LLMUnavailable, a timeout or an unexpected error →
# "llm_down"; the iteration limit → "loop_limit".


def _text(key: str, lang: str) -> str:
    texts = TEMPLATES.get(key)
    if texts is None or lang not in texts:
        raise ValueError(f"unknown template {key!r} or language {lang!r} (expected 'ro' or 'en')")
    return texts[lang]


def _one_line(merchant: str) -> str:
    """Control, format and line-separator characters become spaces; whitespace collapses."""
    cleaned = "".join(
        " " if unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp") else ch for ch in merchant
    )
    return " ".join(cleaned.split())


def transaction_question(
    amount: Decimal, merchant: str, lang: str, *, ask_what_item: bool = False
) -> str:
    """The spoken question when Claude can't ask it (arch 6.9 template fallback)."""
    if amount <= 0:
        raise ValueError(f"a question needs a positive amount, got {amount}")
    name = _one_line(merchant)
    if not name:
        return _text("question.transaction_no_merchant", lang).format_map(
            {"amount": format_money_in_sentence(amount, lang)}
        )
    if ask_what_item:
        return _text("question.what_item", lang).format_map({"merchant": name})
    return _text("question.transaction", lang).format_map(
        {"amount": format_money_in_sentence(amount, lang), "merchant": name}
    )


def own_share_followup(amount: Decimal, lang: str) -> str:
    """'Partea ta a fost ~100 de lei?' after the code estimated the share (arch F11)."""
    return _text("followup.own_share", lang).format_map(
        {"amount": format_money_in_sentence(amount, lang)}
    )


def how_many_followup(lang: str) -> str:
    """The count question after "Și pentru alții" (chips: HOW_MANY_OPTIONS)."""
    return _text("followup.how_many", lang)


def fallback_reply(reason: str, lang: str) -> str:
    """The reply when the agent can't answer (arch 7, 11)."""
    return _text(f"fallback.{reason}", lang)


def quick_replies(keys: Sequence[str], lang: str) -> list[str]:
    """The chip labels for these keys, in order."""
    try:
        return [QUICK_REPLIES[key][lang] for key in keys]
    except KeyError as error:
        raise ValueError(f"unknown quick reply or language: {error}") from None
