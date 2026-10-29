"""Merchant normalisation (C2): bank text -> a catalogue merchant, a display name and a category.

`normalize(merchant_raw, mcc, script_category)` is pure (the catalogue is read once from
`data/merchants.json`, C1) and never raises on any text.

How it works:
1. **Fold** (`app.i18n.text.fold`: case, diacritics, look-alike punctuation), then split into
   **tokens**: runs of letters or of digits. Every other character is a separator, and a letter /
   digit boundary splits too ("MEGAIMAGE0451" -> megaimage, 0451). So `PAYU*EMAG.RO`,
   `BOLT.EU/O/123`, `SHOP&GO 123` and `Cărturești Verona` become token lists.
2. **Longest alias match**: every alias is a token sequence too; an alias matches a contiguous
   run of the text's tokens. The longest matching alias (in letters + digits) wins, so the
   pinned nested pairs resolve to the longer merchant (`BOLT.EU/O/…` -> Bolt Food, `TAZZ BY EMAG`
   -> Tazz, `DIGI SPORT` -> Digi Sport). Two *different* merchants tied for the longest match is
   ambiguous: no merchant (the MCC decides the category).
3. **Noise**: payment prefixes (POS, PAYU, SC, SRL, ORDER…), city tokens and store numbers can't
   break the match (it works on token boundaries, so they are never part of an alias). They are
   stripped from the **display name** of an unknown merchant: `POS LA MAMA 0042 BUCURESTI` ->
   "La Mama". City tokens are not stripped *before* matching: `CTP IAȘI` is a merchant.
4. **Category**: the script category always wins; else the merchant's; else the MCC table
   (work-breakdown C2); else `other`.
"""

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Final

from app.domain.enums import Category
from app.domain.models import Merchant
from app.domain.money import parse_json
from app.i18n.text import fold

MERCHANTS_FILE: Final = Path(__file__).resolve().parents[2] / "data" / "merchants.json"
MAX_INPUT: Final = 500
"""Only the first characters are read: bank text is short (B8 caps it at 200)."""

_TOKEN: Final = re.compile(r"\d+|[^\W\d_]+")

MCC_CATEGORIES: Final[dict[str, Category]] = {
    "5411": Category.GROCERIES,
    "5812": Category.RESTAURANTS,
    "5814": Category.RESTAURANTS,
    "5541": Category.FUEL,
    "5912": Category.HEALTH_PHARMACY,
    "4111": Category.TRANSPORT,
    "4511": Category.TRAVEL,
    "5732": Category.ELECTRONICS,
    "5941": Category.SPORT,
    "5942": Category.BOOKS,
    "5815": Category.SUBSCRIPTIONS,  # digital media (music, video)
    "5816": Category.ENTERTAINMENT,  # digital games
    "5817": Category.SUBSCRIPTIONS,  # software applications
    "4814": Category.TELECOM,
    "4900": Category.UTILITIES,
}
"""The MCC fallback for an unknown merchant (work-breakdown C2)."""

NOISE_TOKENS: Final = frozenset(
    {
        # payment processors, terminals and legal forms
        "pos", "epos", "payu", "netopia", "mobilpay", "sumup", "paypal", "smartpay", "ecom",
        "sc", "srl", "sa", "sra", "pfa", "ii", "order", "ord", "www", "com", "ro", "nr",
        # Romanian cities and address words
        "bucuresti", "bucharest", "buc", "sector", "sect", "cluj", "napoca", "iasi", "timisoara",
        "brasov", "constanta", "sibiu", "oradea", "craiova", "galati", "ploiesti", "pitesti",
        "arad", "bacau", "suceava", "romania",
    }
)  # fmt: skip
"""Tokens stripped from an unknown merchant's display name (folded). No alias is only noise."""


@dataclass(frozen=True, slots=True)
class NormalizedMerchant:
    """The result of `normalize`. `merchant_id` is None when no catalogue merchant matched."""

    merchant_id: str | None
    name: str
    category: Category
    multi_category: bool = False  # D32: eMAG, Altex… sell many categories, items matter


def tokens(text: str) -> tuple[str, ...]:
    """The folded letter / digit runs of `text` (the matching key of C2)."""
    return tuple(_TOKEN.findall(fold(text[:MAX_INPUT])))


@cache
def load_merchants() -> tuple[Merchant, ...]:
    """The catalogue (data/merchants.json), read strictly once (H-7)."""
    data = parse_json(MERCHANTS_FILE.read_bytes())
    if not isinstance(data, dict) or not isinstance(data.get("merchants"), list):
        raise ValueError(f"{MERCHANTS_FILE.name}: expected {{'merchants': [...]}}")
    return tuple(Merchant.model_validate(entry) for entry in data["merchants"])


@cache
def _alias_index() -> tuple[dict[tuple[str, ...], Merchant], int]:
    """Alias token sequence -> merchant (the canonical name counts as an alias), + the longest
    alias in tokens. A sequence shared by two merchants is a data error (C1 guarantees none)."""
    index: dict[tuple[str, ...], Merchant] = {}
    for merchant in load_merchants():
        for alias in (*merchant.aliases, merchant.canonical_name):
            key = tokens(alias)
            if not key:
                continue
            other = index.setdefault(key, merchant)
            if other.id != merchant.id:
                raise ValueError(f"alias {alias!r} of {merchant.id} is also {other.id}'s")
    return index, max(map(len, index))


def _match(words: tuple[str, ...]) -> Merchant | None:
    """The merchant of the longest alias found in `words`; None if none or a tie."""
    index, longest = _alias_index()
    best_length = 0
    best: set[str] = set()
    winner: Merchant | None = None
    for start in range(len(words)):
        for size in range(1, min(longest, len(words) - start) + 1):
            merchant = index.get(words[start : start + size])
            if merchant is None:
                continue
            length = sum(map(len, words[start : start + size]))
            if length > best_length:
                best_length, best, winner = length, {merchant.id}, merchant
            elif length == best_length:
                best.add(merchant.id)
    return winner if len(best) == 1 else None


def _display_name(merchant_raw: str, words: tuple[str, ...]) -> str:
    kept = [word for word in words if word not in NOISE_TOKENS and not word.isdigit()]
    if kept:
        return " ".join(kept).title()
    return " ".join(merchant_raw[:MAX_INPUT].split())


def normalize(
    merchant_raw: str, mcc: str | None = None, script_category: Category | None = None
) -> NormalizedMerchant:
    """Resolve bank text to a catalogue merchant (or None), a display name and a category.

    The script category always wins; then the merchant's category; then the MCC table; then
    `other`. Pure and total: never raises on any `merchant_raw` text.
    """
    words = tokens(merchant_raw)
    merchant = _match(words)
    if merchant is not None:
        return NormalizedMerchant(
            merchant_id=merchant.id,
            name=merchant.canonical_name,
            category=script_category or merchant.category,
            multi_category=merchant.multi_category,
        )
    fallback = MCC_CATEGORIES.get(mcc, Category.OTHER) if mcc is not None else Category.OTHER
    return NormalizedMerchant(
        merchant_id=None,
        name=_display_name(merchant_raw, words),
        category=script_category or fallback,
    )
