"""C1.2: the data-file loader is strict, so the data tests can trust what they read."""

import re
from decimal import Decimal

import pytest

from tests.unit.datafiles import parse_json


def test_parse_json_reads_numbers_as_exact_decimals_and_keeps_integers() -> None:
    data = parse_json(b'{"basket": 85.00, "cv": 0.20, "months": 3}', "x.json")

    assert data == {"basket": Decimal("85.00"), "cv": Decimal("0.20"), "months": 3}
    assert isinstance(data["basket"], Decimal)
    assert str(data["basket"]) == "85.00"  # written precision kept: no float on the way
    assert type(data["months"]) is int


def test_parse_json_rejects_a_duplicate_key() -> None:
    # json.loads alone silently keeps the last value: one prior would replace another.
    with pytest.raises(ValueError, match=re.escape("priors.json: duplicate key 'groceries'")):
        parse_json(b'{"groceries": 1, "groceries": 2}', "priors.json")


def test_parse_json_rejects_a_duplicate_key_in_a_nested_object() -> None:
    with pytest.raises(ValueError, match="duplicate key 'mcc'"):
        parse_json(b'{"merchants": [{"mcc": "5411", "mcc": "5412"}]}', "merchants.json")


def test_parse_json_rejects_a_byte_order_mark() -> None:
    with pytest.raises(ValueError, match=re.escape("x.json: starts with a UTF-8 BOM")):
        parse_json(b'\xef\xbb\xbf{"a": 1}', "x.json")


def test_parse_json_rejects_invalid_utf8_naming_the_file() -> None:
    with pytest.raises(ValueError, match=re.escape("x.json: 'utf-8' codec")):
        parse_json(b'{"a": "\xff"}', "x.json")


def test_parse_json_rejects_malformed_json_naming_the_file() -> None:
    with pytest.raises(ValueError, match=re.escape("x.json: Expecting value")):
        parse_json(b'{"a": }', "x.json")


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_parse_json_rejects_non_finite_numbers_naming_the_file(constant: str) -> None:
    # Review R8: json accepts these by default and returns a float, not a Decimal.
    with pytest.raises(
        ValueError, match=re.escape(f"priors.json: {constant} is not a finite number")
    ):
        parse_json(f'{{"cv": {constant}}}'.encode(), "priors.json")
