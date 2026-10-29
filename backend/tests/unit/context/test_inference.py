"""C10: hypotheses from the transactions (arch 5.3.8, F16; WB C10)."""

from datetime import date, timedelta
from typing import Any

import pytest

from app.agent.style import find_banned
from app.context.inference import QUESTIONS, STATEMENTS, infer_hypotheses, question_for
from app.domain.enums import FactSource, FactStatus, FactType, Language
from app.domain.models import LifeFact, TxView
from app.domain.user_context import UserContext
from tests.builders import TODAY, at, ctx, fact, matei_ctx

_ids = iter(range(1000, 100000))


def spend(
    days_ago: int, category: str, merchant_raw: str, amount: str = "200", **extra: Any
) -> TxView:
    day = TODAY - timedelta(days=days_ago)
    return TxView.model_validate(
        {
            "id": next(_ids),
            "occurred_at": at(day, 18),
            "merchant_raw": merchant_raw,
            "category": category,
            "direction": "debit",
            "amount": amount,
            "effective_amount": amount,
            **extra,
        }
    )


def fuel(days_ago: int) -> TxView:
    return spend(days_ago, "fuel", "PETROM 112 BUCURESTI", merchant_id="petrom", merchant="Petrom")


def pets(days_ago: int) -> TxView:
    return spend(days_ago, "pets", "ANIMAX SRL", "120", merchant_id="animax", merchant="Animax")


def kindergarten(days_ago: int) -> TxView:
    return spend(days_ago, "education", "GRADINITA RAZA DE SOARE", "900")


def rent(days_ago: int, amount: str) -> TxView:
    return spend(days_ago, "housing_rent", "TRANSFER CHIRIE PROPRIETAR", amount)


def user(*txs: TxView, **overrides: Any) -> UserContext:
    return ctx(transactions=list(txs), **overrides)


def hypothesis(type: FactType, value: dict[str, Any], **overrides: Any) -> LifeFact:
    overrides.setdefault("id", 90)
    return fact(
        type,
        value=value,
        source="inferred",
        status=overrides.pop("status", "hypothesis"),
        confidence=0.5,
        **overrides,
    )


def only(found: list[Any]) -> Any:
    assert len(found) == 1, found
    return found[0]


# ── the detectors ────────────────────────────────────────────────────────────────────────────


def test_fuel_in_three_of_four_weeks_is_a_vehicle_hypothesis_at_half() -> None:
    txs = [fuel(1), fuel(9), fuel(23)]  # weeks 1, 2 and 4
    draft = only(infer_hypotheses(user(*txs), TODAY))
    assert draft.type is FactType.VEHICLE
    assert draft.confidence == 0.5
    assert draft.status is FactStatus.HYPOTHESIS
    assert draft.source is FactSource.INFERRED
    assert draft.valid_from == TODAY
    assert set(draft.evidence.transaction_ids) == {t.id for t in txs}
    assert question_for(draft, "ro") == "Ai mașină?"
    assert question_for(draft, "en") == "Do you have a car?"
    assert draft.text == "Am mașină"


def test_fuel_in_two_of_four_weeks_is_not_enough() -> None:
    assert infer_hypotheses(user(fuel(1), fuel(2), fuel(9), fuel(30)), TODAY) == []


def test_fuel_by_merchant_counts_without_the_category() -> None:
    txs = [
        spend(d, "other", "OMV 2231", merchant_id="omv") for d in (0, 8, 15)
    ]  # a script category won
    assert only(infer_hypotheses(user(*txs), TODAY)).type is FactType.VEHICLE


def test_a_monthly_pet_shop_for_three_months_is_a_pet() -> None:
    draft = only(infer_hypotheses(user(pets(3), pets(33), pets(64)), TODAY))
    assert draft.type is FactType.PET
    assert question_for(draft, "ro") == "Ai un animal de companie?"


def test_a_pet_shop_in_only_two_of_three_months_is_not_a_pet() -> None:
    assert infer_hypotheses(user(pets(3), pets(10), pets(64)), TODAY) == []


def test_monthly_kindergarten_is_a_child() -> None:
    draft = only(infer_hypotheses(user(kindergarten(5), kindergarten(35), kindergarten(65)), TODAY))
    assert draft.type is FactType.HOUSEHOLD_MEMBER
    assert draft.value.role == "child"
    assert draft.value.age == 4  # kindergarten age (3-6): the card lets the user correct it
    assert question_for(draft, "ro") == "Ai un copil la grădiniță?"


def test_decathlon_and_a_race_fee_is_a_runner() -> None:
    gear = spend(20, "sport", "DECATHLON BANEASA", "350", merchant_id="decathlon")
    fee = spend(12, "sport", "Taxă înscriere Semimaratonul București", "150")
    draft = only(infer_hypotheses(user(gear, fee), TODAY))
    assert draft.type is FactType.ACTIVITY
    assert draft.value.name == "running"
    assert question_for(draft, "en") == "Do you run races?"


def test_decathlon_alone_is_not_a_runner() -> None:
    gear = spend(20, "sport", "DECATHLON BANEASA", "350", merchant_id="decathlon")
    assert infer_hypotheses(user(gear), TODAY) == []


def test_a_changed_rent_asks_whether_they_moved() -> None:
    txs = [rent(75, "2000"), rent(45, "2000"), rent(14, "2400")]
    draft = only(infer_hypotheses(user(*txs), TODAY))
    assert draft.type is FactType.HOUSING
    assert draft.confidence == 0.4
    assert draft.valid_from == TODAY - timedelta(days=14)
    assert question_for(draft, "ro") == "Te-ai mutat? Chiria pare să fie acum 2.400 de lei."
    assert question_for(draft, "en") == "Did you move? Your rent seems to be 2,400 lei now."


def test_the_same_rent_or_a_small_change_asks_nothing() -> None:
    assert infer_hypotheses(user(rent(45, "2000"), rent(14, "2000")), TODAY) == []
    assert infer_hypotheses(user(rent(45, "2000"), rent(14, "2150")), TODAY) == []


def test_a_confirmed_housing_fact_from_before_the_change_does_not_block_moved() -> None:
    txs = [rent(45, "2000"), rent(14, "2400")]
    known = fact(FactType.HOUSING, value={"kind": "rent"}, valid_from=date(2026, 1, 1))
    assert only(infer_hypotheses(user(*txs, facts=[known]), TODAY)).type is FactType.HOUSING


def test_a_housing_fact_told_after_the_change_blocks_moved() -> None:
    txs = [rent(45, "2000"), rent(14, "2400")]
    told = fact(FactType.HOUSING, value={"kind": "rent"}, valid_from=TODAY - timedelta(days=10))
    assert infer_hypotheses(user(*txs, facts=[told]), TODAY) == []


# ── never sensitive ──────────────────────────────────────────────────────────────────────────


def test_weekly_pharmacy_is_never_a_health_hypothesis() -> None:
    txs = [
        spend(d, "health_pharmacy", "FARMACIA CATENA", "80", merchant_id="catena")
        for d in range(0, 120, 7)
    ]
    assert infer_hypotheses(user(*txs), TODAY) == []


def test_pharmacy_rows_feed_no_detector_even_with_matching_words() -> None:
    txs = [
        spend(d, "health_pharmacy", "FARMACIE BENZINARIE PETROM", merchant_id="petrom")
        for d in (1, 8, 15, 22)
    ]
    assert infer_hypotheses(user(*txs), TODAY) == []


# ── dedupe, rejected, one per run ────────────────────────────────────────────────────────────


def test_a_confirmed_vehicle_fact_means_no_duplicate() -> None:
    txs = [fuel(1), fuel(9), fuel(16)]
    assert infer_hypotheses(user(*txs, facts=[fact(FactType.VEHICLE)]), TODAY) == []


def test_an_open_vehicle_hypothesis_means_no_duplicate() -> None:
    txs = [fuel(1), fuel(9), fuel(16)]
    open_one = hypothesis(FactType.VEHICLE, {"kind": "car"})
    assert infer_hypotheses(user(*txs, hypotheses=[open_one]), TODAY) == []


def test_a_rejected_hypothesis_is_never_proposed_again() -> None:
    txs = [fuel(d) for d in range(0, 60, 3)]
    rejected = hypothesis(FactType.VEHICLE, {"kind": "car"}, status="rejected")
    assert infer_hypotheses(user(*txs), TODAY, rejected=[rejected]) == []
    later = TODAY + timedelta(days=200)
    more = [fuel(-d) for d in range(150, 200, 3)]  # half a year later, still fuel weekly
    assert infer_hypotheses(user(*txs, *more), later, rejected=[rejected]) == []


def test_a_confirmed_child_blocks_kindergarten_but_an_adult_does_not() -> None:
    txs = [kindergarten(5), kindergarten(35), kindergarten(65)]
    child = fact(FactType.HOUSEHOLD_MEMBER, value={"role": "child", "age": 4})
    adult = fact(FactType.HOUSEHOLD_MEMBER, value={"role": "adult", "relation": "partner"})
    assert infer_hypotheses(user(*txs, facts=[child]), TODAY) == []
    assert only(infer_hypotheses(user(*txs, facts=[adult]), TODAY)).value.role == "child"


def test_a_confirmed_running_activity_blocks_runner_but_the_gym_does_not() -> None:
    gear = spend(20, "sport", "DECATHLON BANEASA", "350", merchant_id="decathlon")
    fee = spend(12, "sport", "MARATON CLUJ TAXA PARTICIPARE", "150")
    running = fact(FactType.ACTIVITY, value={"name": "alergare", "per_week": 3})
    gym = fact(FactType.ACTIVITY, value={"name": "sală", "per_week": 3})
    assert infer_hypotheses(user(gear, fee, facts=[running]), TODAY) == []
    assert only(infer_hypotheses(user(gear, fee, facts=[gym]), TODAY)).type is FactType.ACTIVITY


def test_at_most_one_new_hypothesis_per_run_in_priority_order() -> None:
    txs = [fuel(1), fuel(9), fuel(16), pets(3), pets(33), pets(64)]
    assert only(infer_hypotheses(user(*txs), TODAY)).type is FactType.VEHICLE
    with_car = user(*txs, facts=[fact(FactType.VEHICLE)])
    assert only(infer_hypotheses(with_car, TODAY)).type is FactType.PET  # the next week's run


def test_no_new_hypothesis_while_three_are_open() -> None:
    open_ones = [
        hypothesis(FactType.CUSTOM, {"description": f"guess {i}"}, id=80 + i) for i in range(3)
    ]
    assert infer_hypotheses(user(fuel(1), fuel(9), fuel(16), hypotheses=open_ones), TODAY) == []


def test_old_and_future_transactions_are_ignored() -> None:
    assert infer_hypotheses(user(fuel(40), fuel(47), fuel(54)), TODAY) == []
    assert infer_hypotheses(user(fuel(-1), fuel(-8), fuel(1)), TODAY) == []


def test_matei_seeded_context_yields_nothing() -> None:
    assert infer_hypotheses(matei_ctx(), TODAY) == []


# ── texts ────────────────────────────────────────────────────────────────────────────────────


def test_the_statement_follows_the_user_language() -> None:
    en = user(fuel(1), fuel(9), fuel(16), profile={"name": "Alex", "language": "en",
                                                   "coach_style": "warm"})  # fmt: skip
    assert only(infer_hypotheses(en, TODAY)).text == "I have a car"


@pytest.mark.parametrize("table", [QUESTIONS, STATEMENTS])
def test_every_text_is_clean_in_both_languages(table: dict[str, tuple[str, str]]) -> None:
    for ro, en in table.values():
        assert find_banned(ro.format(amount="2.400 de lei"), "ro") == []
        assert find_banned(en.format(amount="2,400 lei"), "en") == []


def test_question_for_a_fact_we_did_not_infer_is_none() -> None:
    assert question_for(fact(FactType.CITY), Language.RO) is None
    assert question_for(fact(FactType.OCCUPATION), Language.EN) is None
