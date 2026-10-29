"""F2 step 1: money helpers (cases from DGAdavid1.md F2)."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.money import share_each, split_share, to_money

D = Decimal


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1.005", "1.01"), (1.005, "1.01"), (-2.675, "-2.68"), (7, "7.00"), (D("0.30"), "0.30")],
)
def test_to_money_rounds_half_up_to_two_decimals(raw, expected):
    result = to_money(raw)
    assert result == D(expected)
    assert result.as_tuple().exponent == -2


@pytest.mark.parametrize(
    ("total", "people", "own", "others"),
    [
        ("500", 5, "100.00", "400.00"),
        ("500", 3, "166.67", "333.33"),
        ("100", 1, "100.00", "0.00"),
        ("0.01", 3, "0.00", "0.01"),
    ],
)
def test_split_share(total, people, own, others):
    assert split_share(D(total), people) == (D(own), D(others))


@pytest.mark.parametrize(("total", "people"), [("500", 0), ("500", -1), ("-1", 2)])
def test_split_share_rejects_bad_input(total, people):
    with pytest.raises(ValueError):
        split_share(D(total), people)


def test_share_each():
    assert share_each(D("333.33"), 2) == D("166.67")
    assert share_each(D("400"), 4) == D("100.00")
    with pytest.raises(ValueError):
        share_each(D("400"), 0)


@given(
    total=st.decimals(min_value=D("0.01"), max_value=D("100000"), places=2),
    people=st.integers(min_value=1, max_value=50),
)
def test_split_share_always_adds_up_and_never_goes_negative(total, people):
    own, others = split_share(total, people)
    assert own + others == total
    assert own >= 0 and others >= 0
