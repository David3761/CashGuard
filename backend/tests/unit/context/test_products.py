"""C12: the mock savings products ranked for the person (arch 6.6, 16.5; WB C12)."""

import json
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.agent.style import find_banned
from app.config import BACKEND_DIR
from app.context.products import (
    REASONS,
    ProductNeeds,
    as_offer,
    months_between,
    months_phrase,
    needs_for,
    rank_offers,
    rank_products,
)
from app.domain.enums import FactType, Language, ProductKind
from app.domain.user_context import UserContext
from tests.builders import (
    TODAY,
    _goal,
    bianca_ctx,
    ctx,
    fact,
    ioana_ctx,
    matei_ctx,
)

PRODUCTS: list[dict[str, Any]] = json.loads(
    (BACKEND_DIR / "data" / "products.json").read_text("utf-8"), parse_float=Decimal
)["products"]
STABLE = [{"id": 1, "source": "Salariu", "amount": "7000", "day_of_month": 10}]


def kinds(ranked: list[Any]) -> list[ProductKind]:
    return [r.product.kind for r in ranked]


def with_goal(deadline: date, **overrides: Any) -> UserContext:
    return ctx(**_goal(9, "8000", deadline, "1000"), **overrides)


def needs(months: int | None, *, stable: bool = True, irregular: bool = False) -> ProductNeeds:
    return ProductNeeds(
        horizon_months=months,
        set_amount=months is not None,
        stable_income=stable,
        irregular_income=irregular,
    )


# ── the personas ─────────────────────────────────────────────────────────────────────────────


def test_matei_six_months_steady_salary_gets_the_term_deposit_first() -> None:
    ranked = rank_products(matei_ctx(), PRODUCTS, TODAY)  # 15 Jun → 31 Dec: 6 months
    assert kinds(ranked) == [
        ProductKind.TERM_DEPOSIT,
        ProductKind.SAVINGS_ACCOUNT,
        ProductKind.FLEXIBLE_POT,
    ]
    assert ranked[0].reason_key == "top.locked_fits"
    assert ranked[0].params["months"] == 6
    assert "venit stabil" in ranked[0].why(Language.RO)
    assert "5,5%" in ranked[0].why(Language.RO)
    assert "5.5%" in ranked[0].why(Language.EN)


def test_bianca_irregular_income_gets_liquidity_first() -> None:
    ranked = rank_products(bianca_ctx(), PRODUCTS, TODAY)
    assert kinds(ranked) == [
        ProductKind.FLEXIBLE_POT,
        ProductKind.SAVINGS_ACCOUNT,
        ProductKind.TERM_DEPOSIT,
    ]
    assert ranked[0].reason_key == "top.irregular_income"
    assert "variază" in ranked[0].why(Language.RO)
    assert ranked[-1].score < ranked[0].score


def test_bianca_irregular_income_wins_even_with_a_long_horizon() -> None:
    long = bianca_ctx().model_copy(update=_goal(3, "3000", date(2027, 6, 30), "900"))
    ranked = rank_products(long, PRODUCTS, TODAY)
    assert kinds(ranked)[0] is ProductKind.FLEXIBLE_POT
    assert ranked[0].reason_key == "top.irregular_income"
    assert ranked[-1].product.kind is ProductKind.TERM_DEPOSIT
    assert ranked[-1].reason_key == "alt.locked_irregular"


def test_ioana_steady_household_income_gets_the_term_deposit_first() -> None:
    ranked = rank_products(ioana_ctx(), PRODUCTS, TODAY)
    assert kinds(ranked)[0] is ProductKind.TERM_DEPOSIT
    assert ranked[1].product.kind is ProductKind.SAVINGS_ACCOUNT


def test_a_freelancer_counts_as_irregular_income() -> None:
    freelancer = with_goal(
        date(2027, 6, 15),
        income_sources=STABLE,
        facts=[fact(FactType.EMPLOYMENT, value={"kind": "freelancer"})],
    )
    assert needs_for(freelancer, TODAY).irregular_income
    assert kinds(rank_products(freelancer, PRODUCTS, TODAY))[0] is ProductKind.FLEXIBLE_POT


# ── the horizon boundaries ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("deadline", "months"),
    [
        (date(2026, 6, 15), 0),
        (date(2026, 7, 14), 0),
        (date(2026, 7, 15), 1),
        (date(2026, 9, 14), 2),
        (date(2026, 9, 15), 3),
        (date(2026, 12, 14), 5),
        (date(2026, 12, 15), 6),
        (date(2027, 6, 15), 12),
        (date(2026, 5, 1), 0),  # already past
    ],
)
def test_months_between_counts_whole_calendar_months(deadline: date, months: int) -> None:
    assert months_between(TODAY, deadline) == months


@pytest.mark.parametrize(
    ("deadline", "top", "key"),
    [
        (date(2026, 7, 1), ProductKind.FLEXIBLE_POT, "top.short_horizon"),  # 0 months
        (date(2026, 9, 14), ProductKind.FLEXIBLE_POT, "top.short_horizon"),  # 2 months
        (date(2026, 9, 15), ProductKind.SAVINGS_ACCOUNT, "top.medium_horizon"),  # 3 months
        (date(2026, 12, 14), ProductKind.SAVINGS_ACCOUNT, "top.medium_horizon"),  # 5 months
        (date(2026, 12, 15), ProductKind.TERM_DEPOSIT, "top.locked_fits"),  # 6 months
        (date(2027, 6, 15), ProductKind.TERM_DEPOSIT, "top.locked_fits"),  # 12 months
        (date(2028, 6, 15), ProductKind.TERM_DEPOSIT, "top.locked_fits"),  # 24 months
    ],
)
def test_the_horizon_picks_the_top_product(deadline: date, top: ProductKind, key: str) -> None:
    ranked = rank_products(with_goal(deadline, income_sources=STABLE), PRODUCTS, TODAY)
    assert ranked[0].product.kind is top
    assert ranked[0].reason_key == key
    assert ranked[0].fits


def test_short_horizon_orders_the_rest_by_liquidity() -> None:
    ranked = rank_products(with_goal(date(2026, 8, 1), income_sources=STABLE), PRODUCTS, TODAY)
    assert kinds(ranked) == [
        ProductKind.FLEXIBLE_POT,
        ProductKind.SAVINGS_ACCOUNT,
        ProductKind.TERM_DEPOSIT,
    ]
    assert [r.reason_key for r in ranked[1:]] == ["alt.too_long", "alt.too_long"]
    assert not ranked[2].fits


def test_three_to_five_months_never_puts_the_deposit_above_the_account() -> None:
    ranked = rank_products(with_goal(date(2026, 10, 20), income_sources=STABLE), PRODUCTS, TODAY)
    assert kinds(ranked) == [
        ProductKind.SAVINGS_ACCOUNT,
        ProductKind.FLEXIBLE_POT,
        ProductKind.TERM_DEPOSIT,
    ]
    assert ranked[2].reason_key == "alt.too_long"


def test_six_months_without_a_known_income_keeps_the_money_unlocked() -> None:
    ranked = rank_products(with_goal(date(2027, 1, 15)), PRODUCTS, TODAY)  # no income source
    assert ranked[0].product.kind is ProductKind.SAVINGS_ACCOUNT
    assert ranked[0].reason_key == "top.no_steady_income"
    assert ranked[-1].reason_key == "alt.no_steady_income"


def test_an_explicit_regular_income_fact_counts_as_steady() -> None:
    regular = with_goal(
        date(2027, 1, 15), facts=[fact(FactType.INCOME_PATTERN, value={"irregular": False})]
    )
    assert rank_products(regular, PRODUCTS, TODAY)[0].product.kind is ProductKind.TERM_DEPOSIT


def test_no_goal_yet_keeps_every_option_open() -> None:
    ranked = rank_products(ctx(income_sources=STABLE), PRODUCTS, TODAY)
    assert ranked[0].product.kind is ProductKind.FLEXIBLE_POT
    assert ranked[0].reason_key == "top.no_horizon"
    assert ranked[-1].reason_key == "alt.locked_no_goal"
    assert "months" not in ranked[0].params


def test_the_deposit_is_skipped_when_no_deposit_product_exists() -> None:
    no_deposit = [p for p in PRODUCTS if p["kind"] != "term_deposit"]
    ranked = rank_offers(needs(12), no_deposit)
    assert kinds(ranked) == [ProductKind.SAVINGS_ACCOUNT, ProductKind.FLEXIBLE_POT]


# ── the output ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("months", [None, 0, 1, 2, 3, 6, 12, 20, 30])
@pytest.mark.parametrize(("stable", "irregular"), [(True, False), (False, False), (False, True)])
def test_every_product_is_mock_with_a_clean_reason_in_both_languages(
    months: int | None, stable: bool, irregular: bool
) -> None:
    rows = [{**p, "mock": False} for p in PRODUCTS]  # whatever a row says
    ranked = rank_offers(needs(months, stable=stable, irregular=irregular), rows)
    assert len(ranked) == 3
    for item in ranked:
        assert item.mock is True
        assert set(item.why_for_you) == {Language.RO, Language.EN}
        for lang, text in item.why_for_you.items():
            assert text
            assert "{" not in text
            assert find_banned(text, lang.value) == []
    assert [r.score for r in ranked] == sorted((r.score for r in ranked), reverse=True)


def test_every_reason_template_is_clean() -> None:
    for ro, en in REASONS.values():
        assert find_banned(ro, "ro") == []
        assert find_banned(en, "en") == []


def test_month_phrases_follow_romanian_grammar() -> None:
    assert [months_phrase(n, Language.RO) for n in (0, 1, 2, 19, 20, 24)] == [
        "sub o lună",
        "o lună",
        "2 luni",
        "19 luni",
        "20 de luni",
        "24 de luni",
    ]
    assert [months_phrase(n, Language.EN) for n in (0, 1, 6)] == [
        "less than a month",
        "1 month",
        "6 months",
    ]


def test_a_row_without_kind_gets_it_from_its_liquidity() -> None:
    offer = as_offer({"id": "depo", "liquidity": "locked", "rate": 0.055, "min_months": 6})
    assert offer.kind is ProductKind.TERM_DEPOSIT
    assert offer.name == "depo"
    assert offer.rate == Decimal("0.055")
