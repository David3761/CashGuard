"""C1.2: data/merchants.json, the merchant catalogue (work-breakdown C1, arch 4.4, D32, D47).

Read by C2 (normalisation), bomboe's B2/B12 (table + seed), danutu's E12 (merchant_raw) and D2.
C2's longest-alias match relies on the alias rules tested here.
"""

import copy
import re
from collections import Counter
from decimal import Decimal
from functools import cache
from typing import Any

import pytest

from app.domain.enums import Category
from app.i18n.text import fold
from tests.unit.datafiles import load_data, load_schema, schema_errors

# The 40 merchants named in work-breakdown C1 (the spec's list).
NAMED_IN_SPEC = [
    "Mega Image", "Shop&Go", "Lidl", "Kaufland", "Carrefour", "Profi", "Penny", "Auchan", "eMAG",
    "Altex", "Flanco", "Decathlon", "Glovo", "Tazz", "Bolt", "Uber", "Petrom", "OMV", "MOL",
    "Rompetrol", "Dr.Max", "Catena", "Sensiblu", "Help Net", "Libris", "Cărturești", "Diverta",
    "Steam", "Netflix", "Spotify", "Digi", "Orange", "Vodafone", "Enel", "Engie", "E.ON",
    "CFR Călători", "Wizz Air", "Ryanair", "Booking.com",
]  # fmt: skip
# 53 approved in D48 (+ 3 invented restaurants, 3 sports streaming, Bolt Food, 6 for empty
# categories) + 9 added after the C1.2 review (DAZN, Wolt, a gym, 2 ticketing, a cafe, 3 transit).
TOTAL = 62
MULTI_CATEGORY = {"eMAG", "Altex", "Carrefour", "Auchan", "Flanco", "Diverta"}
# One merchant's strict key inside another's: C2's longest match must test each pair.
NESTED = {
    ("bolt", "boltfood"),
    ("bolt", "bolteuo"),
    ("bolteu", "bolteuo"),  # BOLT.EU/O/… is Bolt Food, BOLT.EU/R/… a ride
    ("digi", "digisport"),
    ("emag", "tazzbyemag"),  # TAZZ BY EMAG is food delivery, not eMAG (D32 would ask)
    ("omv", "omvpetrom"),
}
# The work-breakdown C2 MCC fallback table (replaced by importing C2's table when C2 lands).
MCC_FALLBACK = {
    "5411": {"groceries"}, "5812": {"restaurants"}, "5814": {"restaurants"}, "5541": {"fuel"},
    "5912": {"health_pharmacy"}, "4111": {"transport"}, "4511": {"travel"},
    "5732": {"electronics"}, "5941": {"sport"}, "5942": {"books"},
    "5815": {"subscriptions", "entertainment"}, "5816": {"subscriptions", "entertainment"},
    "5817": {"subscriptions", "entertainment"}, "4814": {"telecom"}, "4900": {"utilities"},
}  # fmt: skip
FOOD_DELIVERY_PLATFORMS = {
    "glovo",
    "tazz",
    "bolt_food",
    "wolt",
}  # MCC 5814 (fast food), category delivery
# Categories no merchant is expected for: paid by transfer (rent, fees), or not spending at all.
NO_MERCHANT_NEEDED = {"housing_rent", "education", "other", "transfers", "income", "savings"}
# Alias rule 1: an alias is a spelling, not a whole descriptor (C2 strips these).
PAYMENT_TOKENS = {"pos", "payu", "paypal", "sumup", "ecom", "order", "srl", "sa", "sc"}
CITY_TOKENS = {"bucuresti", "bucharest", "cluj", "napoca", "iasi", "sector"}  # persona cities

# Review R2: the whole catalogue, reviewed line by line against the plan (and the review's
# additions). id -> (canonical_name, category, mcc, typical_basket, multi_category, aliases).
GOLDEN = {
    "mega_image": ("Mega Image", "groceries", "5411", "85.00", False, ("mega image", "megaimage")),
    "shop_and_go": ("Shop&Go", "groceries", "5411", "65.00", False, ("shop&go", "shop and go")),
    "lidl": ("Lidl", "groceries", "5411", "110.00", False, ("lidl",)),
    "kaufland": ("Kaufland", "groceries", "5411", "150.00", False, ("kaufland",)),
    "carrefour": ("Carrefour", "groceries", "5411", "140.00", True, ("carrefour",)),
    "profi": ("Profi", "groceries", "5411", "50.00", False, ("profi",)),
    "penny": ("Penny", "groceries", "5411", "80.00", False, ("penny", "penny market")),
    "auchan": ("Auchan", "groceries", "5411", "150.00", True, ("auchan",)),
    "emag": ("eMAG", "electronics", "5732", "250.00", True, ("emag", "emag.ro")),
    "altex": ("Altex", "electronics", "5732", "350.00", True, ("altex", "altex.ro")),
    "flanco": ("Flanco", "electronics", "5732", "350.00", True, ("flanco", "flanco.ro")),
    "decathlon": ("Decathlon", "sport", "5941", "150.00", False, ("decathlon", "decathlon.ro")),
    "glovo": ("Glovo", "food_delivery", "5814", "55.00", False, ("glovo", "glovoapp")),
    "tazz": ("Tazz", "food_delivery", "5814", "55.00", False, ("tazz", "tazz.ro", "tazz by emag")),
    "bolt_food": ("Bolt Food", "food_delivery", "5814", "55.00", False, ("bolt food", "bolt.eu/o")),
    "bolt": ("Bolt", "transport", "4121", "28.00", False, ("bolt", "bolt.eu", "bolt.eu/r")),
    "uber": ("Uber", "transport", "4121", "30.00", False, ("uber",)),
    "cfr_calatori": (
        "CFR Călători",
        "transport",
        "4112",
        "80.00",
        False,
        ("cfr călători", "cfrcalatori.ro"),
    ),
    "petrom": ("Petrom", "fuel", "5541", "220.00", False, ("petrom", "omv petrom")),
    "omv": ("OMV", "fuel", "5541", "220.00", False, ("omv",)),
    "mol": ("MOL", "fuel", "5541", "220.00", False, ("mol",)),
    "rompetrol": ("Rompetrol", "fuel", "5541", "220.00", False, ("rompetrol",)),
    "dr_max": ("Dr.Max", "health_pharmacy", "5912", "45.00", False, ("dr.max", "dr max", "drmax")),
    "catena": ("Catena", "health_pharmacy", "5912", "45.00", False, ("catena", "farmacia catena")),
    "sensiblu": ("Sensiblu", "health_pharmacy", "5912", "45.00", False, ("sensiblu",)),
    "help_net": ("Help Net", "health_pharmacy", "5912", "45.00", False, ("help net", "helpnet")),
    "libris": ("Libris", "books", "5942", "60.00", False, ("libris", "libris.ro")),
    "carturesti": ("Cărturești", "books", "5942", "70.00", False, ("cărturești", "carturesti.ro")),
    "diverta": ("Diverta", "books", "5942", "60.00", True, ("diverta",)),
    "steam": (
        "Steam",
        "entertainment",
        "5816",
        "60.00",
        False,
        ("steam", "steampowered", "steamgames.com"),
    ),
    "netflix": ("Netflix", "subscriptions", "4899", "50.00", False, ("netflix", "netflix.com")),
    "spotify": ("Spotify", "subscriptions", "5815", "25.00", False, ("spotify",)),
    "digi_sport": ("Digi Sport", "subscriptions", "4899", "30.00", False, ("digi sport",)),
    "prima_sport": ("Prima Sport", "subscriptions", "4899", "25.00", False, ("prima sport",)),
    "voyo": ("Voyo", "subscriptions", "4899", "30.00", False, ("voyo",)),
    "digi": ("Digi", "telecom", "4814", "50.00", False, ("digi", "rcs&rds")),
    "orange": ("Orange", "telecom", "4814", "60.00", False, ("orange",)),
    "vodafone": ("Vodafone", "telecom", "4814", "60.00", False, ("vodafone",)),
    "ppc_energie": (
        "PPC Energie",
        "utilities",
        "4900",
        "150.00",
        False,
        ("ppc energie", "enel energie", "enel"),
    ),
    "engie": ("Engie", "utilities", "4900", "200.00", False, ("engie",)),
    "eon": ("E.ON", "utilities", "4900", "180.00", False, ("e.on", "eon")),
    "wizz_air": (
        "Wizz Air",
        "travel",
        "4511",
        "450.00",
        False,
        ("wizz air", "wizzair", "wizzair.com"),
    ),
    "ryanair": ("Ryanair", "travel", "4511", "400.00", False, ("ryanair", "ryanair.com")),
    "booking": ("Booking.com", "travel", "4722", "800.00", False, ("booking.com", "booking")),
    "bistro_cotidian": (
        "Bistro Cotidian",
        "restaurants",
        "5812",
        "70.00",
        False,
        ("bistro cotidian",),
    ),
    "ciorbaria_bunicii": (
        "Ciorbăria Bunicii",
        "restaurants",
        "5812",
        "55.00",
        False,
        ("ciorbăria bunicii",),
    ),
    "pizzeria_nonna_vera": (
        "Pizzeria Nonna Vera",
        "restaurants",
        "5812",
        "65.00",
        False,
        ("pizzeria nonna vera", "nonna vera"),
    ),
    "zara": ("Zara", "clothing", "5651", "200.00", False, ("zara",)),
    "noriel": ("Noriel", "kids", "5945", "120.00", False, ("noriel",)),
    "animax": ("Animax", "pets", "5995", "90.00", False, ("animax",)),
    "dedeman": ("Dedeman", "household_goods", "5200", "160.00", False, ("dedeman",)),
    "dm": (
        "dm drogerie markt",
        "personal_care",
        "5977",
        "60.00",
        False,
        ("dm drogerie markt", "dm drogerie"),
    ),
    "floraria_bujor": ("Florăria Bujor", "gifts", "5992", "100.00", False, ("florăria bujor",)),
    "dazn": ("DAZN", "subscriptions", "4899", "60.00", False, ("dazn",)),
    "wolt": ("Wolt", "food_delivery", "5814", "60.00", False, ("wolt", "wolt.com")),
    "world_class": ("World Class", "sport", "7997", "180.00", False, ("world class", "worldclass")),
    "iabilet": ("iaBilet", "entertainment", "7922", "150.00", False, ("iabilet", "iabilet.ro")),
    "eventim": ("Eventim", "entertainment", "7922", "200.00", False, ("eventim", "eventim.ro")),
    "5_to_go": ("5 to go", "restaurants", "5814", "12.00", False, ("5 to go",)),
    "stb": ("STB", "transport", "4111", "10.00", False, ("stb",)),
    "metrorex": ("Metrorex", "transport", "4111", "10.00", False, ("metrorex",)),
    "ctp_iasi": ("CTP Iași", "transport", "4111", "5.00", False, ("ctp iași",)),
}

VALID_ENTRY: dict[str, Any] = {
    "id": "mega_image",
    "canonical_name": "Mega Image",
    "aliases": ["mega image", "megaimage"],
    "category": "groceries",
    "mcc": "5411",
    "typical_basket": Decimal("85.00"),
    "multi_category": False,
}


@cache
def _merchants() -> tuple[dict[str, Any], ...]:
    return tuple(load_data("merchants")["merchants"])


def _by_id() -> dict[str, dict[str, Any]]:
    return {merchant["id"]: merchant for merchant in _merchants()}


def _strict(alias: str) -> str:
    """The strictest key C2 could use: folded, letters and digits only."""
    return re.sub(r"[^0-9a-z]", "", fold(alias))


def _alias_problems(merchants: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> list[str]:
    """Alias rules 1 to 5 (C1 plan + review R7); empty = they all hold."""
    problems = []
    owners: dict[str, str] = {}
    for merchant in merchants:
        folded = [fold(alias) for alias in merchant["aliases"]]
        if fold(merchant["canonical_name"]) not in folded:
            problems.append(f"{merchant['id']}: the canonical name is not an alias")
        if len(set(folded)) != len(folded):
            problems.append(f"{merchant['id']}: aliases repeat after folding")
        canonical_tokens = set(re.split(r"[^0-9a-z]+", fold(merchant["canonical_name"])))
        for alias in merchant["aliases"]:
            tokens = set(re.split(r"[^0-9a-z]+", fold(alias)))
            if alias != alias.lower():
                problems.append(f"{merchant['id']}: {alias!r} is not lower case")
            if re.search(r"[0-9]{3,}", alias):
                problems.append(f"{merchant['id']}: {alias!r} has a store or order number")
            if "*" in alias or tokens & PAYMENT_TOKENS:
                problems.append(f"{merchant['id']}: {alias!r} has a payment prefix")
            if (tokens & CITY_TOKENS) - canonical_tokens:  # a city in the brand (CTP Iași) is ok
                problems.append(f"{merchant['id']}: {alias!r} has a city")
            if alias != " ".join(alias.split()):
                problems.append(f"{merchant['id']}: {alias!r} has stray spaces")
            if len(fold(alias)) < 3:
                problems.append(f"{merchant['id']}: {alias!r} is shorter than 3 characters")
            owner = owners.setdefault(_strict(alias), merchant["id"])
            if owner != merchant["id"]:
                problems.append(f"{alias!r} of {merchant['id']} collides with {owner}")
    return problems


def _nested_pairs(merchants: tuple[dict[str, Any], ...]) -> set[tuple[str, str]]:
    keys = [
        (merchant["id"], _strict(alias)) for merchant in merchants for alias in merchant["aliases"]
    ]
    return {(a, b) for id_a, a in keys for id_b, b in keys if id_a != id_b and a in b}


# ── happy path ──────────────────────────────────────────────────────────────────────────


def test_merchants_file_validates_against_its_schema() -> None:
    assert schema_errors("merchants", load_data("merchants")) == []


def test_merchants_schema_is_a_draft_2020_12_schema() -> None:
    schema = load_schema("merchants")  # also runs check_schema

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_schema_category_enum_is_exactly_f2s_category() -> None:
    schema = load_schema("merchants")
    enum = schema["$defs"]["merchant"]["properties"]["category"]["enum"]

    assert sorted(enum) == sorted(category.value for category in Category)
    assert len(enum) == len(set(enum))


def test_every_merchant_category_is_a_valid_category() -> None:
    for merchant in _merchants():
        assert Category(merchant["category"]).value == merchant["category"]


def test_the_merchants_named_in_the_spec_are_all_present() -> None:
    # Reachable by their name: Enel is now PPC Energie (review R5) and keeps "enel" as an alias.
    index = {fold(alias) for merchant in _merchants() for alias in merchant["aliases"]}

    assert sorted(name for name in NAMED_IN_SPEC if fold(name) not in index) == []
    assert len(_merchants()) == TOTAL


def test_the_catalogue_matches_the_reviewed_golden_snapshot() -> None:
    actual = {
        m["id"]: (
            m["canonical_name"],
            m["category"],
            m["mcc"],
            str(m["typical_basket"]),
            m["multi_category"],
            tuple(m["aliases"]),
        )
        for m in _merchants()
    }

    assert actual == GOLDEN


# ── boundaries & invalid input (the schema catches each broken entry) ──────────────────


def _errors_for(entry: dict[str, Any]) -> list[str]:
    return schema_errors("merchants", {"merchants": [entry]})


def test_the_valid_sample_entry_passes() -> None:
    assert _errors_for(VALID_ENTRY) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("typical_basket", Decimal("0.01")),
        ("mcc", "0742"),  # leading zero kept: an MCC is a code, not a number
        ("aliases", ["abc"]),
        ("id", "a"),
    ],
)
def test_boundary_values_that_are_still_valid(field: str, value: Any) -> None:
    assert _errors_for({**VALID_ENTRY, field: value}) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("typical_basket", Decimal("0")),
        ("typical_basket", Decimal("-1")),
        ("typical_basket", "85"),
        ("typical_basket", True),
        ("mcc", "541"),
        ("mcc", "54111"),
        ("mcc", "54a1"),
        ("mcc", 5411),
        ("aliases", []),
        ("aliases", ["mega image", "mega image"]),
        ("aliases", ["ab"]),
        ("aliases", "mega image"),
        ("category", "food"),
        ("category", "Groceries"),
        ("multi_category", "yes"),
        ("id", "Mega Image"),
        ("id", "mega-image"),
        ("id", ""),
        ("canonical_name", ""),
    ],
)
def test_the_schema_rejects_a_bad_field(field: str, value: Any) -> None:
    errors = _errors_for({**VALID_ENTRY, field: value})

    assert errors
    assert all(f"merchants/0/{field}" in error for error in errors), errors


@pytest.mark.parametrize("field", sorted(VALID_ENTRY))
def test_the_schema_requires_every_field(field: str) -> None:
    entry = {key: value for key, value in VALID_ENTRY.items() if key != field}

    assert any(f"'{field}' is a required property" in error for error in _errors_for(entry))


def test_the_schema_rejects_unknown_fields_and_a_bad_envelope() -> None:
    assert _errors_for({**VALID_ENTRY, "logo": "mega.png"})
    assert schema_errors("merchants", {"merchants": [VALID_ENTRY], "version": 2})
    assert schema_errors("merchants", {"merchants": []})
    assert schema_errors("merchants", {"merchants": VALID_ENTRY})
    assert schema_errors("merchants", {})


# ── idempotency (stable keys for the seed) & money ─────────────────────────────────────


def test_ids_are_unique() -> None:
    ids = Counter(merchant["id"] for merchant in _merchants())

    assert [merchant_id for merchant_id, n in ids.items() if n > 1] == []


def test_canonical_names_are_unique_after_folding() -> None:
    names = Counter(fold(merchant["canonical_name"]) for merchant in _merchants())

    assert [name for name, n in names.items() if n > 1] == []


def test_typical_baskets_are_exact_decimals_with_at_most_two_decimals() -> None:
    for merchant in _merchants():
        basket = merchant["typical_basket"]
        assert isinstance(basket, Decimal), merchant["id"]
        assert basket == basket.quantize(Decimal("0.01")), merchant["id"]


# ── language ────────────────────────────────────────────────────────────────────────────


def test_canonical_names_keep_their_romanian_diacritics() -> None:
    by_id = _by_id()

    assert by_id["carturesti"]["canonical_name"] == "Cărturești"
    assert by_id["cfr_calatori"]["canonical_name"] == "CFR Călători"
    assert by_id["ciorbaria_bunicii"]["canonical_name"] == "Ciorbăria Bunicii"
    assert by_id["floraria_bujor"]["canonical_name"] == "Florăria Bujor"


@pytest.mark.parametrize(
    ("spelling", "merchant_id"),
    [
        ("Cărturești", "carturesti"),
        ("CARTURESTI", "carturesti"),
        ("CFR CALATORI", "cfr_calatori"),
        ("Ciorbaria Bunicii", "ciorbaria_bunicii"),
        ("FLORARIA BUJOR", "floraria_bujor"),
    ],
)
def test_spellings_with_and_without_diacritics_reach_the_same_merchant(
    spelling: str, merchant_id: str
) -> None:
    index = {fold(alias): m["id"] for m in _merchants() for alias in m["aliases"]}

    assert index[fold(spelling)] == merchant_id


# ── personalisation ─────────────────────────────────────────────────────────────────────


def test_multi_category_merchants_are_exactly_the_six_of_the_spec() -> None:
    # D32: this flag decides ask_what_item ("what did you buy at eMAG?"); a wrong one would make
    # a grocery store ask what was bought.
    multi = {m["canonical_name"] for m in _merchants() if m["multi_category"]}

    assert multi == MULTI_CATEGORY


@pytest.mark.parametrize(
    ("merchant_id", "category"),
    [
        ("mega_image", "groceries"),  # Matei, Scene A
        ("shop_and_go", "groceries"),  # Ioana / Matei, Scene E
        ("kaufland", "groceries"),  # Ioana's Saturday shop
        ("glovo", "food_delivery"),  # Matei's "reduce" category
        ("emag", "electronics"),  # Andrei / Bianca, Scene B
        ("dr_max", "health_pharmacy"),  # acceptance #11 (never asked)
        ("wizz_air", "travel"),  # Matei's flight, Scene C
        ("world_class", "sport"),  # Matei's gym (arch 16.1)
        ("iabilet", "entertainment"),  # Matei's concerts, Andrei's football tickets
        ("5_to_go", "restaurants"),  # Bianca's coffee
        ("ctp_iasi", "transport"),  # Bianca's transport in Iași
        ("dazn", "subscriptions"),  # Andrei's sports streaming
    ],
)
def test_the_personas_merchants_exist_with_their_category(merchant_id: str, category: str) -> None:
    assert _by_id()[merchant_id]["category"] == category


def test_there_are_sports_streaming_services_and_restaurants() -> None:
    # Andrei's two sports subscriptions (overlap hint); Matei's Friday team lunch.
    by_id = _by_id()
    sports = [by_id[i] for i in ("digi_sport", "prima_sport", "voyo")]

    assert all(merchant["category"] == "subscriptions" for merchant in sports)
    assert sum(m["category"] == "restaurants" for m in _merchants()) >= 3


# ── invariants ──────────────────────────────────────────────────────────────────────────


def test_the_aliases_follow_every_rule() -> None:
    assert _alias_problems(_merchants()) == []


def test_the_alias_check_flags_each_broken_rule() -> None:
    # The invariant check itself can fail: one fake catalogue per rule.
    short = [{**VALID_ENTRY, "aliases": ["mega image", "mg"]}]
    no_canonical = [{**VALID_ENTRY, "aliases": ["megaimage"]}]
    repeated = [{**VALID_ENTRY, "aliases": ["mega image", "MEGA IMAGE"]}]
    spaced = [{**VALID_ENTRY, "aliases": ["mega image", "mega  image"]}]
    collision = [
        copy.deepcopy(VALID_ENTRY),
        {**VALID_ENTRY, "id": "other", "canonical_name": "Mega-Image", "aliases": ["mega-image"]},
    ]

    assert any("shorter than 3" in p for p in _alias_problems(short))
    assert any("canonical name" in p for p in _alias_problems(no_canonical))
    assert any("repeat after folding" in p for p in _alias_problems(repeated))
    assert any("stray spaces" in p for p in _alias_problems(spaced))
    assert any("collides with mega_image" in p for p in _alias_problems(collision))


@pytest.mark.parametrize(
    ("alias", "problem"),
    [
        ("mega image 0451", "store or order number"),
        ("payu*emag", "payment prefix"),
        ("pos mega image", "payment prefix"),
        ("mega image srl", "payment prefix"),
        ("kaufland cluj", "city"),
        ("mega image bucuresti", "city"),
        ("mega image sector 3", "city"),
        ("MEGA IMAGE", "not lower case"),
    ],
)
def test_the_alias_check_flags_a_whole_descriptor_used_as_an_alias(
    alias: str, problem: str
) -> None:
    # Review R7: alias rule 1. C2 strips numbers, prefixes and cities, so an alias holding them
    # could never match (and would hide a missing spelling).
    catalogue = [{**VALID_ENTRY, "aliases": ["mega image", alias]}]

    assert any(problem in p for p in _alias_problems(catalogue)), _alias_problems(catalogue)


def _longest_alias_match(descriptor: str) -> str | None:
    """A stand-in for C2's longest-alias match: the merchant whose folded alias is the longest
    substring of the folded descriptor; None when nothing matches or two merchants tie (an
    ambiguity C2 couldn't resolve either). C2 adds the stripping and token boundaries."""
    text = fold(descriptor)
    found = [(len(fold(a)), m["id"]) for m in _merchants() for a in m["aliases"] if fold(a) in text]
    if not found:
        return None
    longest = max(length for length, _ in found)
    winners = {merchant_id for length, merchant_id in found if length == longest}
    return winners.pop() if len(winners) == 1 else None


@pytest.mark.parametrize(
    ("descriptor", "merchant_id"),
    [
        ("MEGA IMAGE 0451 BUCURESTI", "mega_image"),
        ("SHOP&GO 123", "shop_and_go"),
        ("PAYU*EMAG.RO", "emag"),
        ("GLOVO*ORDER 8812", "glovo"),
        ("BOLT.EU/R/2304231234", "bolt"),  # R1: a ride
        ("BOLT.EU/O/2304231234", "bolt_food"),  # R1: a food order, not transport
        ("TAZZ BY EMAG 1234", "tazz"),  # R6: not eMAG (electronics, multi-category)
        ("WOLT.COM", "wolt"),  # R6
        ("OMV PETROM 0123", "petrom"),
        ("OMV 0123", "omv"),
        ("DIGI SPORT ONLINE", "digi_sport"),
        ("RCS&RDS DIGI", "digi"),
        ("DAZN LIMITED", "dazn"),  # R3: in Andrei's signature hints (arch 5.3.3)
        ("STEAMGAMES.COM 4259522985", "steam"),  # R9: domain forms on statements
        ("WIZZAIR.COM", "wizz_air"),
        ("CFRCALATORI.RO", "cfr_calatori"),
        ("RYANAIR.COM", "ryanair"),
        ("PPC ENERGIE SA", "ppc_energie"),  # R5: Enel Romania is now PPC
        ("ENEL ENERGIE", "ppc_energie"),
        ("WORLD CLASS ROMANIA", "world_class"),  # R4: Matei's gym
        ("IABILET.RO", "iabilet"),  # R4: concerts, football tickets
        ("EVENTIM.RO", "eventim"),
        ("5 TO GO 0042", "5_to_go"),  # R4: Bianca's coffee
        ("METROREX", "metrorex"),  # R4: public transport
        ("STB SA", "stb"),
        ("CTP IASI", "ctp_iasi"),
        ("Cărturești Verona", "carturesti"),
        ("CARTURESTI.RO", "carturesti"),
        ("EMAG TAZZ", None),  # two equally long aliases of different merchants: ambiguous
    ],
)
def test_statement_descriptors_reach_the_right_merchant(
    descriptor: str, merchant_id: str | None
) -> None:
    assert _longest_alias_match(descriptor) == merchant_id


def test_nested_aliases_are_exactly_the_reviewed_pairs() -> None:
    assert _nested_pairs(_merchants()) == NESTED


def test_mcc_and_category_agree_with_the_c2_fallback_table() -> None:
    disagree = [
        (m["id"], m["mcc"], m["category"])
        for m in _merchants()
        if m["mcc"] in MCC_FALLBACK
        and m["category"] not in MCC_FALLBACK[m["mcc"]]
        and m["id"] not in FOOD_DELIVERY_PLATFORMS
    ]

    assert disagree == []
    assert {m["category"] for m in _merchants() if m["id"] in FOOD_DELIVERY_PLATFORMS} == {
        "food_delivery"
    }


def test_every_spending_category_has_a_merchant() -> None:
    covered = {m["category"] for m in _merchants()}
    expected = {category.value for category in Category} - NO_MERCHANT_NEEDED

    assert sorted(expected - covered) == []
