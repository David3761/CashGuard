"""C11: calendar expected events (arch 5.3.3, 5.3.9; WB C11) and their life_fit source."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.agent.style import find_banned
from app.context.calendar_events import (
    covered,
    event_signatures,
    expected_events,
    load_calendar,
    orthodox_easter,
    parse_calendar,
)
from app.context.library import library_signatures
from app.context.life_fit import FIT_TEMPLATES, explain, life_fit
from app.domain.enums import Category, FactType, Purpose, SignatureEffect, SignatureOrigin
from app.domain.models import TxView
from app.domain.user_context import UserContext
from tests.builders import at, ctx, fact, ioana_ctx, signature

_ids = iter(range(5000, 90000))


def buy(
    day: date, category: str, amount: str, merchant_raw: str = "NORIEL", **extra: Any
) -> TxView:
    return TxView.model_validate(
        {
            "id": next(_ids),
            "occurred_at": at(day, 17),
            "merchant_raw": merchant_raw,
            "category": category,
            "direction": "debit",
            "amount": amount,
            "effective_amount": amount,
            **extra,
        }
    )


def ids(events: list[Any]) -> list[str]:
    return [e.id for e in events]


def with_child(age: int | None, fact_id: int = 40) -> UserContext:
    value: dict[str, Any] = {"role": "child", "relation": "son"}
    if age is not None:
        value["age"] = age
        return ctx(facts=[fact(FactType.HOUSEHOLD_MEMBER, id=fact_id, value=value)])
    return ctx(facts=[fact(FactType.HOUSEHOLD_MEMBER, id=fact_id, value={"role": "adult"})])


# ── the calendar ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("year", "easter"),
    [
        (2024, date(2024, 5, 5)),
        (2025, date(2025, 4, 20)),
        (2026, date(2026, 4, 12)),
        (2023, date(2023, 4, 16)),
        (2027, date(2027, 5, 2)),
    ],
)
def test_orthodox_easter_by_the_meeus_julian_algorithm(year: int, easter: date) -> None:
    assert orthodox_easter(year) == easter


def test_orthodox_easter_outside_the_julian_offset_range_fails() -> None:
    with pytest.raises(ValueError, match="1900-2099"):
        orthodox_easter(2100)


def test_fixed_and_configurable_dates_come_from_calendar_json() -> None:
    by_id = {e.id: e for e in load_calendar()}
    assert by_id["christmas"].dates_in(2026) == [date(2026, 12, 25)]
    assert by_id["womens_day"].dates_in(2027) == [date(2027, 3, 8)]
    assert by_id["childrens_day"].dates_in(2026) == [date(2026, 6, 1)]
    assert by_id["orthodox_easter"].dates_in(2026) == [date(2026, 4, 12)]
    assert by_id["school_start"].dates_in(2026) == [date(2026, 9, 7)]
    assert by_id["black_friday"].dates_in(2026) == [date(2026, 11, 13)]
    assert by_id["school_start"].dates_in(2027) == []  # not configured yet
    assert by_id["childrens_day"].child_ages == (0, 13)
    assert by_id["school_start"].child_ages == (6, 18)
    assert by_id["christmas"].lead_days == 21


def test_a_configured_date_is_read_from_the_data() -> None:
    entries = parse_calendar(
        {
            "configurable": [
                {
                    "id": "school_start",
                    "dates": ["2027-09-13"],
                    "categories": ["books"],
                    "name": {"ro": "Școala", "en": "School"},
                    "lead_days": 30,
                    "requires_child_age": [6, 18],
                },
            ]
        }
    )
    events = expected_events(with_child(8), date(2027, 9, 1), entries=entries)
    assert [(e.id, e.day) for e in events] == [("school_start", date(2027, 9, 13))]


# ── relevance ────────────────────────────────────────────────────────────────────────────────


def test_childrens_day_and_school_only_with_kids() -> None:
    no_kids = ctx()
    assert "childrens_day" not in ids(expected_events(no_kids, date(2026, 5, 20)))
    assert "school_start" not in ids(expected_events(no_kids, date(2026, 8, 20)))
    assert "childrens_day" in ids(expected_events(ioana_ctx(), date(2026, 5, 20)))
    assert "school_start" in ids(expected_events(ioana_ctx(), date(2026, 8, 20)))


@pytest.mark.parametrize(
    ("age", "childrens_day", "school"),
    [(4, True, False), (6, True, True), (13, True, True), (14, False, True), (18, False, True),
     (19, False, False)],
)  # fmt: skip
def test_the_child_ages_come_from_calendar_json(
    age: int, childrens_day: bool, school: bool
) -> None:
    child = with_child(age)
    assert ("childrens_day" in ids(expected_events(child, date(2026, 5, 20)))) is childrens_day
    assert ("school_start" in ids(expected_events(child, date(2026, 8, 20)))) is school


def test_a_child_without_an_age_or_an_adult_makes_no_child_event() -> None:
    adult = with_child(None)
    assert ids(expected_events(adult, date(2026, 5, 20))) == []


def test_the_event_points_at_the_first_matching_child_fact() -> None:
    [june] = [e for e in expected_events(ioana_ctx(), date(2026, 5, 20)) if e.id == "childrens_day"]
    assert june.fact_id == 33  # the 7-year-old; the 11-year-old (34) doesn't add a second one
    assert june.starts == date(2026, 5, 29)


def test_holidays_are_for_everyone_inside_the_window() -> None:
    assert ids(expected_events(ctx(), date(2026, 12, 1))) == ["christmas"]
    assert ids(expected_events(ctx(), date(2026, 3, 30))) == ["orthodox_easter"]
    assert ids(expected_events(ctx(), date(2026, 11, 1), days_ahead=20)) == ["black_friday"]
    assert ids(expected_events(ctx(), date(2026, 12, 26), days_ahead=30)) == []
    year_end = expected_events(ctx(), date(2026, 12, 20), days_ahead=90)
    assert [(e.id, e.day) for e in year_end] == [
        ("christmas", date(2026, 12, 25)),
        ("womens_day", date(2027, 3, 8)),
    ]


# ── signatures, without double counting ──────────────────────────────────────────────────────


def test_school_start_skips_the_category_the_library_already_covers() -> None:
    ioana = ioana_ctx()  # has the library's school-supplies signature: books in Aug-Sep
    assert covered(ioana.signatures, Category.BOOKS, 9)
    sigs = event_signatures(ioana, date(2026, 8, 20))
    school = [s for s in sigs if s.expected_date == date(2026, 9, 7)]
    assert {s.category for s in school} == {Category.KIDS, Category.CLOTHING}  # not books
    for s in school:
        assert s.effect is SignatureEffect.EXPECTS_EVENT
        assert s.origin is SignatureOrigin.LIBRARY
        assert s.fact_id == 33
        assert s.purpose is Purpose.HOUSEHOLD_CARE


def test_the_real_library_signatures_of_a_child_win_over_the_calendar() -> None:
    child = fact(FactType.HOUSEHOLD_MEMBER, id=40, value={"role": "child", "age": 8})
    library = [s.replace(id=i) for i, s in enumerate(library_signatures(child), start=1)]
    kid = ctx(facts=[child], signatures=library)
    june = [
        s for s in event_signatures(kid, date(2026, 5, 20)) if s.expected_date == date(2026, 6, 1)
    ]
    assert {s.category for s in june} == {Category.GIFTS}  # kids in June is the library's
    school = [
        s for s in event_signatures(kid, date(2026, 8, 20)) if s.expected_date == date(2026, 9, 7)
    ]
    assert {s.category for s in school} == {Category.KIDS, Category.CLOTHING}


def test_christmas_signatures_use_the_usual_basket_and_black_friday_explains_nothing() -> None:
    sigs = event_signatures(ioana_ctx(), date(2026, 12, 1))
    by_category = {s.category: s for s in sigs}
    assert set(by_category) == {Category.GIFTS, Category.GROCERIES}
    assert by_category[Category.GROCERIES].expected_amount == Decimal("280.00")  # 2 x 140
    assert by_category[Category.GIFTS].expected_amount == Decimal("200.00")  # 2 x the prior 100
    assert by_category[Category.GIFTS].purpose is Purpose.SOCIAL_CONNECTION
    assert by_category[Category.GIFTS].fact_id is None
    assert event_signatures(ctx(), date(2026, 11, 1), days_ahead=20) == []  # Black Friday


# ── the life_fit source ──────────────────────────────────────────────────────────────────────


def test_a_toy_before_1_iunie_is_explained_for_a_parent_only() -> None:
    toy = buy(date(2026, 5, 30), "kids", "180", merchant_id="noriel", merchant="Noriel")
    fit = life_fit(toy, ioana_ctx())
    assert fit.source == "expects_event"
    assert fit.explanation_key == "fit.calendar"
    assert fit.fact_id == 33
    assert fit.score == pytest.approx(0.6 * 0.95)
    assert explain(fit, "ro") == "Pentru cei dragi: o cheltuială așteptată de 1 Iunie."
    assert explain(fit, "en") == "For your loved ones: an expected expense for Children's Day."
    assert life_fit(toy, ctx()).source == "none"


def test_the_library_signature_explains_it_once_not_the_calendar_too() -> None:
    child = fact(FactType.HOUSEHOLD_MEMBER, id=40, value={"role": "child", "age": 8})
    library = [s.replace(id=i) for i, s in enumerate(library_signatures(child), start=1)]
    toy = buy(date(2026, 5, 30), "kids", "150", merchant_id="noriel", merchant="Noriel")
    fit = life_fit(toy, ctx(facts=[child], signatures=library))
    assert fit.source in ("signature", "expects_event")  # C5's path, from the library entries
    assert fit.explanation_key != "fit.calendar"
    assert fit.fact_id == 40


def test_christmas_gifts_only_inside_the_lead_window() -> None:
    def fit_on(day: date) -> str | None:
        return life_fit(buy(day, "gifts", "150", "FLORARIA BUJOR"), ctx()).explanation_key

    assert fit_on(date(2026, 12, 3)) is None
    assert fit_on(date(2026, 12, 4)) == "fit.calendar"  # 21 days before
    assert fit_on(date(2026, 12, 25)) == "fit.calendar"
    assert fit_on(date(2026, 12, 26)) is None


def test_the_fit_decays_with_the_amount() -> None:
    christmas = date(2026, 12, 20)
    usual = life_fit(buy(christmas, "gifts", "300", "FLORARIA"), ctx())
    big = life_fit(buy(christmas, "gifts", "450", "FLORARIA"), ctx())
    huge = life_fit(buy(christmas, "gifts", "600", "FLORARIA"), ctx())
    assert usual.score == pytest.approx(0.6)
    assert big.score == pytest.approx(0.3)
    assert huge.source == "none"


def test_black_friday_and_a_credit_are_never_a_calendar_fit() -> None:
    tv = buy(date(2026, 11, 13), "electronics", "2500", "EMAG", merchant_id="emag")
    assert life_fit(tv, ctx()).source == "none"
    refund = buy(date(2026, 12, 20), "gifts", "150", "FLORARIA", direction="credit")
    assert life_fit(refund, ctx()).source == "none"


def test_a_stronger_signature_still_wins_over_the_calendar() -> None:
    present = buy(date(2026, 12, 20), "gifts", "150", "FLORARIA")
    strong = signature(
        fact_id=1,
        effect="explains",
        category="gifts",
        merchant_hints=["Floraria"],
        item_keywords=[],
        amount_min=None,
        amount_max=None,
        replacement_cycle_days=None,
        purpose="social_connection",
        strength=1.0,
    )
    fit = life_fit(present, ctx(facts=[fact(FactType.SOCIAL_PATTERN)], signatures=[strong]))
    assert fit.explanation_key == "fit.signature"


def test_the_calendar_template_is_clean() -> None:
    ro, en = FIT_TEMPLATES["fit.calendar"]
    assert find_banned(ro, "ro") == []
    assert find_banned(en, "en") == []
