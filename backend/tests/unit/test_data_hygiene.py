"""C1.2+: hygiene of every data file and schema in backend/data/ (picked up automatically).

UTF-8 without a BOM, diacritics written literally (no \\u escapes: readable diffs), NFC strings with
comma-below s/t (no cedilla), no control or format characters, no IBAN or card-like numbers
(the data is fictional), and every data file validates against its schema.
"""

import re
import unicodedata
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.unit.datafiles import DATA_DIR, SCHEMA_DIR, load_json, schema_errors

DATA_FILES = sorted(DATA_DIR.glob("*.json"))
SCHEMA_FILES = sorted(SCHEMA_DIR.glob("*.schema.json"))
ALL_FILES = DATA_FILES + SCHEMA_FILES
CEDILLAS = set("\u015f\u0163\u015e\u0162")
ESCAPE = re.compile(r"\\u[0-9a-fA-F]{4}")
IBAN = re.compile(r"RO\d{2}[A-Z]{4}[A-Z0-9]{16}")
CARD_LIKE = re.compile(r"\d{13,19}")


def _strings(node: Any) -> Iterator[str]:
    """Every string in a JSON document: object keys and values, recursively."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _strings(item)


def test_the_data_folder_has_data_files_and_schemas() -> None:
    # Guards the parametrised tests below against passing vacuously on an empty glob.
    assert DATA_FILES
    assert len(SCHEMA_FILES) >= len(DATA_FILES)


@pytest.mark.parametrize("path", ALL_FILES, ids=lambda path: path.name)
def test_data_file_is_clean_utf8_text(path: Path) -> None:
    raw = path.read_bytes()
    text = raw.decode("utf-8")

    assert not raw.startswith(b"\xef\xbb\xbf")
    assert text.endswith("\n")
    assert not ESCAPE.search(text), "write diacritics literally"
    assert not IBAN.search(text)
    assert not CARD_LIKE.search(text)


@pytest.mark.parametrize("path", ALL_FILES, ids=lambda path: path.name)
def test_every_string_is_nfc_with_comma_below_and_no_invisible_characters(path: Path) -> None:
    for text in _strings(load_json(path)):
        assert unicodedata.normalize("NFC", text) == text, text
        assert not CEDILLAS & set(text), text
        assert not any(unicodedata.category(ch) in {"Cc", "Cf"} for ch in text), repr(text)


@pytest.mark.parametrize("path", DATA_FILES, ids=lambda path: path.name)
def test_every_data_file_validates_against_its_schema(path: Path) -> None:
    assert schema_errors(path.stem, load_json(path)) == []
