"""Text folding: the one matching key for aliases, banned phrases and keywords (C1.1, D48).

`fold` is defined character by character, so `fold(s) == "".join(fold_char(c) for c in s)` and a
match in the folded text maps back to the original characters (A5's `find_banned`). It removes
nothing but marks, format and invisible characters: no strip, no whitespace collapsing;
punctuation, digits and underscores stay. Cleanup for merchant strings is C2's, on top of it.
"""

import unicodedata
from functools import lru_cache
from typing import Final

# Unified *before* NFKD (which turns U+00B4 into a space plus a combining accent).
_APOSTROPHES: Final = frozenset(
    "\u2019\u2018\u02bc\u00b4`\u201b\u02bb\u2032\uff07\u02b9\u2035\u02c8\ua78c"
)
_MINUS_SIGNS: Final = frozenset("\u2212")  # dashes outside category Pd (every Pd is a dash)
_DROPPED_CATEGORIES: Final = frozenset({"Mn", "Me", "Cf"})  # marks, enclosing marks, format
# Default_Ignorable_Code_Point (Unicode 15.0, DerivedCoreProperties.txt): render as nothing.
# Most are Mn / Cf already; the Hangul fillers are letters and some ranges are unassigned.
_DEFAULT_IGNORABLE_RANGES: Final = (
    (0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5),
    (0x180B, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F), (0x3164, 0x3164),
    (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF),
)  # fmt: skip
_INVISIBLE: Final = frozenset(
    {chr(code) for start, end in _DEFAULT_IGNORABLE_RANGES for code in range(start, end + 1)}
    | {"\u2800"}  # BRAILLE PATTERN BLANK: a symbol, not ignorable, but just as blank
)


def _punctuation(ch: str) -> str | None:
    if ch in _APOSTROPHES:
        return "'"
    if ch in _MINUS_SIGNS or unicodedata.category(ch) == "Pd":
        return "-"
    return None


def _dropped(ch: str) -> bool:
    return ch in _INVISIBLE or unicodedata.category(ch) in _DROPPED_CATEGORIES


@lru_cache(maxsize=4096)
def fold_char(ch: str) -> str:
    """Fold one character: apostrophe / dash variants → `'` / `-`, NFKD, drop marks, format and
    invisible characters (and spacing diacritics), any whitespace (NBSP, newline, tab…) → one
    space, casefold. May return "" or several characters; never raises on a code point."""
    if len(ch) != 1:
        raise ValueError(f"fold_char takes exactly one character, got {len(ch)}")
    mapped = _punctuation(ch)
    if mapped is not None:
        return mapped
    parts = unicodedata.normalize("NFKD", ch)
    if len(parts) > 1 and parts[0] == " " and all(_dropped(part) for part in parts[1:]):
        return ""  # a spacing diacritic (U+00A8, U+00B8, U+02D8…): a space would split the word
    out: list[str] = []
    for part in parts:
        mapped = _punctuation(part)
        if mapped is not None:
            out.append(mapped)
        elif _dropped(part):
            continue
        elif part.isspace():
            out.append(" ")
        else:
            out.append(part)
    # casefold runs last and can produce a variant again (U+A78B → U+A78C, an apostrophe).
    return "".join(_punctuation(c) or c for c in "".join(out).casefold())


def fold(text: str) -> str:
    """Case- and diacritics-insensitive key: 'Cărturești' → 'carturesti'; s/t with a cedilla
    or a comma below → s/t."""
    return "".join(map(fold_char, text))
