"""Text folding: the one matching key for aliases, banned phrases and keywords (C1.1, D48).

`fold` is defined character by character, so `fold(s) == "".join(fold_char(c) for c in s)` and a
match in the folded text maps back to the original characters (A5's `find_banned`). It removes
nothing but marks and format characters: no strip, no whitespace collapsing, punctuation, digits
and underscores stay. Cleanup for merchant strings (store numbers, prefixes) is C2's, on top.
"""

import unicodedata
from functools import lru_cache
from typing import Final

# Unified *before* NFKD: NFKD would turn U+00B4 into a space plus a combining accent.
_PUNCTUATION: Final[dict[str, str]] = {
    **dict.fromkeys("\u2019\u2018\u02bc\u00b4`\u201b\u02bb\u2032\uff07", "'"),  # apostrophes
    **dict.fromkeys("\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d", "-"),  # dashes
}
# Combining marks (Mn), enclosing marks (Me) and every format character (Cf: zero-width
# space/joiners, word joiner, soft hyphen, BOM, LRM/RLM, bidi controls).
_DROPPED_CATEGORIES: Final = frozenset({"Mn", "Me", "Cf"})


@lru_cache(maxsize=4096)
def fold_char(ch: str) -> str:
    """Fold one character: punctuation variants → `'` / `-`, NFKD, drop Mn / Me / Cf, any
    whitespace (NBSP, newline, tab…) → one space, casefold. May return "" or several characters."""
    if len(ch) != 1:
        raise ValueError(f"fold_char takes exactly one character, got {len(ch)}")
    if ch in _PUNCTUATION:
        return _PUNCTUATION[ch]
    out: list[str] = []
    for part in unicodedata.normalize("NFKD", ch):
        if part in _PUNCTUATION:
            out.append(_PUNCTUATION[part])
        elif unicodedata.category(part) in _DROPPED_CATEGORIES:
            continue
        elif part.isspace():
            out.append(" ")
        else:
            out.append(part)
    return "".join(out).casefold()


def fold(text: str) -> str:
    """Case- and diacritics-insensitive key: 'Cărturești' → 'carturesti'; s/t with a cedilla
    or a comma below → s/t."""
    return "".join(map(fold_char, text))
