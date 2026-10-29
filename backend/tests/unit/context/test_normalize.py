"""C2: merchant normalisation (work-breakdown C2; H-7 alias rules)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.context.normalize import (
    MCC_CATEGORIES,
    NOISE_TOKENS,
    NormalizedMerchant,
    load_merchants,
    normalize,
    tokens,
)
from app.domain.enums import Category


@pytest.mark.parametrize(
    ("raw", "merchant_id", "name", "category"),
    [
        ("MEGA IMAGE 0451 BUCURESTI", "mega_image", "Mega Image", Category.GROCERIES),
        ("SHOP&GO 123", "shop_and_go", "Shop&Go", Category.GROCERIES),
        ("PAYU*EMAG.RO", "emag", "eMAG", Category.ELECTRONICS),
        ("GLOVO*ORDER 8812", "glovo", "Glovo", Category.FOOD_DELIVERY),
        ("Cărturești Verona", "carturesti", "Cărturești", Category.BOOKS),
        ("Carturesti Verona", "carturesti", "Cărturești", Category.BOOKS),
        ("mega image 0451 bucuresti", "mega_image", "Mega Image", Category.GROCERIES),
        ("POS SC MEGA IMAGE SRL", "mega_image", "Mega Image", Category.GROCERIES),
        ("MEGAIMAGE0451", "mega_image", "Mega Image", Category.GROCERIES),
        ("CTP IASI 0012", "ctp_iasi", "CTP Iași", Category.TRANSPORT),  # a city in the alias
    ],
)
def test_work_breakdown_cases(raw: str, merchant_id: str, name: str, category: Category) -> None:
    result = normalize(raw, None, None)
    assert (result.merchant_id, result.name, result.category) == (merchant_id, name, category)


def test_emag_is_multi_category() -> None:
    assert normalize("PAYU*EMAG.RO", None, None).multi_category is True
    assert normalize("MEGA IMAGE 0451", None, None).multi_category is False


@pytest.mark.parametrize(
    ("raw", "merchant_id"),
    [
        ("BOLT.EU/O/2604151230", "bolt_food"),
        ("BOLT.EU/R/2604151230", "bolt"),
        ("BOLT.EU", "bolt"),
        ("BOLT FOOD", "bolt_food"),
        ("DIGI SPORT 4", "digi_sport"),
        ("DIGI RCS&RDS", "digi"),
        ("OMV PETROM 123", "petrom"),
        ("OMV 0042", "omv"),
        ("TAZZ BY EMAG", "tazz"),
        ("PAYU*TAZZ BY EMAG", "tazz"),
    ],
)
def test_pinned_nested_pairs_take_the_longest_alias(raw: str, merchant_id: str) -> None:
    assert normalize(raw, None, None).merchant_id == merchant_id


def test_a_tie_between_two_merchants_is_ambiguous() -> None:
    result = normalize("UBER BOLT 123", "4111", None)  # two 4-letter aliases
    assert result.merchant_id is None
    assert result.category is Category.TRANSPORT  # the MCC still decides
    assert normalize("EMAG ALTEX", None, None).merchant_id == "altex"  # longer, not a tie


def test_unknown_merchant_falls_back_to_the_mcc() -> None:
    result = normalize("POS LA MAMA 0042 BUCURESTI", "5411", None)
    assert result == NormalizedMerchant(None, "La Mama", Category.GROCERIES)


@pytest.mark.parametrize(("mcc", "category"), sorted(MCC_CATEGORIES.items()))
def test_mcc_table(mcc: str, category: Category) -> None:
    assert normalize("NECUNOSCUT 1", mcc, None).category is category


@pytest.mark.parametrize("mcc", [None, "9999", "", "54111"])
def test_unknown_with_no_known_mcc_is_other(mcc: str | None) -> None:
    result = normalize("XYZ 123", mcc, None)
    assert (result.merchant_id, result.category) == (None, Category.OTHER)


def test_empty_string_is_other() -> None:
    assert normalize("", None, None) == NormalizedMerchant(None, "", Category.OTHER)


def test_only_noise_keeps_the_raw_text_as_name() -> None:
    assert normalize("  POS   1234 ", None, None).name == "POS 1234"


def test_the_script_category_always_wins() -> None:
    known = normalize("MEGA IMAGE 0451", "5411", Category.HOUSEHOLD_GOODS)
    assert (known.merchant_id, known.category) == ("mega_image", Category.HOUSEHOLD_GOODS)
    unknown = normalize("XYZ", "5411", Category.GIFTS)
    assert (unknown.merchant_id, unknown.category) == (None, Category.GIFTS)


def test_every_alias_and_canonical_name_resolves_to_its_merchant() -> None:
    for merchant in load_merchants():
        for text in (*merchant.aliases, merchant.canonical_name, merchant.canonical_name.upper()):
            assert normalize(text, None, None).merchant_id == merchant.id, text


def test_idempotent_on_canonical_names() -> None:
    for merchant in load_merchants():
        once = normalize(merchant.canonical_name, None, None)
        assert normalize(once.name, None, None) == once


def test_no_alias_is_only_noise() -> None:
    for merchant in load_merchants():
        for alias in merchant.aliases:
            assert set(tokens(alias)) - NOISE_TOKENS, alias


# Any code point (surrogates included), built from integers: st.text() would build Hypothesis's
# Unicode charmap, a big heap that slows the timing test of test_models_transactions under GC.
ANY_TEXT = st.lists(st.integers(0, 0x10FFFF).map(chr), max_size=300).map("".join)


@given(ANY_TEXT, st.one_of(st.none(), ANY_TEXT))
def test_never_raises_on_arbitrary_unicode(raw: str, mcc: str | None) -> None:
    result = normalize(raw, mcc, None)
    assert isinstance(result.category, Category)
    assert result.merchant_id is None or result.name
