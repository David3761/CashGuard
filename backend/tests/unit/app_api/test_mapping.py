"""app.app_api.mapping + sse: the exact JSON the Flutter app's fromJson casts accept."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.app_api import sse
from app.app_api.mapping import (
    iso_utc,
    message_json,
    reply_chunks,
    signed_bani,
    to_bani,
    transaction_title,
    transaction_type,
)
from app.domain.enums import Category


@pytest.mark.parametrize(
    ("lei", "bani"),
    [
        ("0.01", 1),
        ("18.50", 1850),
        ("2847.35", 284735),
        ("7000", 700000),
        ("9999999999.99", 999999999999),
    ],
)
def test_to_bani_is_an_exact_int(lei, bani):
    assert to_bani(Decimal(lei)) == bani
    assert type(to_bani(Decimal(lei))) is int


def test_signed_bani_is_negative_for_debits():
    assert signed_bani(Decimal("18.50"), "debit") == -1850
    assert signed_bani(Decimal("150"), "credit") == 15000


@pytest.mark.parametrize("category", [None, *Category])
def test_credits_are_transfers_in(category):
    assert transaction_type("credit", category) == "transfer_in"


@pytest.mark.parametrize("category", [None, *Category])
def test_debits_are_payments_except_the_transfer_categories(category):
    expected = "transfer_out" if category in {"transfers", "savings", "housing_rent"} else "payment"
    assert transaction_type("debit", category) == expected


def test_transaction_type_rejects_an_unknown_direction():
    with pytest.raises(ValueError, match="sideways"):
        transaction_type("sideways", None)


@pytest.mark.parametrize(
    ("merchant", "raw", "title"),
    [
        ("Mega Image", "anything", "Mega Image"),
        (None, "MEGA IMAGE 0451 BUCURESTI", "Mega Image"),
        (None, "POS LA MAMA 0042 BUCURESTI", "La Mama"),
        ("  ", "GLOVO*ORDER 8812", "Glovo"),
        (None, "Cărturești Verona", "Cărturești"),
    ],
)
def test_title_prefers_the_merchant_then_the_display_name(merchant, raw, title):
    assert transaction_title(merchant, raw).startswith(title)


@given(st.text(max_size=60))
def test_title_is_never_empty(raw):
    assert transaction_title(None, raw)


def test_iso_utc_is_z_and_whole_seconds():
    bucharest = timezone(timedelta(hours=3))
    assert iso_utc(datetime(2026, 6, 15, 12, 0, 7, 999, tzinfo=bucharest)) == "2026-06-15T09:00:07Z"
    with pytest.raises(ValueError, match="aware"):
        iso_utc(datetime(2026, 6, 15))  # noqa: DTZ001 - naive on purpose


@dataclass
class Msg:
    id: int | None
    role: str
    content: str
    created_at: datetime


def test_message_json_shape():
    out = message_json(Msg(41, "user", "Salut", datetime(2026, 6, 15, 9, tzinfo=UTC)))
    assert out == {
        "id": 41,
        "text": "Salut",
        "sender": "user",
        "created_at": "2026-06-15T09:00:00Z",
    }


@pytest.mark.parametrize(
    "bad",
    [
        Msg(0, "user", "x", datetime(2026, 1, 1, tzinfo=UTC)),
        Msg(1, "system", "x", datetime(2026, 1, 1, tzinfo=UTC)),
    ],
)
def test_message_json_refuses_unstored_or_unknown_roles(bad):
    with pytest.raises(ValueError, match=r"positive id|unknown message role"):
        message_json(bad)


@given(st.text(max_size=300))
def test_chunks_join_back_to_the_text(text):
    chunks = reply_chunks(text)
    assert "".join(chunks) == text
    assert all(chunks)


def test_chunks_are_a_few_words_each():
    assert reply_chunks("Your current balance is 2.847,35 lei. 🙂") == [
        "Your current balance ",
        "is 2.847,35 lei. ",
        "🙂",
    ]
    assert reply_chunks("") == []


# ── SSE frames ──────────────────────────────────────────────────────────────────────────────


def test_a_frame_names_its_event_and_has_one_data_line():
    raw = sse.frame("delta", {"text": 'line1\nline2\r"q" ă 🙂'}).decode()
    lines = raw.split("\n")
    assert lines[0] == "event: delta"
    assert lines[1].startswith("data: ")
    assert lines[2:] == ["", ""]
    assert json.loads(lines[1][6:]) == {"text": 'line1\nline2\r"q" ă 🙂'}
    assert "ă" in lines[1]
    assert "🙂" in lines[1]


@pytest.mark.parametrize("bad", ["", "a\nb", "x:y"])
def test_bad_event_names_are_refused(bad):
    with pytest.raises(ValueError, match="bad SSE event name"):
        sse.frame(bad, {})


def test_keep_alive_is_a_comment():
    assert sse.KEEP_ALIVE.startswith(b":")
    assert sse.KEEP_ALIVE.endswith(b"\n\n")
