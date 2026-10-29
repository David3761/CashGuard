"""C1.5: data/calendar.json, Romanian calendar events for expected spending (C11, G-07)."""

from datetime import date
from typing import Any

from app.domain.enums import Category
from tests.unit.datafiles import load_data, load_schema, schema_errors


def _calendar() -> dict[str, Any]:
    calendar: dict[str, Any] = load_data("calendar")
    return calendar


def _events() -> list[dict[str, Any]]:
    c = _calendar()
    return [*c["fixed"], *c["computed"], *c["configurable"]]


def test_calendar_file_validates_against_its_schema() -> None:
    assert schema_errors("calendar", _calendar()) == []


def test_the_schema_categories_are_f2_s() -> None:
    enum = load_schema("calendar")["$defs"]["common"]["properties"]["categories"]["items"]["enum"]

    assert sorted(enum) == sorted(category.value for category in Category)


def test_the_events_c11_needs() -> None:
    fixed = {e["id"]: (e["month"], e["day"]) for e in _calendar()["fixed"]}

    assert fixed == {"womens_day": (3, 8), "childrens_day": (6, 1), "christmas": (12, 25)}
    assert [e["rule"] for e in _calendar()["computed"]] == ["orthodox_easter"]
    assert {e["id"] for e in _calendar()["configurable"]} == {"school_start", "black_friday"}


def test_fixed_dates_are_real_dates() -> None:
    for event in _calendar()["fixed"]:
        date(2028, event["month"], event["day"])  # a leap year: 02-29 would pass, 02-30 not


def test_configurable_dates_fall_on_their_weekday_and_month() -> None:
    dates = {
        e["id"]: [date.fromisoformat(d) for d in e["dates"]] for e in _calendar()["configurable"]
    }

    assert all(d.month == 11 and d.weekday() == 4 for d in dates["black_friday"])  # a Friday
    assert all(d.month == 9 and d.weekday() == 0 for d in dates["school_start"])  # a Monday


def test_children_only_events_and_romanian_names() -> None:
    by_id = {e["id"]: e for e in _events()}

    assert by_id["childrens_day"]["requires_child_age"] == [0, 13]  # 1 Iunie: under 14 (C4)
    assert by_id["school_start"]["requires_child_age"] == [6, 18]
    assert "requires_child_age" not in by_id["christmas"]
    assert by_id["christmas"]["name"]["ro"] == "Crăciun"
    assert by_id["school_start"]["name"]["ro"] == "Începutul școlii"
    assert len(by_id) == len(_events())  # ids unique


def test_the_schema_rejects_a_bad_date_and_month() -> None:
    bad_date = {**_calendar()["configurable"][0], "dates": ["2026-02-30"]}
    bad_month = {**_calendar()["fixed"][0], "month": 13}

    assert schema_errors("calendar", {**_calendar(), "configurable": [bad_date]})
    assert schema_errors("calendar", {**_calendar(), "fixed": [bad_month]})
