"""C1.5: data/products.json, the 3 mock savings products (arch 4.4, 16.5; work-breakdown C1)."""

from decimal import Decimal
from typing import Any

from app.domain.enums import Liquidity, ProductKind
from tests.unit.datafiles import load_data, load_schema, schema_errors


def _products() -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = load_data("products")["products"]
    return products


def test_products_file_validates_against_its_schema() -> None:
    assert schema_errors("products", load_data("products")) == []


def test_the_schema_enums_are_f2_s() -> None:
    product = load_schema("products")["$defs"]["product"]["properties"]

    assert sorted(product["kind"]["enum"]) == sorted(kind.value for kind in ProductKind)
    assert sorted(product["liquidity"]["enum"]) == sorted(item.value for item in Liquidity)


def test_the_three_arch_products_one_per_kind() -> None:
    by_kind = {p["kind"]: p for p in _products()}

    assert {p["name"] for p in _products()} == {
        "Pușculiță flexibilă",
        "Cont de economii",
        "Depozit 6 luni",
    }
    assert sorted(by_kind) == sorted(kind.value for kind in ProductKind)
    assert by_kind["flexible_pot"]["liquidity"] == "instant"
    assert by_kind["term_deposit"]["liquidity"] == "locked"


def test_every_product_is_mock_with_a_valid_horizon() -> None:
    # Spec: "min_months < max_months; every product mock: true".
    for product in _products():
        assert product["mock"] is True
        assert product["min_months"] < product["max_months"]
        assert isinstance(product["rate"], Decimal)


def test_rates_rise_with_lock_in_and_horizons_cover_two_years() -> None:
    by_liquidity = {p["liquidity"]: p["rate"] for p in _products()}
    covered = {m for p in _products() for m in range(p["min_months"], p["max_months"] + 1)}

    assert by_liquidity["instant"] < by_liquidity["notice"] < by_liquidity["locked"]
    assert set(range(25)) <= covered  # C12 can rank something for any goal up to 2 years


def test_the_schema_rejects_a_non_mock_product() -> None:
    product = {**_products()[0], "mock": False}

    assert schema_errors("products", {"products": [product]})
