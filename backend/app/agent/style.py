"""The banned-phrase checker (arch 6.9, D33): judgmental wording in Romanian and English text.

A6 checks Claude's final reply with it (a hit → regenerate once, then the template), A7 the spoken
question, B13 every notification template. Policy (A5 plan Q1, approved): every standalone «iar»
and «de ce» is a hit, even in the neutral sense ("and", "de ce ai nevoie"); the prompt tells
Claude never to write them.

How a text is matched (every match maps back to offsets in the original text):
- each character is folded with C1's `fold_char` (D48: case, diacritics, apostrophe/dash variants,
  invisible characters), with Cyrillic/Greek look-alikes of Latin letters mapped here, and only
  here: the shared fold must leave real Cyrillic alone;
- only letters and decimal digits of the *original* text are word characters, so "again\u00b9" and
  "again\u2122" still end the word;
- the words of a phrase may be separated by spaces, hyphens, markdown (* _ ~ `), symbols and
  emoji, simple formatting tags (<b>, </em>, <br/>) and soft hyphens, but not by sentence
  punctuation ("din, nou" is clean);
- a second reading removes soft hyphens and joins a "-" + line break inside a word, so a word
  hyphenated across lines is found too.
"""

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import Final

from app.i18n.text import fold_char

LANGS: Final = ("ro", "en")

_TAIL: Final = r"[^\W_]*"  # the rest of the word: letters and digits, never `_`
_ADVERB: Final = "(?: (?:never|really|probably|definitely|even|actually|ever|on earth))?"

# Canonical phrase (arch 6.9, in order; «irosi» is the approved Q3 addition) → the folded forms
# that count as it (A5 plan, the A5.1 variant table + the review fixes). In a form, a space is a
# word separator and `'` an optional-or-not apostrophe (also a backtick); see _compile.
_FORMS: Final[dict[str, dict[str, tuple[str, ...]]]] = {
    "ro": {
        "de ce": ("de ce",),
        "prea mult": ("prea mult(?:a|e|i|or|ora)?",),
        "risipă": ("risip" + _TAIL,),
        "ar fi trebuit": ("ar fi trebuit",),
        "iar": ("iar(?:a|asi)?",),
        "din nou": ("din nou",),
        "iresponsabil": ("iresponsabil" + _TAIL,),
        "nu-ți permiți": ("nu i?ti(?: ai| o)? (?:mai )?(?:(?:poti|putut) )?permi(?:t|s)" + _TAIL,),
        "irosi": ("iros" + _TAIL,),
    },
    "en": {
        "why did you": (
            "why(?:'?d|" + _ADVERB + " (?:did|didn'?t|do|don'?t|would|wouldn'?t)) you",
        ),
        "too much": ("too (?:much|many)",),
        "waste": ("wast(?:e|ing|age)(?!land)" + _TAIL,),
        "should have": ("should(?:n'?t| not)?" + _ADVERB + " have", "should(?:n'?t)?'?ve"),
        "again": ("again",),
        "irresponsible": ("irresponsib" + _TAIL,),
        "can't afford": ("(?:can'?t|cannot|can not|couldn'?t)" + _ADVERB + " afford",),
    },
}

BANNED_PHRASES: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {lang: tuple(forms) for lang, forms in _FORMS.items()}
)

_SEPARATOR_MARK: Final = "\x1f"  # symbols, emoji, formatting tags, soft hyphens
_NON_WORD_MARK: Final = "\x00"  # other non-letters that fold to a letter or digit (\u00b9, \u00bd)
_SEPARATOR: Final = r"[\s\-*_~`\x1f]+"  # bounded by the text; one class, nothing nested
_MARKDOWN: Final = frozenset("*_~`")
_SOFT_HYPHEN: Final = "\u00ad"
_LINE_BREAKS: Final = frozenset("\n\r\x0b\x0c\x85\u2028\u2029")
_TAG: Final = re.compile(
    r"</?(?:a|b|i|u|s|em|strong|br|p|span|div|small|sub|sup|mark|del|ins|code|li|ul|ol|h[1-6])"
    r"\s*/?>",
    re.IGNORECASE,
)

# Cyrillic and Greek letters that look like Latin ones, both cases (review finding 9). Applied in
# this module only: the shared fold must leave real Cyrillic and Greek text alone.
_CONFUSABLES: Final[dict[str, str]] = {
    look_alike: latin
    for look_alikes, latin_letters in (
        ("\u0430\u0441\u0435\u0456\u0458\u043e\u0440\u0455", "aceijops"),  # Cyrillic
        ("\u0445\u0443\u0501\u04bb\u051b\u051d\u04af", "xydhqwy"),  # Cyrillic
        ("\u0410\u0412\u0421\u0415\u041d\u0406\u0408\u041a", "ABCEHIJK"),  # Cyrillic
        ("\u041c\u041e\u0420\u0405\u0422\u0425\u0423\u04ae", "MOPSTXYY"),  # Cyrillic
        ("\u04ba\u051a\u051c", "HQW"),  # Cyrillic
        ("\u03b1\u03b5\u03b9\u03bf\u03bd\u03c4\u03ba\u03c1", "aeiovtkp"),  # Greek
        ("\u03c7\u03c5\u03f2\u03f3", "xucj"),  # Greek
        ("\u0391\u0392\u0395\u0396\u0397\u0399\u039a\u039c", "ABEZHIKM"),  # Greek
        ("\u039d\u039f\u03a1\u03a4\u03a5\u03a7\u03f9\u037f", "NOPTYXCJ"),  # Greek
    )
    for look_alike, latin in zip(look_alikes, latin_letters, strict=True)
}


def _compile(forms: tuple[str, ...]) -> re.Pattern[str]:
    body = "|".join(f.replace("'", "['`]").replace(" ", _SEPARATOR) for f in forms)
    # Letters and digits only are word characters (`\b` would also count `_`).
    return re.compile(rf"(?<![^\W_])(?:{body})(?![^\W_])")


_PATTERNS: Final[dict[str, tuple[tuple[str, re.Pattern[str]], ...]]] = {
    lang: tuple((phrase, _compile(forms)) for phrase, forms in phrases.items())
    for lang, phrases in _FORMS.items()
}


@lru_cache(maxsize=8192)
def _piece(ch: str) -> str:
    """What one original character becomes in the text the patterns run on."""
    if ch == _SOFT_HYPHEN:
        return _SEPARATOR_MARK  # the joined reading removes it again
    if ch in _MARKDOWN:
        return ch
    folded = "".join(_CONFUSABLES.get(c, c) for c in fold_char(_CONFUSABLES.get(ch, ch)))
    if folded in ("", " ", "-", "'"):
        return folded
    category = unicodedata.category(ch)
    if category[0] == "L" or category == "Nd":
        return folded
    if category in ("So", "Sk"):
        return _SEPARATOR_MARK
    return _NON_WORD_MARK if any(c.isalnum() for c in folded) else folded


def _joined(text: str, pieces: list[str]) -> list[str]:
    """The reading with soft hyphens removed and "-" + line break inside a word joined."""
    joined = ["" if ch == _SOFT_HYPHEN else piece for ch, piece in zip(text, pieces, strict=True)]
    if _LINE_BREAKS.isdisjoint(text):
        return joined
    for dash, piece in enumerate(pieces):
        if piece != "-":
            continue
        before = dash - 1
        while before >= 0 and not joined[before]:
            before -= 1
        after, line_break = dash + 1, False
        while after < len(text) and joined[after] in ("", " "):
            line_break = line_break or text[after] in _LINE_BREAKS
            after += 1
        if (
            line_break
            and before >= 0
            and joined[before][-1].isalnum()
            and after < len(text)
            and joined[after][0].isalnum()
        ):
            joined[dash:after] = [""] * (after - dash)
    return joined


def _readings(text: str) -> list[list[str]]:
    pieces = [_piece(ch) for ch in text]
    if "<" in text:
        for tag in _TAG.finditer(text):
            pieces[tag.start() : tag.end()] = [_SEPARATOR_MARK] * (tag.end() - tag.start())
    joined = _joined(text, pieces)
    return [pieces] if joined == pieces else [pieces, joined]


@dataclass(frozen=True, slots=True)
class BannedMatch:
    """One banned phrase found in a text; `start` / `end` index the original text."""

    phrase: str  # the canonical phrase from BANNED_PHRASES, e.g. "risipă"
    lang: str  # "ro" | "en"
    start: int
    end: int
    text: str  # == text[start:end], e.g. "Risipa"


def find_banned(text: str, lang: str | None = None) -> list[BannedMatch]:
    """Every banned phrase in `text`, in text order. `lang` picks the list; None checks both
    (use it for Claude's replies: the user may switch language mid-conversation)."""
    if not isinstance(text, str):
        raise TypeError(f"text must be a str, got {type(text).__name__}")
    langs: tuple[str, ...]
    if lang is None:
        langs = LANGS
    elif lang in LANGS:
        langs = (str(lang),)
    else:
        raise ValueError(f"unsupported language {lang!r}: expected 'ro', 'en' or None")

    found: dict[tuple[str, str, int], BannedMatch] = {}  # one match per (lang, phrase, start)
    for pieces in _readings(text):
        folded = "".join(pieces)
        origin = [i for i, piece in enumerate(pieces) for _ in piece]
        for code in langs:
            for phrase, pattern in _PATTERNS[code]:
                for m in pattern.finditer(folded):
                    start = origin[m.start()]
                    # Up to the next kept character, so the marks and invisibles of the last
                    # letter are inside the span; at least past the last matched character.
                    end = origin[m.end()] if m.end() < len(origin) else len(text)
                    end = max(end, origin[m.end() - 1] + 1)
                    match = BannedMatch(phrase, code, start, end, text[start:end])
                    found.setdefault((code, phrase, start), match)
    return sorted(found.values(), key=lambda m: (m.start, m.end))
