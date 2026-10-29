"""C5: life_fit and the "because" (arch 5.3.4 step 3)."""

from datetime import date, time, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.context.life_fit import amount_term, explain, life_fit, time_term
from app.domain.enums import FactStatus, Language
from app.domain.models import TxView
from tests.builders import (
    TODAY,
    andrei_ctx,
    at,
    bianca_ctx,
    fact,
    ioana_ctx,
    matei_ctx,
    rule,
    signature,
    tx,
)

TV_ITEMS = [{"name": 'Televizor 65"'}]


def emag_tv(**overrides: Any) -> TxView:
    data: dict[str, Any] = {
        "id": 500,
        "occurred_at": at(TODAY, 11, 0),
        "merchant_raw": "EMAG.RO",
        "merchant": "eMAG",
        "merchant_id": "emag",
        "mcc": "5732",
        "category": "electronics",
        "amount": "4500",
        "effective_amount": "4500",
        "items": TV_ITEMS,
        "purpose": None,
        "beneficiary": None,
        "annotation_source": None,
        "annotation_confidence": None,
        "decision": None,
    }
    return tx(**(data | overrides))


def test_andrei_tv_with_items() -> None:
    fit = life_fit(emag_tv(), andrei_ctx())
    assert fit.score == pytest.approx(0.855, abs=0.005)
    assert (fit.source, fit.fact_id) == ("signature", 11)


def test_andrei_tv_without_items_still_fits() -> None:
    fit = life_fit(emag_tv(items=None), andrei_ctx())
    assert fit.score == pytest.approx(0.684, abs=0.001)
    assert fit.score >= 0.6


def test_bianca_tv_has_no_source() -> None:
    fit = life_fit(emag_tv(), bianca_ctx())
    assert (fit.score, fit.source) == (0.0, "none")


@pytest.mark.parametrize(("days_ago", "factor"), [(60, 60 / 900), (900, 1.0), (1000, 1.0)])
def test_saturation_after_a_previous_tv(days_ago: int, factor: float) -> None:
    before = emag_tv(id=499, occurred_at=at(TODAY - timedelta(days=days_ago), 11, 0))
    ctx = andrei_ctx().replace(transactions=[before])
    assert life_fit(emag_tv(), ctx).score == pytest.approx(0.855 * factor, abs=0.005)


def test_a_hypothesis_fact_caps_the_score() -> None:
    base = andrei_ctx()
    hypo = base.facts[0].replace(status=FactStatus.HYPOTHESIS, confidence=0.5)
    ctx = base.replace(facts=base.facts[1:], hypotheses=[hypo])
    assert life_fit(emag_tv(), ctx).score == pytest.approx(0.45)


def test_amount_term_decays_to_zero_at_twice_the_range() -> None:
    low, high = Decimal(1500), Decimal(9000)
    assert amount_term(Decimal(4500), low, high) == 1
    assert amount_term(Decimal(13500), low, high) == pytest.approx(0.5)
    assert amount_term(Decimal(18000), low, high) == 0
    assert amount_term(Decimal(750), low, high) == 0


def test_time_window_mismatch() -> None:
    friday = signature(time_window={"weekdays": [5], "from": "12:00", "to": "15:00"})
    assert time_term(emag_tv(), friday) == 0  # a Monday
    friday_lunch = emag_tv(occurred_at=at(date(2026, 6, 19), 13, 10))
    assert time_term(friday_lunch, friday) == 1
    assert time_term(emag_tv(occurred_at=at(date(2026, 6, 19), 15, 0)), friday) == 0
    assert friday.time_window is not None
    assert friday.time_window.from_ == time(12, 0)


def test_keywords_fold_case_and_diacritics() -> None:
    ctx = andrei_ctx()
    upper = emag_tv(items=[{"name": "TELEVÍZOR SAMSUNG"}])
    assert life_fit(upper, ctx).score == pytest.approx(0.855, abs=0.005)


def test_precedent_from_an_answered_transaction() -> None:
    ctx = matei_ctx().replace(rules=[])
    monday_lunch = tx(
        id=600,
        merchant_raw="TRATTORIA BUONGUSTO",
        merchant=None,
        merchant_id=None,
        category="restaurants",
        amount="100",
        effective_amount="100",
    )
    fit = life_fit(monday_lunch, ctx)
    assert fit.source == "precedent"
    assert fit.score == pytest.approx(0.8 * (1 - 5 / 100))


def test_partial_rule_gives_its_confidence() -> None:
    ctx = matei_ctx().replace(transactions=[])
    lunch = tx(
        id=601,
        occurred_at=at(date(2026, 6, 19), 13, 10),
        category="restaurants",
        amount="95",
        effective_amount="95",
    )
    fit = life_fit(lunch, ctx)
    assert (fit.source, fit.rule_id, fit.score) == ("rule", 1, 0.7)
    assert life_fit(lunch, ctx.replace(rules=[rule(confidence=0.9)])).source == "none"


def test_ioana_school_supplies_in_august_are_expected() -> None:
    supplies = tx(
        id=602,
        occurred_at=at(date(2026, 8, 20)),
        merchant_raw="DIVERTA",
        merchant="Diverta",
        merchant_id="diverta",
        category="books",
        amount="550",
        effective_amount="550",
    )
    fit = life_fit(supplies, ioana_ctx())
    assert fit.source == "expects_event"
    assert fit.score == pytest.approx(0.8 * 0.95)
    in_june = supplies.replace(occurred_at=at(TODAY))
    assert life_fit(in_june, ioana_ctx()).source == "none"


def test_the_explanation_mentions_the_fact_in_both_languages() -> None:
    fit = life_fit(emag_tv(), andrei_ctx())
    ro, en = explain(fit, Language.RO), explain(fit, Language.EN)
    assert ro is not None
    assert en is not None
    assert "analist sportiv" in ro
    assert "Echipament de lucru" in ro
    assert "analist sportiv" in en
    assert "Work equipment" in en
    assert explain(life_fit(emag_tv(), bianca_ctx()), "ro") is None


def test_tie_break_prefers_the_confirmed_fact() -> None:
    base = andrei_ctx()
    twin = fact(id=99, text="am un canal de sport", status="hypothesis", confidence=0.95)
    ctx = base.replace(hypotheses=[twin], signatures=[*base.signatures, signature(fact_id=99)])
    assert life_fit(emag_tv(), ctx).fact_id == 11


@pytest.mark.parametrize("amount", ["50", "1500", "4500", "9000", "20000"])
def test_score_in_unit_range_and_deterministic(amount: str) -> None:
    tv = emag_tv(amount=amount, effective_amount=amount)
    first, second = life_fit(tv, andrei_ctx()), life_fit(tv, andrei_ctx())
    assert 0 <= first.score <= 1
    assert first == second
