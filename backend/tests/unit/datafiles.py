"""Test helper for the reference data files in backend/data/ (C1): strict loading + schema checks.

Not a test module (no `test_` prefix). Numbers are parsed as `Decimal` (money is never a float), a
duplicate key fails instead of silently keeping the last value, NaN / Infinity are rejected, and
files must be UTF-8 without a BOM. Each `data/<name>.json` has its JSON Schema (2020-12) in
`data/schemas/<name>.schema.json`.
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, NoReturn

from jsonschema import Draft202012Validator

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SCHEMA_DIR = DATA_DIR / "schemas"
_BOM = b"\xef\xbb\xbf"


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _reject_non_finite(constant: str) -> NoReturn:
    raise ValueError(f"{constant} is not a finite number")


def parse_json(raw: bytes, source: str) -> Any:
    """Strict UTF-8 JSON: no BOM, no duplicate keys, no NaN / Infinity, every non-integer number
    a Decimal."""
    if raw.startswith(_BOM):
        raise ValueError(f"{source}: starts with a UTF-8 BOM")
    try:
        return json.loads(
            raw.decode("utf-8"),
            parse_float=Decimal,
            parse_constant=_reject_non_finite,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except ValueError as error:  # UnicodeDecodeError and JSONDecodeError are ValueErrors too
        raise ValueError(f"{source}: {error}") from error


def load_json(path: Path) -> Any:
    return parse_json(path.read_bytes(), path.name)


def load_data(name: str) -> Any:
    return load_json(DATA_DIR / f"{name}.json")


def load_schema(name: str) -> dict[str, Any]:
    """The schema of `data/<name>.json`, checked against the 2020-12 meta-schema."""
    schema: dict[str, Any] = load_json(SCHEMA_DIR / f"{name}.schema.json")
    Draft202012Validator.check_schema(schema)
    return schema


def schema_errors(name: str, instance: Any) -> list[str]:
    """Every violation of `data/schemas/<name>.schema.json` as "path: message" (empty = valid)."""
    validator = Draft202012Validator(
        load_schema(name), format_checker=Draft202012Validator.FORMAT_CHECKER
    )
    return sorted(
        f"{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
        for error in validator.iter_errors(instance)
    )
