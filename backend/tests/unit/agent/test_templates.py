"""A5.3: the deterministic agent texts (RO + EN): question fallback, follow-ups, fallback
replies and quick replies. Happy-path tests (fast mode, agreed with the boss)."""

from decimal import Decimal

import pytest

from app.agent.prompts import instructions_for
from app.agent.style import find_banned
from app.agent.templates import (
    HOW_MANY_OPTIONS,
    OWN_SHARE_REPLY_KEYS,
    QUESTION_REPLY_KEYS,
    QUICK_REPLIES,
    TEMPLATES,
    fallback_reply,
    how_many_followup,
    own_share_followup,
    quick_replies,
    transaction_question,
)


def test_the_question_fallback_in_both_languages() -> None:
    assert (
        transaction_question(Decimal("500"), "Mega Image", "ro")
        == "Am văzut 500 de lei la Mega Image. A fost ceva diferit de obicei?"
    )
    assert (
        transaction_question(Decimal("500"), "Mega Image", "en")
        == "I saw 500 lei at Mega Image. Was it something different from usual?"
    )


def test_the_item_question_when_ask_what_item() -> None:
    assert transaction_question(Decimal("4500"), "eMAG", "ro", ask_what_item=True) == (
        "Ce ți-ai luat de la eMAG?"
    )
    assert transaction_question(Decimal("4500"), "eMAG", "en", ask_what_item=True) == (
        "What did you get from eMAG?"
    )


def test_a_blank_merchant_gives_the_question_without_a_merchant() -> None:
    assert transaction_question(Decimal("19"), "  ", "ro", ask_what_item=True) == (
        "Am văzut o plată de 19 lei. A fost ceva diferit de obicei?"
    )
    assert transaction_question(Decimal("30.40"), "", "en") == (
        "I saw a payment of 30.40 lei. Was it something different from usual?"
    )


def test_the_merchant_is_one_line_and_never_re_expanded() -> None:
    assert transaction_question(Decimal("80"), "Mega\nImage\t ", "ro") == (
        "Am văzut 80 de lei la Mega Image. A fost ceva diferit de obicei?"
    )
    assert "{amount}" in transaction_question(Decimal("80"), "{amount}", "en")


def test_the_follow_ups() -> None:
    assert own_share_followup(Decimal("100"), "ro") == "Partea ta a fost ~100 de lei?"
    assert own_share_followup(Decimal("100"), "en") == "Was your share about 100 lei?"
    assert how_many_followup("ro") == "Câți ați fost, cu tot cu tine?"
    assert how_many_followup("en") == "How many of you were there, including you?"
    assert HOW_MANY_OPTIONS == ("2", "3", "4", "5", "6+")


@pytest.mark.parametrize(
    ("reason", "ro", "en"),
    [
        (
            "llm_down",
            "Am o mică problemă tehnică acum, dar planul tău e la zi. Mai încearcă peste un minut.",
            "I'm having trouble right now, but your plan is still up to date. Try me in a minute.",
        ),
        (
            "loop_limit",
            "N-am reușit să termin tot ce mi-ai cerut. Verifică în aplicație ce s-a actualizat "
            "și spune-mi ce mai lipsește.",
            "I couldn't finish everything you asked. Check the app for what got updated and "
            "tell me what's still missing.",
        ),
        (
            "refusal",
            "La asta nu te pot ajuta acum. Hai să ne uităm la plan, la obiectiv sau la "
            "cheltuielile tale.",
            "I can't help with that one right now. We can look at your plan, your goal or your "
            "spending instead.",
        ),
    ],
)
def test_the_fallback_replies(reason: str, ro: str, en: str) -> None:
    assert fallback_reply(reason, "ro") == ro
    assert fallback_reply(reason, "en") == en


def test_the_quick_replies() -> None:
    assert quick_replies(QUESTION_REPLY_KEYS, "ro") == [
        "Doar pentru mine",
        "Și pentru alții",
        "Ceva plănuit",
        "Prefer să nu spun",
    ]
    assert quick_replies(QUESTION_REPLY_KEYS, "en") == [
        "Just for me",
        "For others too",
        "Something planned",
        "I'd rather not say",
    ]
    assert quick_replies(OWN_SHARE_REPLY_KEYS, "ro") == ["Da", "Altă sumă"]
    assert quick_replies(OWN_SHARE_REPLY_KEYS, "en") == ["Yes", "A different amount"]


def test_the_prompt_offers_exactly_the_template_chips() -> None:
    # The chips Claude offers and the ones A9 maps must be the same labels.
    text = instructions_for("transaction_question")
    for lang, label in (("ro", "Romanian"), ("en", "English")):
        chips = ", ".join(f'"{chip}"' for chip in quick_replies(QUESTION_REPLY_KEYS, lang))
        assert f"{label}: {chips}" in text


def test_every_text_exists_in_both_languages_without_a_banned_phrase() -> None:
    for table in (TEMPLATES, QUICK_REPLIES):
        for key, texts in table.items():
            assert set(texts) == {"ro", "en"}, key
            for text in texts.values():
                assert text, key
                assert find_banned(text) == [], text


@pytest.mark.parametrize("bad", [("fr", "llm_down"), ("ro", "timeout")])
def test_an_unknown_language_or_reason_is_refused(bad: tuple[str, str]) -> None:
    lang, reason = bad
    with pytest.raises(ValueError, match="unknown"):
        fallback_reply(reason, lang)


def test_a_non_positive_amount_or_an_unknown_chip_is_refused() -> None:
    with pytest.raises(ValueError, match="positive amount"):
        transaction_question(Decimal("0"), "Lidl", "ro")
    with pytest.raises(ValueError, match="unknown quick reply"):
        quick_replies(("maybe",), "ro")
