import math
from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

pytest.importorskip("app.domain", reason="needs F2 app.domain (David G.)")

from app.engine.anomaly import materiality, novelty, robust_z, stat_score

D = Decimal
TODAY = date(2026, 6, 15)

money = st.decimals(min_value=0, max_value=100_000, places=2, allow_nan=False, allow_infinity=False)
any_money = st.decimals(
    min_value=-100_000, max_value=100_000, places=2, allow_nan=False, allow_infinity=False
)
last_seen = st.one_of(
    st.none(), st.integers(min_value=0, max_value=400).map(lambda n: TODAY - timedelta(days=n))
)


# ── Matei's worked example (arch 5.3.4: Mega Image 500, median basket 85) ────


def test_matei_mega_500_worked_example() -> None:
    z = robust_z(D("500"), expected_median=D("85"), mad=D("25"))
    assert z == pytest.approx(11.196, abs=0.001)
    assert stat_score(z) == 1.0
    # Mega Image near the office, visited every week
    assert novelty(TODAY - timedelta(days=3), TODAY - timedelta(days=1), TODAY) == 0.0
    assert materiality(D("500"), D("4385")) == 1.0


# ── robust_z ─────────────────────────────────────────────────────────────────


def test_robust_z_uses_scaled_mad() -> None:
    # 1.4826 · 10 = 14.826 → one "standard deviation" above the median
    assert robust_z(D("114.826"), D("100"), D("10")) == pytest.approx(1.0)


def test_robust_z_below_median_is_negative() -> None:
    assert robust_z(D("40"), D("85"), D("25")) < 0


def test_robust_z_at_median_is_zero() -> None:
    assert robust_z(D("85"), D("85"), D("25")) == 0.0


def test_robust_z_mad_zero_falls_back_to_quarter_of_median() -> None:
    # MAD 0 → 0.25 · 80 = 20 → z = (120 − 80) / (1.4826 · 20)
    assert robust_z(D("120"), D("80"), D("0")) == pytest.approx(40 / (1.4826 * 20))


def test_robust_z_median_and_mad_zero_with_spending_is_infinite() -> None:
    # no scale at all: any positive amount is "infinitely" unusual → stat 1
    z = robust_z(D("50"), D("0"), D("0"))
    assert z == math.inf
    assert stat_score(z) == 1.0


def test_robust_z_median_and_mad_zero_with_zero_amount_is_zero() -> None:
    assert robust_z(D("0"), D("0"), D("0")) == 0.0


@pytest.mark.parametrize(
    ("amount", "median", "mad"),
    [(D("-1"), D("85"), D("25")), (D("10"), D("-1"), D("25")), (D("10"), D("85"), D("-0.01"))],
)
def test_robust_z_rejects_negative_inputs(amount: Decimal, median: Decimal, mad: Decimal) -> None:
    with pytest.raises(ValueError):
        robust_z(amount, median, mad)


# ── stat_score = clip(z / 4, 0, 1) ───────────────────────────────────────────


@pytest.mark.parametrize(
    ("z", "expected"),
    [(-3.0, 0.0), (0.0, 0.0), (2.0, 0.5), (3.99, 0.9975), (4.0, 1.0), (4.01, 1.0), (math.inf, 1.0)],
)
def test_stat_score_clips_z_over_four(z: float, expected: float) -> None:
    assert stat_score(z) == pytest.approx(expected)


def test_stat_score_rejects_nan() -> None:
    with pytest.raises(ValueError):
        stat_score(math.nan)


# ── novelty: "seen" = within the last 90 days, bound inclusive ───────────────


def test_novelty_both_unseen_is_one() -> None:
    assert novelty(None, None, TODAY) == 1.0


def test_novelty_only_merchant_unseen_is_half() -> None:
    # Andrei's first eMAG purchase, but he buys electronics elsewhere
    assert novelty(None, TODAY - timedelta(days=20), TODAY) == 0.5


def test_novelty_merchant_seen_is_zero() -> None:
    assert novelty(TODAY - timedelta(days=20), TODAY - timedelta(days=20), TODAY) == 0.0


def test_novelty_merchant_seen_but_category_unseen_is_zero() -> None:
    # multi-category merchant (eMAG electronics, now books): only "merchant unseen" gives 0.5
    assert novelty(TODAY - timedelta(days=20), None, TODAY) == 0.0


@pytest.mark.parametrize(("days_ago", "expected"), [(89, 0.0), (90, 0.0), (91, 1.0)])
def test_novelty_ninety_day_bound_is_inclusive(days_ago: int, expected: float) -> None:
    seen = TODAY - timedelta(days=days_ago)
    assert novelty(seen, seen, TODAY) == expected


def test_novelty_ninety_one_days_counts_as_unseen_for_merchant_only() -> None:
    assert novelty(TODAY - timedelta(days=91), TODAY - timedelta(days=5), TODAY) == 0.5


def test_novelty_seen_earlier_the_same_day_counts_as_seen() -> None:
    assert novelty(TODAY, TODAY, TODAY) == 0.0


def test_novelty_rejects_last_seen_after_the_transaction() -> None:
    # the caller must pass history *before* the transaction (and without the transaction itself)
    with pytest.raises(ValueError):
        novelty(TODAY + timedelta(days=1), None, TODAY)


# ── materiality = clip(amount / (0.10 · disposable), 0, 1) ───────────────────


@pytest.mark.parametrize(
    ("amount", "disposable", "expected"),
    [
        (D("219.25"), D("4385"), 0.5),
        (D("438.50"), D("4385"), 1.0),  # exactly 10% of disposable
        (D("438.49"), D("4385"), 438.49 / 438.5),
        (D("0"), D("4385"), 0.0),
        (D("350"), D("4385"), 350 / 438.5),
    ],
)
def test_materiality_is_share_of_ten_percent_of_disposable(
    amount: Decimal, disposable: Decimal, expected: float
) -> None:
    assert materiality(amount, disposable) == pytest.approx(expected)


@pytest.mark.parametrize("disposable", [D("0"), D("-1200")])
def test_materiality_non_positive_disposable_is_one(disposable: Decimal) -> None:
    assert materiality(D("50"), disposable) == 1.0


def test_materiality_rejects_negative_amount() -> None:
    with pytest.raises(ValueError):
        materiality(D("-5"), D("4385"))


# ── personalisation: same purchase, different person ─────────────────────────


def test_same_shopgo_350_matches_arch_table_for_ioana_and_matei() -> None:
    # arch 5.3.4 table: Ioana (family of 4, median 140) 0.79 · 0.58, Matei (alone, median 85) 1 · 0.80
    # Ioana's MAD 45 and disposable 6 034 are the values that reproduce the table (E13 calibrates them)
    ioana_stat = stat_score(robust_z(D("350"), D("140"), D("45")))
    ioana_mat = materiality(D("350"), D("6034"))
    matei_stat = stat_score(robust_z(D("350"), D("85"), D("25")))
    matei_mat = materiality(D("350"), D("4385"))
    assert ioana_stat == pytest.approx(0.79, abs=0.01)
    assert ioana_mat == pytest.approx(0.58, abs=0.01)
    assert matei_stat == 1.0
    assert matei_mat == pytest.approx(0.80, abs=0.01)


# ── invariants ───────────────────────────────────────────────────────────────


@given(amount=money, median=money, mad=money)
def test_stat_is_always_between_zero_and_one(amount: Decimal, median: Decimal, mad: Decimal) -> None:
    assert 0.0 <= stat_score(robust_z(amount, median, mad)) <= 1.0


@given(amount=money, disposable=any_money)
def test_materiality_is_always_between_zero_and_one(amount: Decimal, disposable: Decimal) -> None:
    assert 0.0 <= materiality(amount, disposable) <= 1.0


@given(merchant=last_seen, category=last_seen)
def test_novelty_is_always_zero_half_or_one(merchant: date | None, category: date | None) -> None:
    assert novelty(merchant, category, TODAY) in {0.0, 0.5, 1.0}


@given(median=money, mad=money, a=money, b=money)
def test_stat_never_decreases_when_the_amount_grows(
    median: Decimal, mad: Decimal, a: Decimal, b: Decimal
) -> None:
    low, high = sorted((a, b))
    assert stat_score(robust_z(low, median, mad)) <= stat_score(robust_z(high, median, mad))
