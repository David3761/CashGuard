"""E13 golden: Matei's demo probabilities (arch 16.2 Scene A) from the committed persona files.

Fails when the engine or the persona data change in a way that breaks the demo script.
Assumes what the seed (B12) and the pipeline do: Matei is user 1; the seed saves plan version 1 and
its
forecast on 2026-06-15 plus the "last week" snapshot as of 2026-06-08; the Mega Image transaction
makes
plan version 2, the answer version 3; the receivable is expected 14 days later.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.domain.enums import (
    Beneficiary,
    Category,
    CoachStyle,
    Direction,
    Language,
    PotKind,
    Purpose,
    ReceivableStatus,
)
from app.domain.models import (
    Account,
    FixedCost,
    IncomeSource,
    Receivable,
    TxView,
    UserProfile,
)
from app.domain.money import parse_json
from app.engine.forecast import build_forecast_inputs, forecast
from app.engine.stats import stable_seed
from tests.builders import ctx
from tests.builders import goal as make_goal
from tests.builders import pot as make_pot
from tests.builders import receivable as make_receivable

D = Decimal
PERSONA = Path(__file__).resolve().parents[2] / "data" / "personas" / "matei"
MATEI_ID = 1
TODAY = date(2026, 6, 15)
LAST_WEEK = date(2026, 6, 8)
MEGA_AT = datetime(2026, 6, 15, 10, 5, tzinfo=UTC)  # 13:05 in Bucharest

# recorded after the E13 calibration; a change here must be reviewed against the demo script
GOLDEN = {"last_week": 0.7153, "before": 0.7879, "provisional": 0.6982, "answered": 0.7590}
# the demo script's numbers and how far the engine may be from them (see merged_notes: E13)
DEMO = {
    "last_week": (0.72, 0.01),
    "before": (0.78, 0.01),
    "provisional": (0.71, 0.02),
    "answered": (0.77, 0.02),
}


def to_tx(i: int, t: dict[str, Any]) -> TxView:
    annotation = t["annotation"] or {}
    return TxView(
        id=i,
        merchant_raw=t["merchant_raw"],
        amount=D(t["amount"]),
        effective_amount=D(annotation.get("effective_amount", t["amount"])),
        category=Category(t["category"]),
        occurred_at=datetime.fromisoformat(t["occurred_at"]),
        direction=Direction(t["direction"]),
        purpose=Purpose(annotation.get("purpose", "unknown")),
        beneficiary=Beneficiary.SELF,
    )


def matei(
    today: date, extra: tuple[TxView, ...] = (), receivables: tuple[Receivable, ...] = ()
) -> Any:
    # strict, exact JSON (money as Decimal, H-8)
    profile: Any = parse_json((PERSONA / "profile.json").read_bytes())
    rows: Any = parse_json((PERSONA / "transactions.json").read_bytes())
    goal = make_goal(
        id=1,
        amount=D(profile["goal"]["amount"]),
        deadline=date.fromisoformat(profile["goal"]["deadline"]),
    )
    pot = make_pot(
        id=1,
        name=profile["goal_pot"]["name"],
        kind=PotKind.GOAL,
        target=goal.amount,
        saved=D(profile["goal_pot"]["saved"]),
        goal_id=1,
    )
    history = [
        to_tx(i, t)
        for i, t in enumerate(rows, 1)
        if datetime.fromisoformat(t["occurred_at"]).date() <= today
    ]
    return ctx(
        user_id=MATEI_ID,
        profile=UserProfile(
            name="Matei",
            city=profile["user"]["city"],
            language=Language.RO,
            coach_style=CoachStyle.WARM,
        ),
        account=Account(current_balance=D(profile["account"]["current_balance"])),
        goal=goal,
        goal_pot=pot,
        pots=[pot],
        income_sources=[
            IncomeSource(
                id=i, source=s["source"], amount=D(s["amount"]), day_of_month=s["day_of_month"]
            )
            for i, s in enumerate(profile["income_sources"], 1)
        ],
        fixed_costs=[
            FixedCost(id=i, name=f["name"], amount=D(f["amount"]), day_of_month=f["day_of_month"])
            for i, f in enumerate(profile["fixed_costs"], 1)
        ],
        transactions=[*history, *extra],
        receivables=list(receivables),
    )


def probability(c: Any, today: date, plan_version: int) -> float:
    return forecast(
        build_forecast_inputs(c, today), seed=stable_seed(MATEI_ID, today, plan_version)
    ).probability


def scene_a() -> dict[str, float]:
    mega = TxView(
        id=918,
        merchant_raw="MEGA IMAGE 0451 BUCURESTI",
        amount=D("500"),
        effective_amount=D("500"),
        category=Category.GROCERIES,
        occurred_at=MEGA_AT,
        direction=Direction.DEBIT,
        purpose=Purpose.UNKNOWN,
        beneficiary=Beneficiary.SELF,
    )
    answered = mega.model_copy(
        update={
            "effective_amount": D("100"),
            "purpose": Purpose.ON_BEHALF_OF_OTHERS,
            "beneficiary": Beneficiary.SHARED,
        }
    )
    owed = make_receivable(
        id=9,
        amount=D("400"),
        debtor_label="colegi",
        expected_by=TODAY + timedelta(days=14),
        status=ReceivableStatus.OPEN,
        transaction_id=918,
    )
    return {
        "last_week": probability(matei(LAST_WEEK), LAST_WEEK, 1),
        "before": probability(matei(TODAY), TODAY, 1),
        "provisional": probability(matei(TODAY, (mega,)), TODAY, 2),
        "answered": probability(matei(TODAY, (answered,), (owed,)), TODAY, 3),
    }


def test_scene_a_matches_the_recorded_golden_values() -> None:
    assert scene_a() == pytest.approx(GOLDEN, abs=1e-4)


@pytest.mark.parametrize("moment", list(DEMO))
def test_scene_a_is_close_to_the_demo_script(moment: str) -> None:
    target, tolerance = DEMO[moment]
    assert abs(scene_a()[moment] - target) <= tolerance


def test_scene_a_story_order() -> None:
    p = scene_a()
    assert p["last_week"] < p["before"]  # "78 %, față de 72 % săptămâna trecută"
    assert (
        p["provisional"] < p["answered"] < p["before"]
    )  # 500 lei drops it, the answer lifts it back
