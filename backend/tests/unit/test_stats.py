from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.engine.stats import DAYS_PER_MONTH, blend, median_and_mad, monthly_rate

D = Decimal
money = st.decimals(min_value=0, max_value=100_000, places=2, allow_nan=False, allow_infinity=False)


# ── median_and_mad ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("values", "median", "mad"),
    [
        ([D("85")], D("85"), D("0")),
        ([D("60"), D("85"), D("110")], D("85"), D("25")),
        (
            [D("10"), D("20"), D("30"), D("40")],
            D("25"),
            D("10"),
        ),  # even count → mean of the middle two
        ([D("80"), D("85"), D("90"), D("500")], D("87.5"), D("5")),  # one outlier barely moves MAD
    ],
)
def test_median_and_mad_hand_computed(values: list[Decimal], median: Decimal, mad: Decimal) -> None:
    assert median_and_mad(values) == (median, mad)


def test_median_and_mad_empty_is_zero() -> None:
    assert median_and_mad([]) == (D("0"), D("0"))


def test_median_and_mad_identical_values_have_zero_mad() -> None:
    assert median_and_mad([D("100")] * 5) == (D("100"), D("0"))


@given(values=st.lists(money, min_size=1, max_size=50))
def test_median_and_mad_are_non_negative_and_median_within_range(values: list[Decimal]) -> None:
    median, mad = median_and_mad(values)
    assert min(values) <= median <= max(values)
    assert mad >= 0


# ── blend = (n·personal + k·prior) / (n + k) ─────────────────────────────────


@pytest.mark.parametrize(
    ("n", "personal", "prior", "expected"),
    [
        (0, D("0"), D("70"), D("70")),  # new user: the prior
        (5, D("100"), D("70"), D("85")),  # n = k: the midpoint
        (100, D("100"), D("70"), D("100") * 100 / 105 + D("70") * 5 / 105),
    ],
)
def test_blend_moves_from_prior_to_personal(
    n: int, personal: Decimal, prior: Decimal, expected: Decimal
) -> None:
    assert blend(n, personal, prior) == pytest.approx(expected)


def test_blend_without_prior_weight_is_personal() -> None:
    assert blend(3, D("42"), D("999"), k=0) == D("42")


@pytest.mark.parametrize(("n", "k"), [(-1, 5), (2, -1), (0, 0)])
def test_blend_rejects_invalid_weights(n: int, k: int) -> None:
    with pytest.raises(ValueError, match="must be ≥ 0"):
        blend(n, D("1"), D("1"), k=k)


@given(n=st.integers(0, 500), personal=money, prior=money)
def test_blend_is_between_personal_and_prior(n: int, personal: Decimal, prior: Decimal) -> None:
    low, high = sorted((personal, prior))
    assert low <= blend(n, personal, prior) <= high


# ── monthly_rate ─────────────────────────────────────────────────────────────


def test_monthly_rate_scales_total_to_an_average_month() -> None:
    assert DAYS_PER_MONTH == D("30.4375")  # 365.25 / 12
    assert monthly_rate(D("1000"), 60) == D("1000") * D("30.4375") / 60


def test_monthly_rate_of_a_one_day_span() -> None:
    assert monthly_rate(D("350"), 1) == D("350") * DAYS_PER_MONTH


def test_monthly_rate_no_span_is_zero() -> None:
    assert monthly_rate(D("500"), 0) == D("0")


def test_monthly_rate_rejects_negative_span() -> None:
    with pytest.raises(ValueError, match="span_days"):
        monthly_rate(D("500"), -1)
