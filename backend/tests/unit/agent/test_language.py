"""A11: language detection and the spoken form of a reply (arch 6.9)."""

import pytest

from app.agent.language import detect_language, language_scores, make_speak_text
from app.agent.loop import speak_text_for
from app.domain.enums import Language

RO, EN = Language.RO, Language.EN


# ── detect_language ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Am luat si pt colegi", RO),  # no diacritics
        ("I bought it for my colleagues", EN),
        ("am dat split cu colegii", RO),  # code-switching
        ("Am luat și pentru colegi, suntem cinci.", RO),
        ("Nu, a fost doar pentru mine", RO),
        ("No, it was just for me", EN),
        ("Every Friday we have lunch with the team", EN),
        ("În fiecare vineri mâncăm cu echipa", RO),
        ("Mulțumesc", RO),  # one word, but with diacritics
    ],
)
@pytest.mark.parametrize("current", list(Language))
def test_detects_the_language(text: str, expected: Language, current: Language) -> None:
    assert detect_language(text, current) is expected


@pytest.mark.parametrize("text", ["ok", "5", "", "   ", "👍", "OK!", "Netflix", "split 50/50"])
@pytest.mark.parametrize("current", list(Language))
def test_short_or_ambiguous_text_keeps_the_current_language(text: str, current: Language) -> None:
    assert detect_language(text, current) is current


def test_a_tie_keeps_the_current_language() -> None:
    assert language_scores("in a") == (2, 2)
    assert detect_language("in a", EN) is EN
    assert detect_language("in a", RO) is RO


# ── make_speak_text ──────────────────────────────────────────────────────────────────────────


def test_no_markdown_no_emoji_at_most_two_sentences() -> None:
    text = "**Gata!** 🎉 Partea ta a fost ~100 de lei. Vezi [planul](https://x). Hai."
    assert make_speak_text(text, RO) == "Gata! Partea ta a fost cam 100 de lei."


def test_lines_and_list_markers_become_sentences() -> None:
    text = "## Variante\n- mutăm termenul\n- *punem* 200 de lei în plus\n> notă"
    assert make_speak_text(text, RO) == "Variante. mutăm termenul."


@pytest.mark.parametrize(
    ("text", "lang", "spoken"),
    [
        ("Șansa e 77%.", RO, "Șansa e 77 la sută."),
        ("The chance is 77%.", EN, "The chance is 77 percent."),
        ("Șansa e 12,5 %.", RO, "Șansa e 12,5 la sută."),
        ("~3.000 lei", RO, "cam 3000 de lei"),
        ("~3,000 lei", EN, "about 3000 lei"),
        ("≈ 50 lei", EN, "about 50 lei"),
    ],
)
def test_percent_and_about(text: str, lang: Language, spoken: str) -> None:
    assert make_speak_text(text, lang) == spoken


@pytest.mark.parametrize(
    ("text", "lang", "spoken"),
    [
        (
            "Am mutat cumpărăturile la 1.890 lei/lună.",
            RO,
            "Am mutat cumpărăturile la 1890 de lei/lună.",
        ),
        ("Partea ta: 100 lei.", RO, "Partea ta: 100 de lei."),
        ("Ai 19 lei.", RO, "Ai 19 lei."),
        ("Ai 101 lei.", RO, "Ai 101 lei."),
        ("Ai 1 leu.", RO, "Ai 1 leu."),
        ("Azi: 29,80 lei.", RO, "Azi: 29 de lei și 80 de bani."),
        ("Azi: 30,05 lei.", RO, "Azi: 30 de lei și 5 bani."),
        ("Azi: 1.500,50 lei.", RO, "Azi: 1500 de lei și 50 de bani."),
        ("Sold: -30,40 lei.", RO, "Sold: minus 30 de lei și 40 de bani."),
        ("Today: 29.80 lei.", EN, "Today: 29 lei and 80 bani."),
        ("Your share: 10,000 lei.", EN, "Your share: 10000 lei."),
        ("Only 500 RON.", EN, "Only 500 lei."),
        ("Ai 2 cafele.", RO, "Ai 2 cafele."),  # not money
    ],
)
def test_amounts_are_read_naturally(text: str, lang: Language, spoken: str) -> None:
    assert make_speak_text(text, lang) == spoken


def test_the_spoken_text_fits_300_characters() -> None:
    spoken = make_speak_text("cuvânt " * 200, EN)
    assert len(spoken) <= 300
    assert spoken.endswith("…")


def test_the_loop_uses_it() -> None:
    text = "Gata! Partea ta: 100 lei, șansa 77%. Mai mult text."
    assert speak_text_for(text, "ro") == make_speak_text(text, RO)
    assert speak_text_for(text, "ro") == "Gata! Partea ta: 100 de lei, șansa 77 la sută."


def test_a_unicode_minus_and_one_ban() -> None:
    assert make_speak_text(f"Sold: {chr(0x2212)}30 lei.", RO) == "Sold: minus 30 de lei."
    assert make_speak_text("Left: 2.01 lei.", EN) == "Left: 2 lei and 1 ban."
    assert make_speak_text("Rest: 2,01 lei.", RO) == "Rest: 2 lei și 1 ban."
