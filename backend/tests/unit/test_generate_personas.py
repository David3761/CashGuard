"""E12: the persona data generator (scripts/generate_personas.py) and the files it produces."""

import importlib.util
import json
import shutil
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import median
from types import ModuleType
from typing import Any
from zoneinfo import ZoneInfo

import pytest

BACKEND = Path(__file__).resolve().parents[2]
PERSONAS = BACKEND / "data" / "personas"
BUCHAREST = ZoneInfo("Europe/Bucharest")


def load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "generate_personas", BACKEND / "scripts" / "generate_personas.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = load_generator()


def generated(pid: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    config = json.loads((PERSONAS / pid / "config.json").read_text(encoding="utf-8"))
    profile, transactions = gen.generate(config)
    return profile, transactions


def when(t: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(t["occurred_at"]).astimezone(BUCHAREST)


def stream(transactions: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [t for t in transactions if t["stream"] == name]


ALL = ["matei", "andrei", "bianca", "ioana", "alex"]


# ── determinism and files ────────────────────────────────────────────────────


def test_running_twice_gives_byte_identical_files(tmp_path: Path) -> None:
    outputs = []
    for run in ("a", "b"):
        folder = tmp_path / run / "matei"
        folder.mkdir(parents=True)
        shutil.copy(PERSONAS / "matei" / "config.json", folder / "config.json")
        gen.write_persona(folder)
        outputs.append(((folder / "profile.json").read_bytes(), (folder / "transactions.json").read_bytes()))
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize("pid", ALL)
def test_committed_files_match_the_generator(pid: str) -> None:
    profile, transactions = generated(pid)
    assert (PERSONAS / pid / "profile.json").read_text(encoding="utf-8") == gen.dump(profile)
    assert (PERSONAS / pid / "transactions.json").read_text(encoding="utf-8") == gen.dump(transactions)


# ── every persona ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("pid", ALL)
def test_history_stays_inside_the_window(pid: str) -> None:
    _, txs = generated(pid)
    days = [when(t).date() for t in txs]
    assert min(days) >= date(2026, 2, 15)
    assert max(days) <= date(2026, 6, 14)  # nothing after 2026-06-14 23:59 Bucharest


@pytest.mark.parametrize("pid", ALL)
def test_start_balance_plus_history_ends_on_the_current_balance(pid: str) -> None:
    profile, txs = generated(pid)
    net = sum((Decimal(t["amount"]) * (1 if t["direction"] == "credit" else -1) for t in txs), Decimal(0))
    assert Decimal(profile["history"]["start_balance"]) + net == Decimal(
        profile["account"]["current_balance"]
    )
    assert Decimal(profile["history"]["start_balance"]) > 0


@pytest.mark.parametrize("pid", ALL)
def test_amounts_are_positive_with_two_decimals(pid: str) -> None:
    _, txs = generated(pid)
    for t in txs:
        amount = Decimal(t["amount"])
        assert amount > 0 and amount == amount.quantize(Decimal("0.01"))


@pytest.mark.parametrize("pid", ALL)
def test_receipt_items_are_well_formed(pid: str) -> None:
    _, txs = generated(pid)
    for t in txs:
        if t["items"]:
            assert sum(Decimal(i["amount"]) for i in t["items"]) == Decimal(t["amount"])
            assert all(i["qty"] >= 1 and i["name"] for i in t["items"])


@pytest.mark.parametrize("pid", ["matei", "andrei", "ioana"])
def test_salary_and_rent_land_on_their_day_every_month(pid: str) -> None:
    profile, txs = generated(pid)
    salary_day = profile["income_sources"][0]["day_of_month"]
    rent = profile["fixed_costs"][0]
    for month in (3, 4, 5):
        salary = [t for t in stream(txs, "salary") if when(t).month == month]
        rents = [t for t in stream(txs, f"fixed:{rent['name']}") if when(t).month == month]
        assert [when(t).day for t in salary] == [salary_day]
        assert [when(t).day for t in rents] == [rent["day_of_month"]]
        assert [Decimal(t["amount"]) for t in rents] == [Decimal(rent["amount"])]


# ── persona patterns (arch 16.1) ─────────────────────────────────────────────


def full_weeks() -> list[date]:
    first = date(2026, 2, 16)  # the first Monday inside the window
    return [first + timedelta(weeks=i) for i in range(17)]  # last full week: 8–14 Jun


def test_matei_mega_image_three_or_four_weekday_lunches_each_week() -> None:
    _, txs = generated("matei")
    mega = stream(txs, "mega_lunch")
    per_week = Counter(when(t).date() - timedelta(when(t).weekday()) for t in mega)
    assert all(3 <= per_week[monday] <= 4 for monday in full_weeks())
    assert all(when(t).isoweekday() <= 5 and 12 <= when(t).hour < 14 for t in mega)


def test_matei_mega_image_median_basket_is_85() -> None:
    _, txs = generated("matei")
    assert abs(median(Decimal(t["amount"]) for t in stream(txs, "mega_lunch")) - 85) <= 8


def test_matei_team_lunch_every_friday_60_to_110() -> None:
    _, txs = generated("matei")
    lunches = stream(txs, "friday_lunch")
    fridays = {d + timedelta(4) for d in full_weeks()}
    assert {when(t).date() for t in lunches} >= fridays
    assert all(60 <= Decimal(t["amount"]) <= 110 and 12 <= when(t).hour < 15 for t in lunches)


def test_matei_last_two_team_lunches_were_answered() -> None:
    _, txs = generated("matei")
    answered = [t for t in txs if t["annotation"] and t["annotation"]["source"] == "answer"]
    assert len(answered) == 2
    assert {t["annotation"]["label"] for t in answered} == {"Prânz cu echipa"}
    assert answered == stream(txs, "friday_lunch")[-2:]


def test_matei_eighth_of_march_flowers() -> None:
    _, txs = generated("matei")
    assert any(t["category"] == "gifts" and when(t).date() == date(2026, 3, 7) for t in txs)


def test_ioana_shop_and_go_median_basket_is_140() -> None:
    _, txs = generated("ioana")
    normal = [t for t in stream(txs, "shopgo") if not date(2026, 4, 6) <= when(t).date() <= date(2026, 4, 11)]
    assert abs(median(Decimal(t["amount"]) for t in normal) - 140) <= 15


def test_ioana_easter_week_is_well_above_an_average_week() -> None:
    _, txs = generated("ioana")
    spending = [t for t in txs if t["direction"] == "debit" and t["category"] in ("groceries", "gifts")]
    weekly: dict[date, Decimal] = {}
    for t in spending:
        monday = when(t).date() - timedelta(when(t).weekday())
        weekly[monday] = weekly.get(monday, Decimal(0)) + Decimal(t["amount"])
    easter = weekly[date(2026, 4, 6)]
    average = sum((weekly.get(w, Decimal(0)) for w in full_weeks()), Decimal(0)) / len(full_weeks())
    assert easter > Decimal("1.5") * average


def test_ioana_children_day_gifts() -> None:
    _, txs = generated("ioana")
    assert any(
        t["category"] == "gifts" and date(2026, 5, 29) <= when(t).date() <= date(2026, 6, 1) for t in txs
    )


def test_bianca_income_is_irregular() -> None:
    _, txs = generated("bianca")
    credits = [t for t in txs if t["direction"] == "credit"]
    assert len({when(t).day for t in credits}) > 6  # no fixed payday
    assert len({Decimal(t["amount"]) for t in credits}) == len(credits)


def test_andrei_has_two_sports_streaming_subscriptions_and_football() -> None:
    profile, txs = generated("andrei")
    subscriptions = [f for f in profile["fixed_costs"] if f["name"] in ("DAZN", "Voyo Sport")]
    assert len(subscriptions) == 2
    assert len(stream(txs, "football")) >= 4


def test_andrei_saw_electronics_but_never_emag_and_bianca_never_electronics() -> None:
    # arch 5.3.4 table: Andrei's eMAG TV is half novel (category seen), Bianca's fully novel
    _, andrei = generated("andrei")
    _, bianca = generated("bianca")
    assert any(t["category"] == "electronics" for t in andrei)
    assert not any("EMAG" in t["merchant_raw"] for t in andrei)
    assert not any(t["category"] == "electronics" for t in bianca)


# ── waiting for teammates ────────────────────────────────────────────────────


def test_every_merchant_raw_resolves_with_normalize() -> None:
    normalize = pytest.importorskip("app.context.normalize", reason="needs C2 normalize (David G.)").normalize
    for pid in ALL:
        _, txs = generated(pid)
        for t in txs:
            if t["direction"] == "debit" and t["category"] not in ("housing_rent", "savings"):
                _, _, category = normalize(t["merchant_raw"], t["mcc"], t["category"])
                assert category == t["category"]


def test_every_transaction_validates_as_a_domain_object() -> None:
    models = pytest.importorskip("app.domain.models", reason="needs F2 app.domain (David G.)")
    from app.domain.enums import Category

    for pid in ALL:
        _, txs = generated(pid)
        for t in txs:
            Category(t["category"])
            assert models.TxView is not None
