"""C1.3: data/priors.json, single-adult priors for VARIABLE spending (arch 5.3.5, D-kids).

Read by danutu's E6 (baselines: the prior * household_scale * city_index for the household-scaled
categories, kids per child, blended with the person's history) and E8 (short-history forecast).
Fixed costs (rent, utilities, phone, subscriptions) have no prior: they come from each person's
fixed costs / recurring detection (David G., D-variable).
"""

import math
import re
from decimal import ROUND_HALF_UP, Decimal
from functools import cache
from typing import Any

import pytest

from app.domain.enums import HOUSEHOLD_SCALED_CATEGORIES, Category
from app.i18n.text import fold
from tests.unit.datafiles import load_data, load_schema, schema_errors

NOT_SPENDING = {Category.TRANSFERS, Category.INCOME, Category.SAVINGS}
FIXED_COSTS = {Category.HOUSING_RENT, Category.UTILITIES, Category.TELECOM, Category.SUBSCRIPTIONS}
VARIABLE = sorted(c.value for c in Category if c not in NOT_SPENDING | FIXED_COSTS)
SCALED = {category.value for category in HOUSEHOLD_SCALED_CATEGORIES}
CENT = Decimal("0.01")
FIELDS = ("monthly_mean", "basket_median", "basket_cv", "cv")
# Bought less often than once a month: one transaction is bigger than the average month.
LUMPY = {"electronics", "clothing", "sport", "education", "books", "travel", "gifts", "other"}

# The whole table, reviewed against the C1.3 rework (report: old -> new, why).
# category -> (monthly_mean, basket_median, basket_cv, cv); single adult (kids: per child).
GOLDEN = {
    "groceries": ("900.00", "70.00", "0.60", "0.35"),
    "restaurants": ("200.00", "55.00", "0.50", "0.62"),
    "food_delivery": ("100.00", "55.00", "0.40", "0.83"),
    "transport": ("100.00", "25.00", "0.80", "0.72"),
    "fuel": ("450.00", "220.00", "0.30", "0.75"),
    "electronics": ("60.00", "250.00", "1.00", "3.43"),
    "clothing": ("120.00", "150.00", "0.70", "1.51"),
    "sport": ("50.00", "120.00", "0.80", "2.25"),
    "health_pharmacy": ("60.00", "45.00", "0.80", "1.26"),
    "kids": ("350.00", "100.00", "0.80", "0.77"),
    "education": ("100.00", "300.00", "0.80", "2.51"),
    "books": ("25.00", "50.00", "0.60", "1.78"),
    "entertainment": ("100.00", "70.00", "0.80", "1.21"),
    "travel": ("120.00", "500.00", "0.80", "2.96"),
    "gifts": ("60.00", "100.00", "0.70", "1.74"),
    "pets": ("180.00", "90.00", "0.60", "0.89"),
    "household_goods": ("50.00", "45.00", "0.60", "1.19"),
    "personal_care": ("60.00", "50.00", "0.60", "1.15"),
    "other": ("40.00", "50.00", "0.80", "1.62"),
}

# arch 16.1 + documented assumptions (danutu's profile.json will be the source; E13 calibrates).
# net, fixed costs, household scale, city, children, student
PERSONAS: dict[str, tuple[int, int, str, str, int, bool]] = {
    # rent 2000, utilities 350, phone 60, Spotify 25, gym 180 (arch 16.1)
    "matei": (7000, 2615, "1.0", "București", 0, False),
    # rent 2600 (arch); utilities ~400, phone 60, 2 sports streams ~60 (assumed); city assumed
    "andrei": (9000, 3120, "1.5", "București", 0, False),
    # rent share 700 incl. utilities (arch: shared flat), phone 50 (assumed)
    "bianca": (2800, 750, "1.0", "Iași", 0, True),
    # mortgage 3200 (arch); utilities ~700, phones 120, subscriptions 50 (assumed)
    "ioana": (15500, 4070, "2.1", "Cluj-Napoca", 2, False),
}
NO_VEHICLE_OR_PET = {"fuel", "pets"}  # no persona has a vehicle or a pet fact (arch 16.1)
ESSENTIAL = {"groceries", "transport", "health_pharmacy", "kids"}  # arch 4.5 essential_living

VALID_PRIOR: dict[str, Any] = {
    "monthly_mean": Decimal("900.00"),
    "basket_median": Decimal("70.00"),
    "basket_cv": Decimal("0.60"),
    "cv": Decimal("0.35"),
}


@cache
def _priors() -> dict[str, Any]:
    data: dict[str, Any] = load_data("priors")
    return data


def _city_key(name: str) -> str:
    """The city key E6 is told to use (HANDOFFS): folded words without punctuation, ignored words
    ("municipiul", "romania", "sector"...) and numbers, joined without spaces."""
    ignored = set(_priors()["city_ignored_words"])
    words = re.split(r"[^0-9a-z]+", fold(name))
    return "".join(w for w in words if w and w not in ignored and not w.isdigit())


def _city(name: str) -> dict[str, Any] | None:
    key = _city_key(name)
    for entry in _priors()["cities"]:
        if key and key in {_city_key(n) for n in entry["names"]}:
            found: dict[str, Any] = entry
            return found
    return None


def _city_index(name: str) -> Decimal:
    entry = _city(name)
    index: Decimal = entry["index"] if entry else _priors()["default_city_index"]
    return index


def _monthly(category: str, scale: Decimal, city: str, children: int) -> Decimal:
    """E6's monthly prior as specified (arch 5.3.5 + D-kids): kids per child, the other
    household-scaled categories * scale; the city index only on household-scaled categories."""
    mean: Decimal = _priors()["categories"][category]["monthly_mean"]
    if category == "kids":
        return mean * children * _city_index(city)
    if category in SCALED:
        return mean * scale * _city_index(city)
    return mean


def _basket(category: str, scale: Decimal, city: str) -> Decimal:
    """E6's basket prior (prior_median): * scale * city index for household-scaled categories;
    kids per transaction (not per child)."""
    basket: Decimal = _priors()["categories"][category]["basket_median"]
    if category == "kids":
        return basket * _city_index(city)
    if category in SCALED:
        return basket * scale * _city_index(city)
    return basket


def _blended(category: str, personal: Decimal, n: int, scale: Decimal, city: str) -> Decimal:
    """arch 5.3.5: expected = (n * personal + 5 * prior) / (n + 5)."""
    return (n * personal + 5 * _basket(category, scale, city)) / (n + 5)


def _variable_month(persona: str) -> Decimal:
    _, _, scale, city, children, student = PERSONAS[persona]
    categories = set(VARIABLE) - NO_VEHICLE_OR_PET - (set() if student else {"education"})
    return sum((_monthly(c, Decimal(scale), city, children) for c in categories), start=Decimal(0))


def _with(**changes: Any) -> dict[str, Any]:
    document = {
        "categories": {category: VALID_PRIOR for category in VARIABLE},
        "cities": [{"id": "bucuresti", "names": ["București"], "index": Decimal("1.00")}],
        "city_ignored_words": ["municipiul"],
        "default_city_index": Decimal("1.00"),
    }
    document.update(changes)
    return document


# ── happy path & the variable-only rule ─────────────────────────────────────────────────


def test_priors_file_validates_against_its_schema() -> None:
    assert schema_errors("priors", _priors()) == []


def test_priors_schema_is_a_draft_2020_12_schema() -> None:
    assert load_schema("priors")["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_the_schema_lists_exactly_the_variable_categories_of_f2() -> None:
    categories = load_schema("priors")["properties"]["categories"]

    assert sorted(categories["propertyNames"]["enum"]) == VARIABLE
    assert sorted(categories["required"]) == VARIABLE


def test_there_is_a_prior_for_every_variable_category_and_nothing_else() -> None:
    assert sorted(_priors()["categories"]) == VARIABLE


def test_fixed_cost_categories_have_no_prior() -> None:
    # D-variable: rent, utilities, phone and subscriptions come from the person's fixed costs.
    assert {c.value for c in FIXED_COSTS} & set(_priors()["categories"]) == set()


def test_the_numbers_match_the_reviewed_golden_snapshot() -> None:
    actual = {
        category: tuple(str(prior[field]) for field in FIELDS)
        for category, prior in _priors()["categories"].items()
    }

    assert actual == GOLDEN


# ── boundaries & invalid input ──────────────────────────────────────────────────────────


def test_the_valid_sample_document_passes() -> None:
    assert schema_errors("priors", _with()) == []


@pytest.mark.parametrize(
    ("field", "value", "valid"),
    [
        ("cv", Decimal("0"), False),
        ("cv", Decimal("0.01"), True),
        ("cv", Decimal("4.99"), True),  # lumpy categories are honest up to ~3.5 (cap 5)
        ("cv", Decimal("5"), False),
        ("basket_cv", Decimal("0"), False),
        ("basket_cv", Decimal("3"), True),
        ("basket_cv", Decimal("3.01"), False),
        ("monthly_mean", Decimal("0"), False),
        ("monthly_mean", Decimal("0.01"), True),
        ("monthly_mean", Decimal("10000"), True),  # a sane upper bound (review R10)
        ("monthly_mean", Decimal("90000.00"), False),  # a slipped zero
        ("basket_median", Decimal("10000.01"), False),
        ("basket_median", Decimal("-70"), False),
        ("basket_median", "70.00", False),
        ("basket_median", True, False),
    ],
)
def test_prior_boundaries(field: str, value: Any, valid: bool) -> None:
    categories = {category: VALID_PRIOR for category in VARIABLE}
    categories["groceries"] = {**VALID_PRIOR, field: value}
    errors = schema_errors("priors", _with(categories=categories))

    assert (errors == []) is valid, errors
    assert all(f"categories/groceries/{field}" in error for error in errors), errors


@pytest.mark.parametrize(
    ("index", "valid"),
    [
        (Decimal("0"), False),
        (Decimal("0.01"), True),
        (Decimal("2.00"), True),
        (Decimal("2.01"), False),
    ],
)
def test_city_index_boundaries(index: Decimal, valid: bool) -> None:
    city = {"id": "iasi", "names": ["Iași"], "index": index}

    assert (schema_errors("priors", _with(cities=[city])) == []) is valid
    assert (schema_errors("priors", _with(default_city_index=index)) == []) is valid


@pytest.mark.parametrize(
    "categories",
    [
        {**{c: VALID_PRIOR for c in VARIABLE}, "food": VALID_PRIOR},
        {**{c: VALID_PRIOR for c in VARIABLE}, "housing_rent": VALID_PRIOR},  # a fixed cost
        {**{c: VALID_PRIOR for c in VARIABLE}, "transfers": VALID_PRIOR},  # not spending
        {c: VALID_PRIOR for c in VARIABLE if c != "kids"},
        {**{c: VALID_PRIOR for c in VARIABLE}, "groceries": {"monthly_mean": Decimal(900)}},
        {**{c: VALID_PRIOR for c in VARIABLE}, "groceries": {**VALID_PRIOR, "scaled": True}},
    ],
    ids=["unknown", "fixed-cost", "not-spending", "missing", "incomplete-prior", "extra-field"],
)
def test_the_schema_rejects_a_bad_category_table(categories: dict[str, Any]) -> None:
    assert schema_errors("priors", _with(categories=categories))


@pytest.mark.parametrize(
    "changes",
    [
        {"cities": []},
        {"cities": [{"id": "iasi", "names": [], "index": Decimal("0.85")}]},
        {"cities": [{"id": "iasi", "names": ["Iași", "Iași"], "index": Decimal("0.85")}]},
        {"cities": [{"id": "Iași", "names": ["Iași"], "index": Decimal("0.85")}]},
        {"cities": [{"id": "iasi", "index": Decimal("0.85")}]},
        {"cities": [{"id": "iasi", "names": ["Iași"], "index": Decimal("0.85"), "x": 1}]},
        {"city_ignored_words": ["Municipiul"]},  # folded lower-case ASCII words only
        {"city_ignored_words": ["sector 3"]},
    ],
    ids=[
        "no-city",
        "no-names",
        "repeated-name",
        "id-not-a-slug",
        "names-missing",
        "extra-field",
        "ignored-not-folded",
        "ignored-not-a-word",
    ],
)
def test_the_schema_rejects_bad_city_data(changes: dict[str, Any]) -> None:
    assert schema_errors("priors", _with(**changes))


def test_the_schema_rejects_a_bad_envelope() -> None:
    assert schema_errors("priors", {**_with(), "version": 2})
    assert schema_errors("priors", {k: v for k, v in _with().items() if k != "city_ignored_words"})


# ── money ───────────────────────────────────────────────────────────────────────────────


def test_every_number_is_an_exact_decimal_with_at_most_two_decimals() -> None:
    numbers = [p[field] for p in _priors()["categories"].values() for field in FIELDS]
    numbers += [city["index"] for city in _priors()["cities"]] + [_priors()["default_city_index"]]

    for number in numbers:
        assert isinstance(number, Decimal), number
        assert number == number.quantize(CENT), number


# ── language: the user's city arrives in any spelling (review R6) ───────────────────────


@pytest.mark.parametrize(
    ("city", "city_id"),
    [
        ("București", "bucuresti"),
        ("BUCUREȘTI", "bucuresti"),
        ("Bucuresti", "bucuresti"),
        ("Bucharest", "bucuresti"),
        ("Bucharest, RO", "bucuresti"),
        ("Municipiul București", "bucuresti"),
        ("București, Sector 3", "bucuresti"),
        ("Cluj-Napoca", "cluj"),
        ("Cluj Napoca", "cluj"),
        ("CLUJ-NAPOCA", "cluj"),
        ("cluj", "cluj"),
        ("Iași", "iasi"),
        ("Iași ", "iasi"),
        ("IASI", "iasi"),
        ("Iasi, Romania", "iasi"),
        ("Mun. Iași", "iasi"),
        ("Timișoara", None),  # not listed: the default index
        ("", None),
        ("   ", None),
    ],
)
def test_a_city_in_any_spelling_finds_its_entry(city: str, city_id: str | None) -> None:
    entry = _city(city)

    assert (entry["id"] if entry else None) == city_id


def test_bianca_in_iasi_gets_0_85_not_the_default() -> None:
    # Review R6: a missed match silently gives 1.00 instead of 0.85.
    assert _city_index("Iasi, Romania") == Decimal("0.85")
    assert _city_index("Timișoara") == _priors()["default_city_index"] == Decimal("1.00")


def test_city_names_keep_their_diacritics_and_their_keys_are_unique() -> None:
    keys = [_city_key(name) for city in _priors()["cities"] for name in city["names"]]
    names = {name for city in _priors()["cities"] for name in city["names"]}

    assert {"București", "Iași"} <= names
    assert len(keys) == len(set(keys))  # no two names (of any cities) share a key
    assert len({city["id"] for city in _priors()["cities"]}) == len(_priors()["cities"])


# ── plausibility (review R7): the numbers make sense, not just match a copy ─────────────


def test_only_the_named_lumpy_categories_have_a_basket_above_their_month() -> None:
    above = {
        c for c, p in _priors()["categories"].items() if p["basket_median"] > p["monthly_mean"]
    }

    assert above == LUMPY


def test_every_lumpy_category_varies_more_than_every_steady_one() -> None:
    cvs = {c: p["cv"] for c, p in _priors()["categories"].items()}

    assert min(cvs[c] for c in LUMPY) > max(cvs[c] for c in cvs if c not in LUMPY)


def test_each_cv_follows_from_the_purchase_rate_and_the_basket() -> None:
    # Review R4: compound Poisson. Purchases at rate monthly_mean / basket_mean, each a lognormal
    # amount (median basket_median, cv basket_cv) => cv = sqrt((1 + cb^2)^1.5 * basket / mean).
    for category, p in _priors()["categories"].items():
        spread = 1 + float(p["basket_cv"]) ** 2
        derived = math.sqrt(spread**1.5 * float(p["basket_median"]) / float(p["monthly_mean"]))
        expected = Decimal(str(derived)).quantize(CENT, rounding=ROUND_HALF_UP)
        assert abs(p["cv"] - expected) <= CENT, (category, p["cv"], expected)


@pytest.mark.parametrize(("persona", "share"), [("matei", "0.60"), ("andrei", "0.60"),
                                                ("ioana", "0.60"), ("bianca", "1.00")])  # fmt: skip
def test_a_persona_s_prior_variable_month_fits_their_disposable_income(
    persona: str, share: str
) -> None:
    # Bianca (student, irregular income) may use all of it; the employed personas at most 60%.
    net, fixed, *_ = PERSONAS[persona]

    assert _variable_month(persona) <= Decimal(share) * (net - fixed)


@pytest.mark.parametrize("persona", sorted(PERSONAS))
def test_the_essentials_floor_is_under_half_of_each_persona_s_daily_free_money(
    persona: str,
) -> None:
    # arch 5.3.5: essentials floor = sum of essential monthly expectations / days in the month.
    net, fixed, scale, city, children, _ = PERSONAS[persona]
    floor = (
        sum((_monthly(c, Decimal(scale), city, children) for c in ESSENTIAL), start=Decimal(0)) / 30
    )

    assert floor < Decimal("0.5") * (net - fixed) / 30


def test_a_young_single_adult_s_variable_month_is_coherent_with_5000_net() -> None:
    # ~5.000 net, fixed ~2.260 (rent 1.800, utilities 350, phone 60, subscriptions 50).
    categories = set(VARIABLE) - NO_VEHICLE_OR_PET - {"education", "kids"}
    month = sum((_monthly(c, Decimal(1), "București", 0) for c in categories), start=Decimal(0))
    disposable = Decimal(5000 - 2260)

    assert Decimal("0.40") * disposable <= month <= Decimal("0.85") * disposable


# ── personalisation & regression: the arch numbers and the demo baselines (review R8) ───


def test_city_indices_are_the_arch_values() -> None:
    indices = {city["id"]: city["index"] for city in _priors()["cities"]}

    assert indices == {
        "bucuresti": Decimal("1.00"),
        "cluj": Decimal("1.00"),
        "iasi": Decimal("0.85"),
    }
    assert _priors()["default_city_index"] == Decimal("1.00")


def test_a_family_of_four_gets_the_arch_groceries_month() -> None:
    # arch 5.3.9: "acum sunteți 4 acasă, am mutat cumpărăturile la 1.890 lei/lună" (scale 2.1).
    assert _monthly("groceries", Decimal("2.1"), "Cluj-Napoca", 2) == Decimal("1890.00")


def test_the_city_index_applies_only_to_household_scaled_categories() -> None:
    for category in VARIABLE:
        bucharest = _monthly(category, Decimal(1), "București", 1)
        iasi = _monthly(category, Decimal(1), "Iași", 1)
        factor = Decimal("0.85") if category in SCALED else Decimal(1)
        assert iasi == bucharest * factor, category


@pytest.mark.parametrize(
    ("children", "scale", "city", "expected"),
    [
        (0, "1.0", "București", "0"),  # no children: no kids prior
        (2, "2.1", "Cluj-Napoca", "700.00"),  # Ioana: per child, not the OECD scale
        (2, "1.0", "Cluj-Napoca", "700.00"),  # the household scale has no effect on kids
        (1, "1.5", "Iași", "297.5000"),  # the city index still applies (household-scaled list)
    ],
)
def test_the_kids_prior_is_per_child(children: int, scale: str, city: str, expected: str) -> None:
    # D-kids (David G.): E6 multiplies the kids prior by the number of children.
    assert _monthly("kids", Decimal(scale), city, children) == Decimal(expected)


def test_matei_s_groceries_baseline_stays_at_his_85() -> None:
    # B12 "85 ± 10"; E12 gives him ~60 groceries transactions in 4 months (3-4 a week).
    assert abs(_blended("groceries", Decimal(85), 60, Decimal(1), "București") - 85) <= 2
    for n in (20, 100, 200):
        assert abs(_blended("groceries", Decimal(85), n, Decimal(1), "București") - 85) <= Decimal(
            3
        )


def test_ioana_s_family_baseline_stays_at_her_140() -> None:
    # arch 5.3.4: family median 140 at scale 2.1, Cluj; E12 "140 ± 15"; ~100+ transactions.
    assert abs(_blended("groceries", Decimal(140), 100, Decimal("2.1"), "Cluj-Napoca") - 140) <= 1
    for n in (20, 60, 200):
        expected = _blended("groceries", Decimal(140), n, Decimal("2.1"), "Cluj-Napoca")
        assert abs(expected - 140) <= Decimal(2)


def test_bianca_in_iasi_starts_from_the_city_indexed_prior() -> None:
    # A household-scaled category gets the Iași index, a non-scaled one doesn't.
    assert _blended("groceries", Decimal(0), 0, Decimal(1), "Iași") == Decimal("59.5000")
    assert _blended("restaurants", Decimal(0), 0, Decimal(1), "Iași") == Decimal("55.00")
