"""C1.4: RO / EN labels for categories, purposes and beneficiaries (arch 9.1, 9.3, D33).

The app never maps enum values to text itself (arch 9.1): `category_label` and `purpose_label`
come from `label()`. Read by B6a, B13, A4, A5 and E9.
"""

import unicodedata
from enum import StrEnum

import pytest

from app.agent.style import find_banned
from app.domain.enums import AnnotationSource, Beneficiary, Category, Decision, Language, Purpose
from app.i18n.labels import label

ENUMS: list[type[Category] | type[Purpose] | type[Beneficiary]] = [Category, Purpose, Beneficiary]
MEMBERS = [member for enum in ENUMS for member in enum]
CEDILLAS = set("\u015f\u0163\u015e\u0162")
RO_LETTERS = set("ăâîșțĂÂÎȘȚ")

# The reviewed table (C1 plan §C1.4, approved in D48). (value, ro, en) per enum.
GOLDEN: dict[type[StrEnum], dict[str, tuple[str, str]]] = {
    Category: {
        "groceries": ("Cumpărături", "Groceries"),
        "restaurants": ("Restaurante", "Restaurants"),
        "food_delivery": ("Livrare de mâncare", "Food delivery"),
        "transport": ("Transport", "Transport"),
        "fuel": ("Carburant", "Fuel"),
        "electronics": ("Electronice", "Electronics"),
        "clothing": ("Haine", "Clothing"),
        "sport": ("Sport", "Sport"),
        "health_pharmacy": ("Sănătate și farmacie", "Health & pharmacy"),
        "kids": ("Copii", "Kids"),
        "education": ("Educație", "Education"),
        "books": ("Cărți", "Books"),
        "entertainment": ("Divertisment", "Entertainment"),
        "subscriptions": ("Abonamente", "Subscriptions"),
        "travel": ("Călătorii", "Travel"),
        "housing_rent": ("Chirie și locuință", "Rent & housing"),
        "utilities": ("Utilități", "Utilities"),
        "telecom": ("Telefon și internet", "Phone & internet"),
        "gifts": ("Cadouri", "Gifts"),
        "pets": ("Animale de companie", "Pets"),
        "household_goods": ("Casă și gospodărie", "Household goods"),
        "personal_care": ("Îngrijire personală", "Personal care"),
        "transfers": ("Transferuri", "Transfers"),
        "income": ("Venituri", "Income"),
        "savings": ("Economii", "Savings"),
        "other": ("Altele", "Other"),
    },
    Purpose: {
        "essential_living": ("Nevoi de bază", "Essentials"),
        "household_care": ("Pentru cei dragi", "For your loved ones"),
        "work_tool": ("Echipament de lucru", "Work equipment"),
        "self_investment": ("Investiție în tine", "Investing in yourself"),
        "identity_joy": ("Pasiuni", "Passions"),
        "social_connection": ("Socializare", "Social life"),
        "planned_event": ("Plănuit", "Planned"),
        "on_behalf_of_others": ("Pentru alții", "For others"),
        "unplanned_discretionary": ("Neplanificat", "Unplanned"),
        "emergency": ("Urgență", "Emergency"),
        "unknown": ("Neprecizat", "Not specified"),
    },
    Beneficiary: {
        "self": ("Pentru tine", "For you"),
        "household": ("Pentru cei de acasă", "For your household"),
        "shared": ("Împărțit", "Shared"),
        "others": ("Pentru alții", "For others"),
        "employer": ("Pentru angajator", "For your employer"),
    },
}


# ── happy path ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "ro", "en"),
    [
        (Category.GROCERIES, "Cumpărături", "Groceries"),  # arch 9.3 Transaction example
        (Purpose.ON_BEHALF_OF_OTHERS, "Pentru alții", "For others"),  # arch 9.3
        (Purpose.WORK_TOOL, "Echipament de lucru", "Work equipment"),  # arch 16.2 Scene B
    ],
)
def test_the_labels_the_arch_doc_shows(value: Category | Purpose, ro: str, en: str) -> None:
    assert label(value, "ro") == ro
    assert label(value, "en") == en


def test_every_label_matches_the_reviewed_table() -> None:
    actual = {
        enum: {member.value: (label(member, "ro"), label(member, "en")) for member in enum}
        for enum in ENUMS
    }

    assert actual == GOLDEN


# ── boundaries: complete, no stale rows ─────────────────────────────────────────────────


@pytest.mark.parametrize("member", MEMBERS, ids=lambda m: f"{type(m).__name__}.{m.value}")
def test_every_value_has_a_romanian_and_an_english_label(
    member: Category | Purpose | Beneficiary,
) -> None:
    # Spec: "every enum value has an RO and an EN label (no missing key)".
    assert label(member, "ro").strip()
    assert label(member, "en").strip()


def test_the_golden_covers_exactly_the_enums() -> None:
    # A value added to (or removed from) F2's enums shows up here, not in production.
    for enum in ENUMS:
        assert sorted(GOLDEN[enum]) == sorted(member.value for member in enum)


# ── invalid input ───────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("lang", ["fr", "", "RO", "ro ", "en-GB", None])
def test_label_rejects_an_unknown_language(lang: object) -> None:
    with pytest.raises(ValueError, match="language"):
        label(Category.GROCERIES, lang)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    ["groceries", 1, None, Decision.ASK, AnnotationSource.AUTO, Language.RO],
    ids=["plain-str", "int", "none", "decision", "annotation-source", "language"],
)
def test_label_rejects_anything_but_the_three_enums(value: object) -> None:
    # A plain DB string must be converted first (Category(value)): a silent wrong label is worse.
    # Decision.AUTO == AnnotationSource.AUTO == "auto": dispatch is by enum type, never by value.
    with pytest.raises(TypeError, match="Category, Purpose or Beneficiary"):
        label(value, "ro")  # type: ignore[arg-type]


# ── language ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("member", MEMBERS, ids=lambda m: f"{type(m).__name__}.{m.value}")
def test_language_members_work_like_their_values(member: Category | Purpose | Beneficiary) -> None:
    assert label(member, Language.RO) == label(member, "ro")
    assert label(member, Language.EN) == label(member, "en")


@pytest.mark.parametrize("lang", ["ro", "en"])
def test_labels_are_clean_short_capitalised_text(lang: str) -> None:
    for member in MEMBERS:
        text = label(member, lang)
        assert unicodedata.normalize("NFC", text) == text, text
        assert not CEDILLAS & set(text), text  # comma-below s/t only
        assert text == " ".join(text.split()), text
        assert len(text) <= 30, text  # fits a feed chip
        assert text[0].isupper(), text
        if lang == "en":
            assert not RO_LETTERS & set(text), text  # no Romanian copied into English


# ── personalisation: nothing labels a purchase good or bad (D33) ────────────────────────


@pytest.mark.parametrize("lang", ["ro", "en"])
def test_no_label_contains_a_banned_phrase(lang: str) -> None:
    hits = {label(m, lang): find_banned(label(m, lang), lang) for m in MEMBERS}

    assert {text: found for text, found in hits.items() if found} == {}


# ── invariants ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("lang", ["ro", "en"])
@pytest.mark.parametrize("enum", ENUMS, ids=lambda e: e.__name__)
def test_labels_are_unique_within_each_enum(
    enum: type[Category] | type[Purpose] | type[Beneficiary], lang: str
) -> None:
    # Two categories never read the same in the feed.
    texts = [label(member, lang) for member in enum]

    assert len(texts) == len(set(texts))
