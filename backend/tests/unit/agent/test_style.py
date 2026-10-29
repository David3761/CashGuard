"""A5.1: `find_banned`, the banned-phrase checker of arch 6.9 (D33).

The folding itself (case, diacritics, apostrophe/dash variants, invisible characters) is C1.1's
`fold_char` (D48) and has its own tests; the language and security cases here are integration
tests: they fail if `find_banned` stops folding, or if the shared fold regresses.
Policy (A5 plan Q1, approved): every standalone «iar» / «de ce» is a hit. Invisible and
look-alike characters are written as escapes so every case is explicit.
"""

import sys
import time
import unicodedata
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.agent.style import BANNED_PHRASES, LANGS, BannedMatch, find_banned
from app.domain.enums import Language

# Arch 6.9, verbatim and in order, plus the approved Q3 addition (the boss adds it to 6.9).
ARCH_6_9 = {
    "ro": ("de ce", "prea mult", "risipă", "ar fi trebuit", "iar", "din nou", "iresponsabil",
           "nu-ți permiți"),
    "en": ("why did you", "too much", "waste", "should have", "again", "irresponsible",
           "can't afford"),
}  # fmt: skip
Q3_ADDITIONS = {"ro": ("irosi",), "en": ()}
ALL_PHRASES = [(lang, phrase) for lang in LANGS for phrase in ARCH_6_9[lang] + Q3_ADDITIONS[lang]]

ANY_TEXT = st.text(
    st.one_of(
        st.characters(),
        st.characters(categories=["Mn", "Me", "Cf", "Zs", "Zl", "Zp", "Pd", "Lm", "Sk", "Cc"]),
        st.integers(0xD800, 0xDFFF).map(chr),  # lone surrogates
        st.integers(0, sys.maxunicode).map(chr),
    )
)


def phrases(text: str, lang: str | None = None) -> list[str]:
    return [m.phrase for m in find_banned(text, lang)]


def strip_diacritics(text: str) -> str:
    """Test-only: the text a user types without diacritics."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


# ── happy path ──────────────────────────────────────────────────────────────────────────


def test_find_banned_de_ce_is_a_hit_with_its_original_span() -> None:
    assert find_banned("De ce ai cheltuit atât?", "ro") == [
        BannedMatch(phrase="de ce", lang="ro", start=0, end=5, text="De ce")
    ]


@pytest.mark.parametrize(
    ("text", "lang", "expected"),
    [
        ("Iar ai cheltuit la Mega", "ro", ["iar"]),
        ("Asta e risipa", "ro", ["risipă"]),
        ("Asta e risipă", "ro", ["risipă"]),
        ("Ai cheltuit din nou", "ro", ["din nou"]),
        ("Why did you buy it?", "en", ["why did you"]),
        ("You did it again.", "en", ["again"]),
    ],
)
def test_find_banned_hits_the_spec_cases(text: str, lang: str, expected: list[str]) -> None:
    assert phrases(text, lang) == expected


@pytest.mark.parametrize(("lang", "phrase"), ALL_PHRASES)
def test_every_canonical_phrase_is_found_with_and_without_diacritics(
    lang: str, phrase: str
) -> None:
    template = "Mi-a spus că {} azi." if lang == "ro" else "She said {} today."
    assert phrases(template.format(phrase), lang) == [phrase]
    assert phrases(template.format(strip_diacritics(phrase)), lang) == [phrase]


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("Am înțeles! Cheltuiala ta reală e 100 lei. Ai 400 lei de recuperat de la colegi. "
         "Șansa pentru 10.000 lei: 77% (era 71%).", "ro"),
        ("Got it! Your real spend is 100 lei, and you have 400 lei to get back from your "
         "colleagues. Chance of 10,000 lei: 77% (was 71%).", "en"),
    ],
)  # fmt: skip
def test_the_demo_reply_is_clean(text: str, lang: str) -> None:
    assert find_banned(text, lang) == []
    assert find_banned(text) == []


def test_find_banned_returns_every_hit_in_text_order() -> None:
    text = "Iar ai cheltuit prea mult, din nou."
    found = find_banned(text, "ro")

    assert [(m.phrase, m.start, m.end, m.text) for m in found] == [
        ("iar", 0, 3, "Iar"),
        ("prea mult", 16, 25, "prea mult"),
        ("din nou", 27, 34, "din nou"),
    ]
    assert phrases("iar și iar", "ro") == ["iar", "iar"]


# ── boundaries: whole words only ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("de cele mai multe ori", "ro"),
        ("e mai mult decât atât", "ro"),
        ("de când ai planul?", "ro"),
        ("chiar", "ro"),
        ("iarnă", "ro"),
        ("iarna asta", "ro"),
        ("iarbă", "ro"),
        ("un ziar", "ro"),
        ("whyever", "en"),
        ("against", "en"),
        ("regain", "en"),
        ("wasteland", "en"),
        ("you should", "en"),
    ],
)
def test_find_banned_ignores_the_phrase_inside_other_words(text: str, lang: str) -> None:
    assert find_banned(text, lang) == []


@pytest.mark.parametrize(
    ("text", "lang", "expected"),
    [
        ("Iar.", "ro", "iar"),
        ("(din nou)", "ro", "din nou"),
        ("«risipă»", "ro", "risipă"),
        ("again!", "en", "again"),
        ("again, and", "en", "again"),
        ("iar", "ro", "iar"),
        ("_iar_", "ro", "iar"),
        ("**din nou**", "ro", "din nou"),
        ("*again*", "en", "again"),
    ],
)
def test_punctuation_and_markdown_are_word_boundaries(text: str, lang: str, expected: str) -> None:
    # `_` must be a boundary too: Claude writes _italics_, and plain `\b` treats `_` as a letter.
    assert phrases(text, lang) == [expected]


@pytest.mark.parametrize("text", ["iar2", "2iar"])
def test_digits_are_word_characters(text: str) -> None:
    assert find_banned(text, "ro") == []


@pytest.mark.parametrize(
    ("text", "hit"),
    [
        ("din  nou", True),
        ("din\nnou", True),
        ("din\tnou", True),
        ("din\u00a0nou", True),
        ("din-nou", True),
        ("din, nou", False),
        ("dinnou", False),
    ],
)
def test_the_words_of_a_phrase_are_separated_by_spaces_or_hyphens(text: str, hit: bool) -> None:
    assert phrases(text, "ro") == (["din nou"] if hit else [])


# The variant table of the A5 plan (Q2, approved): text → canonical phrase, or None = no hit.
VARIANTS = [
    # ro
    ("De ce-ai luat asta?", "ro", "de ce"),
    ("de-ce", "ro", "de ce"),
    ("ai cheltuit prea multe", "ro", "prea mult"),
    ("prea mulți bani", "ro", "prea mult"),
    ("prea multă vreme", "ro", "prea mult"),
    ("sunt prea mulțumit", "ro", None),
    ("ai risipit banii", "ro", "risipă"),
    ("risipești", "ro", "risipă"),
    ("risipitor", "ro", "risipă"),
    ("n-ar fi trebuit", "ro", "ar fi trebuit"),
    ("nu ar fi trebuit", "ro", "ar fi trebuit"),
    ("ar fi fost bine", "ro", None),
    ("iară", "ro", "iar"),
    ("iarăși", "ro", "iar"),
    ("din noua aplicație", "ro", None),
    ("din noul plan", "ro", None),
    ("din nouă lei", "ro", None),
    ("iresponsabilă", "ro", "iresponsabil"),
    ("iresponsabilitate", "ro", "iresponsabil"),
    ("nu îți permiți", "ro", "nu-ți permiți"),
    ("nu ți permiți", "ro", "nu-ți permiți"),
    ("nu-ți poți permite", "ro", "nu-ți permiți"),
    ("nu îți mai permiți", "ro", "nu-ți permiți"),
    ("îți permiți asta", "ro", None),
    ("îți poți permite", "ro", None),
    ("ai irosit banii", "ro", "irosi"),
    ("irosești", "ro", "irosi"),
    # en
    ("why'd you do it", "en", "why did you"),
    ("why didn't you", "en", "why did you"),
    ("why do you", "en", "why did you"),
    ("why don't you", "en", "why did you"),
    ("why would you", "en", "why did you"),
    ("why wouldn't you", "en", "why did you"),
    ("why not", "en", None),
    ("why did your budget change", "en", None),
    ("too many", "en", "too much"),
    ("wasted", "en", "waste"),
    ("wasting", "en", "waste"),
    ("wasteful", "en", "waste"),
    ("wastefully", "en", "waste"),
    ("wastes", "en", "waste"),
    ("waist", "en", None),
    ("should've", "en", "should have"),
    ("shouldn't have", "en", "should have"),
    ("should not have", "en", "should have"),
    ("gain", "en", None),
    ("irresponsibly", "en", "irresponsible"),
    ("irresponsibility", "en", "irresponsible"),
    ("cant afford", "en", "can't afford"),
    ("cannot afford", "en", "can't afford"),
    ("can not afford", "en", "can't afford"),
    ("couldn't afford", "en", "can't afford"),
    ("you can afford it", "en", None),
]


@pytest.mark.parametrize(("text", "lang", "expected"), VARIANTS)
def test_the_approved_variant_table(text: str, lang: str, expected: str | None) -> None:
    assert phrases(text, lang) == ([expected] if expected else [])


# ── invalid input ───────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_empty_or_blank_text_has_no_hit(text: str) -> None:
    assert find_banned(text) == []


@pytest.mark.parametrize("lang", ["fr", "RO", ""])
def test_an_unknown_language_is_refused(lang: str) -> None:
    with pytest.raises(ValueError, match="'ro', 'en' or None"):
        find_banned("iar", lang)


@pytest.mark.parametrize("text", [None, b"iar", ["iar"]])
def test_text_that_is_not_a_str_is_refused(text: Any) -> None:
    # A list would otherwise be folded element by element and "work".
    with pytest.raises(TypeError, match="must be a str"):
        find_banned(text, "ro")


def test_long_text_finds_the_one_hit_at_its_offset() -> None:
    prefix = "Bugetul tău e la zi. " * 10_000  # ~210 KB, clean
    found = find_banned(prefix + "iar", "ro")

    assert [(m.phrase, m.start, m.end) for m in found] == [("iar", len(prefix), len(prefix) + 3)]


# ── security ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ri\u00adsipă", "risipă"),  # soft hyphen
        ("ia\u200br", "iar"),  # zero-width space
        ("din\u2060 nou", "din nou"),  # word joiner
        ("de\u200d ce", "de ce"),  # zero-width joiner
        ("\ufeffiar", "iar"),  # BOM
    ],
)
def test_invisible_characters_do_not_hide_a_phrase(text: str, expected: str) -> None:
    # e.g. text shaped by an injected merchant name
    assert phrases(text, "ro") == [expected]


@pytest.mark.parametrize(
    "text",
    [
        "risi\u00a8pa",  # spacing diaeresis
        "i\u00b8ar",  # spacing cedilla
        "ia\u02d8r",  # spacing breve
        "risi\u02dcpa",  # spacing tilde
        "ri\u00afsipa",  # macron
        "ia\u02ddr",  # double acute
        "ia\u02dbr",  # ogonek
        "ia\u02dar",  # ring above
    ],
)
def test_spacing_diacritics_inside_a_word_do_not_hide_it(text: str) -> None:
    assert len(phrases(text, "ro")) == 1


@pytest.mark.parametrize(
    "text",
    ["ia\u3164r", "ia\uffa0r", "ia\u115fr", "ia\u1160r", "ia\u2800r"],  # invisible fillers
)
def test_invisible_fillers_do_not_hide_a_phrase(text: str) -> None:
    assert phrases(text, "ro") == ["iar"]


@pytest.mark.parametrize(
    "text",
    ["nu\u058ați permiți", "nu\u2e3ați permiți", "nu\u2e3bți permiți"],  # dash look-alikes
)
def test_dash_look_alikes_separate_words(text: str) -> None:
    assert phrases(text, "ro") == ["nu-ți permiți"]


@pytest.mark.parametrize(
    "text",
    ["can\u02b9t afford", "can\u2035t afford", "can\u02c8t afford", "can\ua78ct afford"],
)  # apostrophe look-alikes
def test_apostrophe_look_alikes_are_apostrophes(text: str) -> None:
    assert phrases(text, "en") == ["can't afford"]


@pytest.mark.parametrize(
    "text",
    [
        "de " * 33_000,
        "din" + " " * 100_000 + "x",
        "nu-" * 33_000,
        "why " * 25_000,
    ],
)
def test_adversarial_input_is_checked_in_linear_time(text: str) -> None:
    # No catastrophic backtracking. Measured ~0.1 s for these ~100 KB inputs; 1 s is the margin.
    start = time.perf_counter()
    find_banned(text)

    assert time.perf_counter() - start < 1.0


# ── language ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "lang", "expected"),
    [
        ("RISIPĂ", "ro", "risipă"),
        ("Risipa", "ro", "risipă"),
        ("DIN NOU", "ro", "din nou"),
        ("dIn NoU", "ro", "din nou"),
        ("Why Did You", "en", "why did you"),
        ("AGAIN", "en", "again"),
        ("\u0130AR", "ro", "iar"),  # Turkish dotted capital I
    ],
)
def test_case_does_not_matter(text: str, lang: str, expected: str) -> None:
    assert phrases(text, lang) == [expected]


@pytest.mark.parametrize(
    ("comma_below", "cedilla"),
    [
        ("nu-\u021bi permi\u021bi", "nu-\u0163i permi\u0163i"),
        ("iară\u0219i", "iară\u015fi"),
    ],
)
def test_cedilla_and_comma_below_diacritics_give_the_same_hits(
    comma_below: str, cedilla: str
) -> None:
    assert phrases(comma_below, "ro") == phrases(cedilla, "ro") != []


def test_decomposed_input_is_matched_and_the_span_keeps_the_combining_mark() -> None:
    text = unicodedata.normalize("NFD", "e risipă")
    [match] = find_banned(text, "ro")

    assert match.phrase == "risipă"
    assert match.text == text[2:]
    assert match.text.endswith("\u0306")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("can\u2019t afford", "can't afford"),
        ("can\u2018t afford", "can't afford"),
        ("can\u02bct afford", "can't afford"),
        ("can\u00b4t afford", "can't afford"),
        ("should\u2019ve", "should have"),
        ("why\u2019d you", "why did you"),
    ],
)
def test_curly_apostrophes_are_apostrophes(text: str, expected: str) -> None:
    assert phrases(text, "en") == [expected]


def test_the_language_selects_the_list() -> None:
    assert find_banned("again", "ro") == []
    assert find_banned("iar", "en") == []
    assert [(m.lang, m.phrase) for m in find_banned("iar, again")] == [
        ("ro", "iar"),
        ("en", "again"),
    ]


def test_the_language_enum_is_accepted_and_matches_carry_a_plain_str() -> None:
    # A6 / B13 pass F2's Language; BannedMatch.lang stays the plain "ro" (logs, JSON).
    [match] = find_banned("iar", Language.RO)

    assert match.lang == "ro"
    assert type(match.lang) is str


# ── invariants (property tests) ─────────────────────────────────────────────────────────


@settings(max_examples=500)
@given(text=ANY_TEXT, lang=st.sampled_from(["ro", "en", None]))
def test_find_banned_never_raises_and_every_span_is_the_match(text: str, lang: str | None) -> None:
    found = find_banned(text, lang)

    assert [(m.start, m.end) for m in found] == sorted((m.start, m.end) for m in found)
    for m in found:
        assert 0 <= m.start < m.end <= len(text)
        assert text[m.start : m.end] == m.text
        assert m.phrase in BANNED_PHRASES[m.lang]
        assert m.phrase in phrases(m.text, m.lang)


@given(prefix=ANY_TEXT, suffix=ANY_TEXT, entry=st.sampled_from(ALL_PHRASES))
def test_a_phrase_between_spaces_is_always_found(
    prefix: str, suffix: str, entry: tuple[str, str]
) -> None:
    lang, phrase = entry

    assert phrase in phrases(f"{prefix} {phrase} {suffix}", lang)


VOCABULARY = [
    "de", "ce", "cele", "iar", "Iar", "chiar", "iarnă", "iarăși", "ziar", "din", "nou", "noua",
    "nouă", "prea", "mult", "multă", "mulțumit", "risipă", "risipit", "irosit", "ar", "fi",
    "trebuit", "n-ar", "nu", "ți", "îți", "nu-ți", "permiți", "poți", "permite", "mai",
    "iresponsabil", "iresponsabilă", "știu", "șansa", "țintă", "again", "against", "why", "did",
    "you", "whyever", "too", "much", "many", "waste", "wasted", "wasteland", "should", "have",
    "should've", "can't", "afford", "cannot", "irresponsible",
]  # fmt: skip
SEPARATORS = [" ", "  ", "-", ", ", "\n", " \u2014 ", ". "]
SENTENCES = st.lists(
    st.tuples(st.sampled_from(VOCABULARY), st.sampled_from(SEPARATORS)), max_size=12
).map(lambda pairs: "".join(word + sep for word, sep in pairs))
CEDILLA = str.maketrans("\u0219\u021b\u0218\u021a", "\u015f\u0163\u015e\u0162")


@given(text=SENTENCES)
def test_hits_do_not_depend_on_diacritics_case_or_encoding(text: str) -> None:
    expected = phrases(text)

    assert phrases(strip_diacritics(text)) == expected
    assert phrases(text.upper()) == expected
    assert phrases(text.translate(CEDILLA)) == expected
    assert phrases(unicodedata.normalize("NFD", text)) == expected


# ── regression ──────────────────────────────────────────────────────────────────────────


def test_banned_phrases_are_the_arch_6_9_lists_plus_the_approved_addition() -> None:
    assert dict(BANNED_PHRASES) == {lang: ARCH_6_9[lang] + Q3_ADDITIONS[lang] for lang in LANGS}


def test_banned_phrases_cannot_be_changed_at_runtime() -> None:
    with pytest.raises(TypeError):
        BANNED_PHRASES["ro"] = ()  # type: ignore[index]


# ── review fixes (A5.1 review findings 1-10): every quoted bypass is a test ─────────────


@pytest.mark.parametrize(
    ("text", "lang", "expected"),
    [
        # 1. markdown inside a phrase
        ("din **nou**", "ro", "din nou"),
        ("**din** nou", "ro", "din nou"),
        ("de *ce*", "ro", "de ce"),
        ("too _much_", "en", "too much"),
        ("~~din~~ nou", "ro", "din nou"),
        ("`din` nou", "ro", "din nou"),
        # 2. English intensifiers (one bounded adverb slot)
        ("should never have", "en", "should have"),
        ("shouldn't really have", "en", "should have"),
        ("can't even afford", "en", "can't afford"),
        ("can't really afford", "en", "can't afford"),
        ("cannot actually afford", "en", "can't afford"),
        ("why on earth did you", "en", "why did you"),
        ("why ever did you", "en", "why did you"),
        # 3. apostrophe-less spellings
        ("whyd you", "en", "why did you"),
        ("shouldve", "en", "should have"),
        ("shouldntve", "en", "should have"),
        ("can`t afford", "en", "can't afford"),
        # 4. waste derivatives
        ("wastefulness", "en", "waste"),
        ("wastage", "en", "waste"),
        ("waster", "en", "waste"),
        # 5. «nu-ți permiți»: past tense and clitics
        ("nu ți-ai permis", "ro", "nu-ți permiți"),
        ("nu ți-ai putut permite", "ro", "nu-ți permiți"),
        ("nu ți-o poți permite", "ro", "nu-ți permiți"),
        ("nu ți-ai mai permis", "ro", "nu-ți permiți"),
        ("nu ți-o mai poți permite", "ro", "nu-ți permiți"),
        # 6. «prea mult»: genitive / dative plural
        ("prea multor", "ro", "prea mult"),
        ("prea multora", "ro", "prea mult"),
        # 7. emoji, symbols and formatting tags between the words
        ("din \U0001f501 nou", "ro", "din nou"),
        ("din \U0001f642 nou", "ro", "din nou"),
        ("din \U0001f44d\U0001f3fd nou", "ro", "din nou"),  # emoji + skin tone (Sk)
        ("<b>din</b> nou", "ro", "din nou"),
        ("<em>de</em> ce", "ro", "de ce"),
        ("din<br/>nou", "ro", "din nou"),
        # 8. a non-letter that folds to a letter or digit still ends the word
        ("again\u00b9", "en", "again"),
        ("din nou\u00b9", "ro", "din nou"),
        ("again\u2122", "en", "again"),
        ("risipă\u00ae", "ro", "risipă"),
        # 9. Cyrillic / Greek look-alikes (style.py only; the shared fold keeps real Cyrillic)
        ("i\u0430r", "ro", "iar"),  # Cyrillic a
        ("\u0430gain", "en", "again"),  # Cyrillic a
        ("r\u0456sipă", "ro", "risipă"),  # Cyrillic i
        ("d\u03b9n n\u03bfu", "ro", "din nou"),  # Greek iota, omicron
        ("AGAI\u039d", "en", "again"),  # Greek capital Nu
        ("\u03a4\u039f\u039f \u039cUCH", "en", "too much"),  # Greek Tau, Omicron, Mu
        ("\u0391G\u0391IN", "en", "again"),  # Greek capital Alpha
        # 10. soft hyphen used as a space; hyphenation across a line break
        ("de\u00adce", "ro", "de ce"),
        ("too\u00admuch", "en", "too much"),
        ("ri-\nsipă", "ro", "risipă"),
        ("ag-\nain", "en", "again"),
        ("ag-\r\nain", "en", "again"),
        ("ri-\n    sipă", "ro", "risipă"),
    ],
)
def test_review_bypasses_are_found(text: str, lang: str, expected: str) -> None:
    assert phrases(text, lang) == [expected]


@pytest.mark.parametrize(
    "text",
    [
        "din, nou",  # sentence punctuation is not a separator
        "din. nou",
        "wasteland",
        "wastelands",
        "waist",
        "prea mulțumit",
        "planul nu ți-a permis",  # "the plan didn't allow you": not the phrase
        "you should never",
        "you can't even",
        "<span>chiar</span>",
        "iar2",
        "\u043f\u0440\u0438\u0432\u0435\u0442",  # real Cyrillic: privet
        "\u03b3\u03b5\u03b9\u03b1 \u03c3\u03bf\u03c5",  # real Greek: geia sou
    ],
)
def test_review_fixes_keep_the_no_hit_cases_clean(text: str) -> None:
    assert find_banned(text) == []


def test_a_tag_shaped_banned_word_is_not_hidden() -> None:
    # Only known formatting tags are separators; the app shows plain text, so "<iar>" reads "iar".
    assert phrases("<iar>", "ro") == ["iar"]


def test_a_real_hyphen_at_a_line_end_still_separates_words() -> None:
    # The joined reading must not lose the as-written one (and the reverse for a soft hyphen).
    assert phrases("nu-\nți permiți", "ro") == ["nu-ți permiți"]
    assert phrases("ri\u00adsipă", "ro") == ["risipă"]


def test_a_joined_match_spans_the_hyphenated_original() -> None:
    [match] = find_banned("Ai ri-\nsipit banii", "ro")

    assert (match.phrase, match.start, match.end, match.text) == ("risipă", 3, 12, "ri-\nsipit")


def test_the_look_alike_table_maps_cyrillic_and_greek_letters_to_ascii_letters() -> None:
    from app.agent.style import _CONFUSABLES

    assert len(_CONFUSABLES) >= 50
    for source, target in _CONFUSABLES.items():
        assert unicodedata.name(source).split()[0] in {"CYRILLIC", "GREEK"}
        assert len(target) == 1
        assert target.isascii()
        assert target.isalpha()


@pytest.mark.parametrize(
    "text",
    [
        "<b>" * 30_000,
        "\u00ad" * 100_000,
        "a-\n" * 33_000,
        "din " + "\U0001f642" * 50_000 + " x",
        "should never " * 8_000,
        "nu ți-o mai " * 8_000,
    ],
)
def test_the_review_fixes_keep_matching_linear(text: str) -> None:
    start = time.perf_counter()
    find_banned(text)

    assert time.perf_counter() - start < 1.0


def test_a_phrase_found_by_both_readings_is_reported_once() -> None:
    # The soft hyphen makes the joined reading run too; both readings see "iar".
    assert phrases("de\u00adce iar", "ro") == ["de ce", "iar"]
