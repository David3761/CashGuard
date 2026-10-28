"""C1.1: `fold` / `fold_char`, the one matching key for aliases, banned phrases and keywords.

Consumers: C1's alias-uniqueness test, C2 normalisation, C4/C5 keyword matching, A5 `find_banned`
(which needs per-character folding to map matches back to offsets in the original text).
Invisible and look-alike characters are written as escapes so every case is explicit.
"""

import sys
import time
import unicodedata

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.i18n.text import fold, fold_char

# Any character a Python string can hold. st.characters() never yields lone surrogates and
# rarely yields marks, so those are mixed in explicitly (surrogateescape decoding produces them).
ANY_TEXT = st.text(
    st.one_of(
        st.characters(),
        st.characters(categories=["Mn", "Me", "Cf", "Zs", "Zl", "Zp", "Pd", "Lm", "Sk"]),
        st.integers(0xD800, 0xDFFF).map(chr),
        st.integers(0, sys.maxunicode).map(chr),
    )
)

APOSTROPHES = ["\u2019", "\u2018", "\u02bc", "\u00b4", "`", "\u201b", "\u02bb", "\u2032",
               "\uff07"]  # fmt: skip
DASHES = ["\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015", "\u2212", "\ufe58",
          "\ufe63", "\uff0d"]  # fmt: skip
INVISIBLES = ["\u200b", "\u200c", "\u200d", "\u2060", "\u00ad", "\ufeff", "\u200e",
              "\u200f", "\u202e", "\u2066", "\u061c"]  # fmt: skip
SPACES = ["\u00a0", "\u202f", "\u2009", "\u2007", "\u3000", "\u1680", "\t", "\n", "\r",
          "\u2028", "\u2029", "\u0085"]  # fmt: skip


def _clean_problems(out: str) -> list[str]:
    """What must never be left in folded text (empty list = clean)."""
    problems = []
    for ch in out:
        if unicodedata.category(ch) in {"Mn", "Me", "Cf"}:
            problems.append(f"mark/format {ord(ch):#06x}")
        if ch.isspace() and ch != " ":
            problems.append(f"non-plain space {ord(ch):#06x}")
        if ch in APOSTROPHES or ch in DASHES:
            problems.append(f"punctuation variant {ord(ch):#06x}")
    if out != out.casefold():
        problems.append("not casefolded")
    return problems


# ── happy path ──────────────────────────────────────────────────────────────────────────


def test_fold_lowercases_and_strips_romanian_diacritics() -> None:
    assert fold("Cărturești Verona") == "carturesti verona"
    assert fold("MEGA IMAGE") == "mega image"
    assert fold("Pușculiță ÎNCEPUTUL ȘCOLII") == "pusculita inceputul scolii"


def test_fold_keeps_digits_underscores_and_other_punctuation() -> None:
    # Nothing but marks and format characters is removed: C2 and A5 build on top of it.
    assert fold("PAYU*EMAG.RO 0451 Shop&Go snake_case!") == "payu*emag.ro 0451 shop&go snake_case!"


# ── language: every spelling of the same word gives the same key ────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("\u0219", "s"),  # comma below (correct Romanian)
        ("\u015f", "s"),  # cedilla (older text, bank feeds)
        ("\u0218", "s"),
        ("\u015e", "s"),
        ("\u021b", "t"),
        ("\u0163", "t"),
        ("\u021a", "t"),
        ("\u0162", "t"),
        ("\u0103", "a"),  # a breve
        ("\u0102", "a"),
        ("\u00e2", "a"),  # a circumflex
        ("\u00c2", "a"),
        ("\u00ee", "i"),  # i circumflex
        ("\u00ce", "i"),
    ],
)
def test_fold_char_maps_every_romanian_letter_form_to_ascii(raw: str, expected: str) -> None:
    assert fold_char(raw) == expected


def test_fold_gives_the_same_key_for_composed_and_decomposed_input() -> None:
    word = "Cărturești sâmbătă"
    nfc = unicodedata.normalize("NFC", word)
    nfd = unicodedata.normalize("NFD", word)

    assert nfc != nfd
    assert fold(nfc) == fold(nfd) == "carturesti sambata"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("STRA\u00dfE", "strasse"),
        ("\u0130", "i"),  # capital I with dot: casefold alone would leave i + a combining dot
        ("\u210c", "h"),  # black-letter H: only NFKD turns it into a letter that has a case
        ("\uff2d\uff25\uff27\uff21", "mega"),  # full-width
        ("\ufb01", "fi"),  # ligature
        ("\u216b", "xii"),  # roman numeral twelve
    ],
)
def test_fold_applies_compatibility_forms_and_full_casefolding(raw: str, expected: str) -> None:
    assert fold(raw) == expected


@pytest.mark.parametrize("invisible", INVISIBLES)
def test_fold_drops_invisible_format_characters(invisible: str) -> None:
    # Zero-width space/joiners, word joiner, soft hyphen, BOM, LRM/RLM/ALM and bidi controls
    # must not hide a banned phrase or split an alias.
    assert fold(f"risi{invisible}pă") == "risipa"


@pytest.mark.parametrize("space", SPACES)
def test_fold_turns_every_unicode_space_into_one_plain_space(space: str) -> None:
    assert fold(f"de{space}ce") == "de ce"


def test_fold_never_glues_words_across_a_line_break() -> None:
    # A5: "cheltuit\niar" must still contain the word "iar".
    assert fold("Ai cheltuit\niar\r\ntot\tazi") == "ai cheltuit iar  tot azi"


def test_fold_maps_spaces_one_to_one_without_collapsing() -> None:
    # One output space per input space keeps fold(s) == "".join(fold_char(c) for c in s),
    # which A5 needs to map a match back to the original text.
    assert fold("  shop \u00a0 go\r\n") == "  shop   go  "


@pytest.mark.parametrize("apostrophe", [*APOSTROPHES, "'"])
def test_fold_unifies_apostrophe_variants(apostrophe: str) -> None:
    # U+00B4 is the trap: NFKD alone would turn it into a space plus a combining accent.
    assert fold(f"N{apostrophe}am") == "n'am"


@pytest.mark.parametrize("dash", [*DASHES, "-"])
def test_fold_unifies_dash_variants(dash: str) -> None:
    assert fold(f"Cluj{dash}Napoca") == "cluj-napoca"


# ── boundaries & invalid input ──────────────────────────────────────────────────────────


def test_fold_of_empty_and_blank_text() -> None:
    assert fold("") == ""
    assert fold("   ") == "   "
    assert fold("a") == "a"


def test_fold_char_may_return_nothing_or_several_characters() -> None:
    assert fold_char("\u200b") == ""
    assert fold_char("\u00df") == "ss"
    assert fold_char("\ufb01") == "fi"


@pytest.mark.parametrize("bad", ["", "ab", "a\u0306"])
def test_fold_char_rejects_anything_but_exactly_one_character(bad: str) -> None:
    with pytest.raises(ValueError, match="one character"):
        fold_char(bad)


@pytest.mark.parametrize(
    "kept", [chr(0xD800), chr(0xDFFF), "\ue000", "\u0378", "\x00", "\x07"]
)  # lone surrogates, private use, unassigned, controls
def test_fold_char_keeps_surrogates_private_use_unassigned_and_controls(kept: str) -> None:
    assert fold_char(kept) == kept


# ── invariants (property + exhaustive) ──────────────────────────────────────────────────


@given(ANY_TEXT)
def test_fold_is_the_concatenation_of_fold_char(text: str) -> None:
    assert fold(text) == "".join(fold_char(ch) for ch in text)


@given(ANY_TEXT)
def test_fold_is_idempotent_and_never_raises(text: str) -> None:
    once = fold(text)

    assert fold(once) == once


@given(ANY_TEXT)
def test_fold_output_has_no_marks_invisibles_case_or_variant_punctuation(text: str) -> None:
    assert _clean_problems(fold(text)) == []


def _assigned_characters() -> list[str]:
    return [
        chr(code)
        for code in range(sys.maxunicode + 1)
        if unicodedata.category(chr(code)) not in {"Cn", "Cs", "Co"}
    ]


@pytest.mark.slow  # ~1 s under coverage: 149 251 code points
def test_fold_char_is_a_clean_fixed_point_for_every_assigned_character() -> None:
    # Exhaustive over all assigned code points: since fold is per character, this proves
    # fold(fold(s)) == fold(s) for every string, not only the ones hypothesis happens to try.
    not_fixed: list[str] = []
    dirty: list[str] = []
    marks_kept: list[str] = []
    for ch in _assigned_characters():
        out = fold_char(ch)
        if fold(out) != out:
            not_fixed.append(f"{ord(ch):#06x}")
        if _clean_problems(out):
            dirty.append(f"{ord(ch):#06x}")
        if unicodedata.category(ch) in {"Mn", "Me", "Cf"} and out != "":
            marks_kept.append(f"{ord(ch):#06x}")

    assert not_fixed == []
    assert dirty == []
    assert marks_kept == []  # every combining mark (Mn, Me) and format character (Cf) is dropped


# ── performance ─────────────────────────────────────────────────────────────────────────


def test_fold_of_100_kb_of_adversarial_text_takes_under_a_second() -> None:
    # A5's budget: user / Claude text is folded on every reply. 100 000 *distinct* code points
    # (marks, ligatures, many scripts, the surrogate block) defeat any per-character cache.
    adversarial = "".join(chr(code) for code in range(0x0300, 0x0300 + 100_000))

    started = time.perf_counter()
    fold(adversarial)
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0
