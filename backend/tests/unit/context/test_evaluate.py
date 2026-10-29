"""C6: evaluate (arch 5.3.4), acceptance cases #1, #3-#6, #11 and the thresholds."""

from datetime import timedelta
from typing import Any

import pytest

from app.context.evaluate import decide, evaluate
from app.domain.enums import Category, Decision, Purpose
from app.domain.models import TxView
from tests.builders import TODAY, andrei_ctx, at, bianca_ctx, ioana_ctx, matei_ctx, tx
from tests.unit.context.test_life_fit import emag_tv

NEW = {
    "purpose": None,
    "beneficiary": None,
    "annotation_source": None,
    "annotation_confidence": None,
    "decision": None,
}


def new_tx(**overrides: Any) -> TxView:
    return tx(**(NEW | {"id": 700} | overrides))


def test_1_matei_mega_500_is_asked() -> None:
    mega = new_tx(amount="500", effective_amount="500")
    result = evaluate(matei_ctx(), mega)
    assert result.decision is Decision.ASK
    assert result.purpose is Purpose.UNKNOWN  # provisional
    assert result.effective_amount == 500
    assert result.question_hint is not None
    assert result.question_hint.reason == "basket_ratio"
    assert result.question_hint.params["ratio"] == 6
    assert result.goal_impact == pytest.approx(500 / 4800)


def test_3_andrei_tv_is_a_work_tool() -> None:
    result = evaluate(andrei_ctx(), emag_tv())
    assert result.decision is Decision.INFORM
    assert result.purpose is Purpose.WORK_TOOL
    assert result.question_hint is None
    assert result.explanation is not None
    assert "analist sportiv" in result.explanation


def test_4_bianca_tv_is_asked() -> None:
    result = evaluate(bianca_ctx(), emag_tv())
    assert result.decision is Decision.ASK
    assert result.question_hint is not None
    assert result.question_hint.ask_what_item is False


def test_5_bianca_tv_without_items_asks_what_it_was() -> None:
    result = evaluate(bianca_ctx(), emag_tv(items=None))
    assert result.question_hint is not None
    assert result.question_hint.ask_what_item is True


def test_6_ioana_shopgo_350_is_normal_for_her_family() -> None:
    shopgo = {"merchant_raw": "SHOP&GO", "merchant": "Shop&Go", "merchant_id": "shop_and_go"}
    history = [
        tx(id=800 + d, occurred_at=at(TODAY - timedelta(days=d)), amount="140", **shopgo)
        for d in range(1, 6)
    ]
    base = ioana_ctx()
    family = base.baselines[Category.GROCERIES].replace(personal_mad="45")
    ctx = base.replace(transactions=history, baselines={"groceries": family})
    result = evaluate(ctx, new_tx(amount="350", effective_amount="350", **shopgo))
    assert result.decision is Decision.AUTO
    assert result.question_hint is None


def test_11_pharmacy_is_never_asked() -> None:
    drmax = new_tx(
        merchant_raw="DR.MAX",
        merchant="Dr.Max",
        merchant_id="dr_max",
        category="health_pharmacy",
        amount="5000",
        effective_amount="5000",
    )
    result = evaluate(matei_ctx(), drmax)
    assert (result.decision, result.purpose) == (Decision.AUTO, Purpose.ESSENTIAL_LIVING)


@pytest.mark.parametrize(
    ("ctx_name", "amount", "decision"),
    [("bianca", "49.99", Decision.IGNORE), ("matei", "69.99", Decision.IGNORE)],
)
def test_amount_floor(ctx_name: str, amount: str, decision: Decision) -> None:
    ctx = bianca_ctx() if ctx_name == "bianca" else matei_ctx()
    assert evaluate(ctx, new_tx(amount=amount, effective_amount=amount)).decision is decision


def test_floor_boundary_is_evaluated() -> None:
    at_floor = evaluate(matei_ctx(), new_tx(amount="70", effective_amount="70"))
    assert at_floor.decision is not Decision.IGNORE


def test_thresholds_are_inclusive() -> None:
    assert decide(0.9, 0.0, 0.55) is Decision.ASK
    assert decide(0.9, 0.0, 0.5499) is Decision.AUTO
    assert decide(0.5, 0.6, 0.2) is Decision.INFORM
    assert decide(0.5, 0.59, 0.2) is Decision.AUTO
    assert decide(0.4999, 0.9, 0.0) is Decision.AUTO
