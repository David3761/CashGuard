"""A11: the user's language and the spoken form of a reply (arch 6.9, D15), pure.

`detect_language(text, current)`: Romanian diacritics (ă â î ș ț, cedilla forms too) count 2,
every RO / EN function word or common chat word 1 ("am luat si pt colegi" has no diacritics and
is still Romanian). The language wins with a score ≥ 2 and more than the other one. A short text
(one word without diacritics, "ok", "5"), a tie or too little evidence keeps `current`.
Code-switching is normal: "am dat split cu colegii" stays Romanian.

`make_speak_text(text, lang)`: what the voice says (≤ 2 sentences, ≤ 300 characters):
- no markdown (bold, headings, code, quotes, tables, list markers; a link keeps its text), no
  emoji; every line is its own sentence;
- "77%" → "77 la sută" / "77 percent"; "~" / "≈" → "cam" / "about";
- amounts read naturally, without thousands separators: RO "1.500 lei" → "1500 de lei",
  "30,40 lei" → "30 de lei și 40 de bani", "1 leu"; EN "1,500 lei" → "1500 lei",
  "30.40 lei" → "30 lei and 40 bani"; a minus sign → "minus".
"""

import re
import unicodedata
from typing import Final

from app.domain.enums import Language
from app.i18n.format import format_money_in_sentence

MIN_SCORE: Final = 2
DIACRITIC_WEIGHT: Final = 2
SPOKEN_SENTENCES: Final = 2
MAX_SPOKEN: Final = 300  # AgentResult.speak_text (F2 Text300)

RO_DIACRITICS: Final = frozenset("ăâîșțşţĂÂÎȘȚŞŢ")
_RO_TEXT: Final = """
a ai al ale am ar are as au azi ba bani bine ca care cam ce cel cea ceva cine colegi colegii cu
cum cumparat cand da dar dat de deja din doar e ea ei el ele era este eu face facut fi fiecare
foarte fost ieri in inca ii iar imi la le lei lor lui luat luna m ma mai maine mea meu mersi mi
mie mult multumesc ne nimic noi nu o pe pentru platit pot poti prieteni pt sa saptamana se si
sunt ta tau te tot toate tu un una unde unei unui va vineri voi vreau
"""
_EN_TEXT: Final = """
a about all am an and are at be been bought but can colleagues did do does don every for friends
from friday got had has have he how i im in is it its just lunch me money month my no not of on
only or our paid please she so some spent thank thanks that the they this to want was we week
were what when where who why will with would yes you your
"""
RO_WORDS: Final = frozenset(_RO_TEXT.split())
"""Romanian function and chat words, folded (no diacritics: "si" for "și")."""
EN_WORDS: Final = frozenset(_EN_TEXT.split())
"""English function and chat words ("am", "a", "in" are in both: they cancel out)."""

_WORD = re.compile(r"[^\W\d_]+")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_LINE_MARK = re.compile(r"^\s*(?:(?:[-•*+]|\d+[.)])\s+|(?:#{1,6}|>)\s*)", re.MULTILINE)
_MARKUP = re.compile(r"[*_`#>|]+")
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
_PERCENT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
_MONEY = re.compile(
    r"(?<![\d.,])([-\u2212]\s?)?(\d{1,3}(?:[.,\u00a0]\d{3})+|\d+)(?:[.,](\d{1,2}))?(?!\d)"
    r"\s*(?:de\s+)?(?:lei|leu|ron)\b",
    re.IGNORECASE,
)
_ABOUT: Final = {Language.RO: "cam", Language.EN: "about"}
_PERCENT_WORD: Final = {Language.RO: "la sută", Language.EN: "percent"}


# ── detect_language ──────────────────────────────────────────────────────────────────────────


def _fold(word: str) -> str:
    decomposed = unicodedata.normalize("NFKD", word.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def language_scores(text: str) -> tuple[int, int]:
    """(Romanian, English) evidence in `text`."""
    words = [_fold(w) for w in _WORD.findall(text)]
    ro = sum(w in RO_WORDS for w in words)
    en = sum(w in EN_WORDS for w in words)
    if any(ch in RO_DIACRITICS for ch in text):
        ro += DIACRITIC_WEIGHT
    return ro, en


def detect_language(text: str, current: Language) -> Language:
    """The language `text` is written in, or `current` when the text can't tell."""
    words = _WORD.findall(text)
    has_diacritics = any(ch in RO_DIACRITICS for ch in text)
    if len(words) < 2 and not has_diacritics:
        return current
    ro, en = language_scores(text)
    if max(ro, en) < MIN_SCORE or ro == en:
        return current
    return Language.RO if ro > en else Language.EN


# ── make_speak_text ──────────────────────────────────────────────────────────────────────────


def _is_emoji(ch: str) -> bool:
    return unicodedata.category(ch) in ("So", "Sk", "Cs", "Co") or ch in "‍️︎"


def _plain(text: str) -> str:
    """No links, list markers, markup or emoji; a line without an ending becomes a sentence."""
    text = _LINE_MARK.sub("", _LINK.sub(r"\1", text))
    text = _MARKUP.sub("", text)
    text = "".join(ch for ch in text if not _is_emoji(ch))
    lines = [" ".join(line.split()) for line in text.splitlines()]
    lines = [line for line in lines if line]
    ended = [
        line if line[-1] in ".!?…:;," or i == len(lines) - 1 else f"{line}."
        for i, line in enumerate(lines)
    ]
    return " ".join(ended)


def _bani(cents: int, lang: Language) -> str:
    if lang is Language.EN:
        return f"{cents} {'ban' if cents == 1 else 'bani'}"
    if cents == 1:
        return "1 ban"
    return f"{cents} de bani" if cents >= 20 else f"{cents} bani"


def _spoken_money(match: re.Match[str], lang: Language) -> str:
    sign, whole_text, cents_text = match.group(1), match.group(2), match.group(3)
    whole = int(re.sub(r"\D", "", whole_text))
    unit = format_money_in_sentence(whole, lang).split(" ", 1)[1]  # "de lei" / "lei" / "leu"
    spoken = f"{whole} {unit}"
    if cents_text:
        cents = int(cents_text.ljust(2, "0"))
        if cents:
            joiner = "și" if lang is Language.RO else "and"
            spoken = f"{spoken} {joiner} {_bani(cents, lang)}"
    return f"minus {spoken}" if sign else spoken


def _first_sentences(text: str, count: int) -> str:
    return " ".join(_SENTENCE_END.split(text)[:count]).strip()


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{cut}…"


def make_speak_text(text: str, lang: Language | str) -> str:
    """The spoken form of `text`: plain, at most 2 sentences and 300 characters."""
    language = Language(lang)
    spoken = _first_sentences(_plain(text), SPOKEN_SENTENCES)
    spoken = _MONEY.sub(lambda m: _spoken_money(m, language), spoken)
    spoken = _PERCENT.sub(lambda m: f"{m.group(1)} {_PERCENT_WORD[language]}", spoken)
    for mark in ("~", "≈"):
        spoken = spoken.replace(mark, f" {_ABOUT[language]} ")
    return _clip(" ".join(spoken.split()), MAX_SPOKEN)
