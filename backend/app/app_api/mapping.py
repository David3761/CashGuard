"""Pure mapping from the platform's rows to the app's JSON (API_SPEC.md). No I/O.

The app casts with `as int` / `as String` and throws on an unknown enum value, so every helper
here returns exactly the type and the closed set of values the Dart models accept.
"""

import re
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Final, Literal, Protocol

from app.context.normalize import normalize
from app.domain.enums import Category, Direction

TxType = Literal["payment", "transfer_in", "transfer_out"]
Sender = Literal["user", "assistant"]

TRANSFER_OUT_CATEGORIES: Final = frozenset(
    {Category.TRANSFERS, Category.SAVINGS, Category.HOUSING_RENT}
)
"""Debits the app shows as outgoing transfers (David G., 2026-10-29); every other debit is a
card payment."""

TRANSFER_ID_OFFSET: Final = 1_000_000_000
"""Savings transfers (a `transfers` row) share the app's id space with transactions: they are
shown as `TRANSFER_ID_OFFSET + transfers.id`, positive and never equal to a transaction id."""

SAVINGS_TITLE: Final = {"ro": "Economii", "en": "Savings"}


def to_bani(amount: Decimal) -> int:
    """Lei → integer bani, half-up (amounts are NUMERIC(12,2), so this is exact)."""
    return int((Decimal(amount) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def signed_bani(amount: Decimal, direction: str) -> int:
    """Bani, negative when the money left the account."""
    bani = to_bani(amount)
    return -bani if Direction(direction) == Direction.DEBIT else bani


def iso_utc(moment: datetime) -> str:
    """ISO 8601 in UTC with a `Z`, whole seconds: `2026-06-15T09:00:00Z`."""
    if moment.tzinfo is None:
        raise ValueError("an aware datetime is required")
    return moment.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def transaction_type(direction: str, category: str | None) -> TxType:
    """credit → transfer_in; a debit in TRANSFER_OUT_CATEGORIES → transfer_out; else payment."""
    if Direction(direction) == Direction.CREDIT:
        return "transfer_in"
    if category is not None and category in TRANSFER_OUT_CATEGORIES:
        return "transfer_out"
    return "payment"


def transaction_title(merchant: str | None, merchant_raw: str, mcc: str | None = None) -> str:
    """The canonical merchant name, else C2's display name of the bank text, never empty."""
    if merchant and merchant.strip():
        return merchant.strip()
    name = normalize(merchant_raw, mcc).name.strip()
    return name or merchant_raw.strip() or "?"


class _Message(Protocol):
    @property
    def id(self) -> int | None: ...
    @property
    def role(self) -> str: ...
    @property
    def content(self) -> str: ...
    @property
    def created_at(self) -> datetime: ...


def sender(role: str) -> Sender:
    if role == "user":
        return "user"
    if role == "assistant":
        return "assistant"
    raise ValueError(f"unknown message role {role!r}")


def message_json(message: _Message) -> dict[str, object]:
    """A stored chat message as the app's `ChatMessage.fromJson` reads it."""
    if message.id is None or message.id <= 0:
        raise ValueError("a stored message has a positive id")
    return {
        "id": message.id,
        "text": message.content,
        "sender": sender(str(message.role)),
        "created_at": iso_utc(message.created_at),
    }


_WORDS = re.compile(r"\s*\S+\s*")
WORDS_PER_CHUNK: Final = 3


def reply_chunks(text: str, words: int = WORDS_PER_CHUNK) -> list[str]:
    """The reply cut into `delta` chunks of about `words` words. `"".join(chunks) == text`
    always (whitespace kept), and no chunk is empty; an empty text gives no chunk."""
    pieces = _WORDS.findall(text)
    if "".join(pieces) != text:  # only whitespace (or nothing): one chunk, or none
        return [text] if text else []
    return ["".join(pieces[i : i + words]) for i in range(0, len(pieces), words)]
