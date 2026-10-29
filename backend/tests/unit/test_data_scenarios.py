"""D2: data/scenarios/<id>.json, the scripted demo transactions (arch 16.2) and their expected
decisions (arch 16.3). Read by bomboe's /sim/transaction (B10) and the acceptance tests (D3).

Each file validates against data/schemas/scenario.schema.json, belongs to a persona, resolves to
its merchant through C2's alias match, and has a positive amount with exactly 2 decimals.
"""

import copy
import unicodedata
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from functools import cache
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.context.normalize import normalize
from app.domain.enums import Category, Decision, Purpose
from tests.unit.datafiles import DATA_DIR, load_data, schema_errors

SCENARIO_DIR = DATA_DIR / "scenarios"
SIM_DATE = date(2026, 6, 15)  # a Monday (arch 16.2)
BUCHAREST = ZoneInfo("Europe/Bucharest")
PERSONAS = {"matei", "andrei", "bianca", "ioana", "alex"}
# id -> (persona, decision): the arch 16.2 / 16.3 contract (work-breakdown D2's list).
EXPECTED = {
    "matei_mega_500": ("matei", Decision.ASK),
    "andrei_tv": ("andrei", Decision.INFORM),
    "bianca_tv": ("bianca", Decision.ASK),
    "bianca_tv_noitems": ("bianca", Decision.ASK),
    "matei_flight": ("matei", Decision.AUTO),
    "matei_friday_lunch": ("matei", Decision.AUTO),
    "ioana_shopgo_350": ("ioana", Decision.AUTO),
    "matei_shopgo_350": ("matei", Decision.ASK),
}
IDS = sorted(EXPECTED)


@cache
def _scenario(scenario_id: str) -> dict[str, Any]:
    data: dict[str, Any] = load_data(f"scenarios/{scenario_id}")
    return data


def scenario(scenario_id: str) -> dict[str, Any]:
    return copy.deepcopy(_scenario(scenario_id))


def occurred_at(data: dict[str, Any]) -> datetime:
    """The scenario's timestamp: day_offset days after the sim date, at time (Bucharest)."""
    day = SIM_DATE + timedelta(days=data["day_offset"])
    return datetime.combine(day, time.fromisoformat(data["time"]), tzinfo=BUCHAREST)


def _two_dp(value: Any) -> bool:
    return isinstance(value, Decimal) and value > 0 and value.as_tuple().exponent == -2


def test_the_folder_has_exactly_the_d2_scenarios() -> None:
    assert sorted(path.stem for path in SCENARIO_DIR.glob("*.json")) == IDS


@pytest.mark.parametrize("scenario_id", IDS)
def test_scenario_validates_and_is_named_by_its_id(scenario_id: str) -> None:
    data = scenario(scenario_id)
    assert schema_errors("scenario", data) == []
    assert data["id"] == scenario_id


@pytest.mark.parametrize("scenario_id", IDS)
def test_persona_and_expected_decision(scenario_id: str) -> None:
    data = scenario(scenario_id)
    assert data["persona"] in PERSONAS
    assert (data["persona"], Decision(data["expected"]["decision"])) == EXPECTED[scenario_id]
    assert Category(data["expected"]["category"])
    if "purpose" in data["expected"]:
        assert Purpose(data["expected"]["purpose"])


@pytest.mark.parametrize("scenario_id", IDS)
def test_merchant_resolves_by_alias(scenario_id: str) -> None:
    data = scenario(scenario_id)
    merchant = normalize(data["merchant_raw"], data["mcc"])
    assert merchant.merchant_id == data["expected"]["merchant_id"]
    assert merchant.category == Category(data["expected"]["category"])
    catalogue = {m["id"]: m for m in load_data("merchants")["merchants"]}
    assert data["mcc"] == catalogue[merchant.merchant_id]["mcc"]


@pytest.mark.parametrize("scenario_id", IDS)
def test_amounts_are_positive_with_two_decimals(scenario_id: str) -> None:
    data = scenario(scenario_id)
    assert _two_dp(data["amount"]), data["amount"]
    for item in data["items"] or []:
        assert "amount" not in item or _two_dp(item["amount"])
    priced = [
        item["amount"] * item.get("qty", 1) for item in data["items"] or [] if "amount" in item
    ]
    if priced and len(priced) == len(data["items"]):
        assert sum(priced) == data["amount"]


@pytest.mark.parametrize("scenario_id", IDS)
def test_text_is_nfc_with_comma_below(scenario_id: str) -> None:
    raw = (SCENARIO_DIR / f"{scenario_id}.json").read_text(encoding="utf-8")
    assert "\\u" not in raw
    assert unicodedata.normalize("NFC", raw) == raw
    assert not set(raw) & set("şţŞŢ")


def test_the_demo_script_details() -> None:
    # Scene A: Monday 13:05 (arch 16.2 / 16.3 #1); Scene D: after the jump to Friday, 13:10.
    assert occurred_at(scenario("matei_mega_500")) == datetime(2026, 6, 15, 13, 5, tzinfo=BUCHAREST)
    friday = occurred_at(scenario("matei_friday_lunch"))
    assert (friday.isoweekday(), friday.time()) == (5, time(13, 10))
    assert scenario("matei_friday_lunch")["expected"]["outcome_label"] == "Prânz cu echipa"
    # Scene B: the same purchase, different lives; without items eMAG needs "what was it?".
    andrei, bianca, noitems = (scenario(i) for i in ("andrei_tv", "bianca_tv", "bianca_tv_noitems"))
    for key in ("merchant_raw", "mcc", "amount", "items"):
        assert andrei[key] == bianca[key]
    assert andrei["items"][0]["name"] == 'Televizor 65"'
    assert andrei["expected"]["purpose"] == Purpose.WORK_TOOL
    assert noitems["items"] is None
    assert noitems["expected"]["ask_what_item"] is True
    assert scenario("matei_flight")["expected"]["purpose"] == Purpose.PLANNED_EVENT
    # Scene E: the same 350 lei at Shop&Go is normal for Ioana's family, a question for Matei.
    assert scenario("ioana_shopgo_350")["amount"] == scenario("matei_shopgo_350")["amount"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount", Decimal("0.00")),
        ("amount", Decimal("-5.00")),
        ("amount", Decimal("1.001")),
        ("persona", "bob"),
        ("time", "24:00"),
        ("mcc", "541"),
        ("day_offset", -1),
        ("items", []),
    ],
)
def test_schema_rejects(field: str, value: Any) -> None:
    data = scenario("matei_mega_500")
    data[field] = value
    assert schema_errors("scenario", data) != []


def test_schema_accepts_the_boundaries() -> None:
    data = scenario("matei_mega_500")
    data.update(amount=Decimal("0.01"), time="23:59", day_offset=0, items=None)
    assert schema_errors("scenario", data) == []
    data.update(time="00:00", amount=Decimal("1"))
    assert schema_errors("scenario", data) == []
