"""C9: propagation on a fact change (arch 5.3.9): re-reading, precedence, scale, the shells."""

import time as stopwatch
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app import clock
from app.context import propagate, service
from app.context.evaluate import evaluate
from app.context.propagate import (
    ScaleWindow,
    fact_scale_windows,
    fact_signatures,
    reevaluate,
    scale_windows,
)
from app.domain.enums import (
    AnnotationSource,
    Category,
    Decision,
    FactStatus,
    FactType,
    Purpose,
    SignatureOrigin,
)
from app.domain.models import LifeFact, TxView
from app.domain.results import Forecast, PlanSummary
from app.domain.user_context import UserContext
from app.engine.baselines import compute_baselines, household_scale
from app.engine.service import ledger_delta
from tests.builders import TODAY, andrei_ctx, at, fact, ioana_ctx, signature
from tests.unit.context.test_life_fit import emag_tv

YESTERDAY = TODAY - timedelta(days=1)


def without_job(ctx: UserContext) -> UserContext:
    """Andrei before he told us his job: no occupation fact, no TV signature."""
    return ctx.replace(
        facts=[f for f in ctx.facts if f.type is not FactType.OCCUPATION],
        signatures=[],
    )


def stored(ctx: UserContext, tx: TxView) -> TxView:
    """`tx` with the reading C6 gave it in `ctx`, as the pipeline saved it."""
    reading = evaluate(ctx, tx)
    return tx.replace(
        **reading.model_dump(
            include={
                "category",
                "purpose",
                "beneficiary",
                "effective_amount",
                "decision",
                "explanation",
                "matched_fact_id",
                "matched_rule_id",
                "pot_id",
                "life_fit",
                "anomaly_score",
                "unexplained",
            }
        ),
        annotation_source=reading.annotation_source,
    )


def asked_tv() -> TxView:
    """Andrei's TV, bought yesterday, read automatically as a question (no job known yet)."""
    tv = stored(without_job(andrei_ctx()), emag_tv(occurred_at=at(YESTERDAY, 11)))
    assert (tv.decision, tv.annotation_source, tv.purpose) == (
        Decision.ASK, AnnotationSource.AUTO, Purpose.UNKNOWN
    )  # fmt: skip
    return tv


# ── re-reading ───────────────────────────────────────────────────────────────────────────────


def test_andrei_tv_becomes_a_work_tool_once_the_job_is_known() -> None:
    tv = asked_tv()
    [change] = reevaluate(andrei_ctx(), [tv], TODAY)
    new = change.evaluation
    assert change.transaction_id == tv.id
    assert (new.decision, new.purpose, new.annotation_source, new.matched_fact_id) == (
        Decision.INFORM, Purpose.WORK_TOOL, AnnotationSource.FACT, 11
    )  # fmt: skip
    assert new.explanation is not None
    assert "analist sportiv" in new.explanation
    # the ledger is unchanged: the whole amount was already counted
    assert new.effective_amount == tv.effective_amount == Decimal(4500)
    assert ledger_delta(tv.replace(effective_amount=new.effective_amount)) == ledger_delta(tv)


@pytest.mark.parametrize("source", [AnnotationSource.ANSWER, AnnotationSource.USER_EDIT])
def test_the_same_tv_after_a_user_answer_is_never_overridden(source: AnnotationSource) -> None:
    answered = asked_tv().replace(
        purpose=Purpose.UNPLANNED_DISCRETIONARY, annotation_source=source, decision=Decision.AUTO
    )
    assert reevaluate(andrei_ctx(), [answered], TODAY) == ()


@pytest.mark.parametrize("source", [AnnotationSource.RULE, AnnotationSource.POT, None])
def test_rule_pot_and_unread_transactions_are_left_alone(source: AnnotationSource | None) -> None:
    assert reevaluate(andrei_ctx(), [asked_tv().replace(annotation_source=source)], TODAY) == ()


def test_running_twice_changes_nothing_more() -> None:
    ctx = andrei_ctx()
    tv = asked_tv()
    [change] = reevaluate(ctx, [tv], TODAY)
    saved = stored(ctx, tv)
    assert saved.decision is change.evaluation.decision
    assert reevaluate(ctx, [saved], TODAY) == ()


def test_only_the_last_30_days_are_re_read() -> None:
    old = asked_tv().replace(id=501, occurred_at=at(TODAY - timedelta(days=31), 11))
    edge = asked_tv().replace(id=502, occurred_at=at(TODAY - timedelta(days=30), 11))
    changed = reevaluate(andrei_ctx(), [old, edge], TODAY)
    assert [c.transaction_id for c in changed] == [502]


def test_removing_the_fact_never_turns_the_past_into_a_question() -> None:
    explained = stored(andrei_ctx(), emag_tv(occurred_at=at(YESTERDAY, 11)))
    assert explained.annotation_source is AnnotationSource.FACT
    [change] = reevaluate(without_job(andrei_ctx()), [explained], TODAY)
    assert change.evaluation.decision is Decision.AUTO
    assert change.evaluation.annotation_source is AnnotationSource.DEFAULT
    assert change.evaluation.matched_fact_id is None


def test_a_waiting_question_keeps_its_state() -> None:
    later = asked_tv().replace(decision=Decision.ASK_LATER)
    assert reevaluate(without_job(andrei_ctx()), [later], TODAY) == ()


def test_30_days_take_under_200_ms() -> None:
    ctx = andrei_ctx()
    month = [
        asked_tv().replace(id=600 + d, occurred_at=at(TODAY - timedelta(days=d), 11 + d % 8))
        for d in range(30)
        for _ in range(3)
    ]
    start = stopwatch.perf_counter()
    reevaluate(ctx, month, TODAY)
    assert stopwatch.perf_counter() - start < 0.2


# ── household scale (#13) ────────────────────────────────────────────────────────────────────


def mother() -> LifeFact:
    return fact(
        FactType.HOUSEHOLD_MEMBER,
        id=36,
        value={"role": "adult", "relation": "mother"},
        text="Mama stă la noi în iulie",
        persistence="temporary",
        valid_from=date(2026, 7, 1),
        valid_to=date(2026, 7, 31),
    )


def test_13_ioana_mother_scales_the_household_in_july_only() -> None:
    facts = ioana_ctx().facts
    windows = fact_scale_windows(facts, mother(), TODAY)
    assert windows == (
        ScaleWindow(date(2026, 7, 1), date(2026, 7, 31), Decimal("2.1"), Decimal("2.6")),
    )
    with_mother = [*facts, mother()]
    assert household_scale(with_mother, date(2026, 6, 30)) == Decimal("2.1")
    assert household_scale(with_mother, date(2026, 7, 15)) == Decimal("2.6")
    assert household_scale(with_mother, date(2026, 8, 1)) == Decimal("2.1")


def test_13_groceries_expected_rescale_by_2_6_over_2_1_in_july_only() -> None:
    from app.context.evaluate import default_priors

    def groceries(day: date) -> Decimal:
        scale = household_scale([*ioana_ctx().facts, mother()], day)
        found = compute_baselines([], default_priors(), scale, "Cluj", day, children=2)
        return found[Category.GROCERIES].expected_median

    june, july, august = groceries(TODAY), groceries(date(2026, 7, 15)), groceries(date(2026, 8, 3))
    assert june == august
    assert july / june == pytest.approx(Decimal("2.6") / Decimal("2.1"), abs=Decimal("0.001"))


def test_scale_windows_merge_consecutive_days_only() -> None:
    a = fact(FactType.HOUSEHOLD_MEMBER, id=40, value={"role": "adult"}, valid_from=date(2026, 7, 1),
             valid_to=date(2026, 7, 2), persistence="temporary")  # fmt: skip
    b = a.replace(id=41, valid_from=date(2026, 7, 5), valid_to=date(2026, 7, 5))
    assert [
        (w.start.day, w.end.day) for w in scale_windows([], [a, b], TODAY, date(2026, 8, 1))
    ] == [
        (1, 2),
        (5, 5),
    ]
    assert scale_windows([a], [a], TODAY, date(2026, 8, 1)) == ()


# ── signatures ───────────────────────────────────────────────────────────────────────────────


def test_fact_signatures_keep_claude_ones_and_drop_all_when_not_confirmed() -> None:
    job = andrei_ctx().facts[0]
    claude = signature(fact_id=11, id=90, category="books", merchant_hints=["Cărturești"],
                       item_keywords=[], origin="llm")  # fmt: skip
    library_tv = signature(fact_id=11, id=91)
    fresh = fact_signatures(job, [claude, library_tv])
    assert any(s.origin is SignatureOrigin.LIBRARY and s.category == "electronics" for s in fresh)
    assert [s.category for s in fresh if s.origin is SignatureOrigin.LLM] == ["books"]
    assert all(s.id is None for s in fresh)
    assert fact_signatures(job.replace(status=FactStatus.EXPIRED), [claude]) == []


# ── the shells ───────────────────────────────────────────────────────────────────────────────


class _World:
    """bomboe's services + danutu's engine, in memory, for one user (Andrei)."""

    def __init__(self, ctx: UserContext, txs: list[TxView], job: LifeFact) -> None:
        self.ctx, self.txs, self.job = ctx, {t.id: t for t in txs}, job
        self.calls: list[str] = []
        self.version = 7
        self.signatures: list[Any] = []

    # life_facts / signatures / transactions
    async def get(self, db: Any, user_id: int, fact_id: int) -> LifeFact:
        return self.job

    async def list_for_fact(self, db: Any, user_id: int, fact_id: int) -> list[Any]:
        return list(self.signatures)

    async def replace_for_fact(
        self, db: Any, user_id: int, fact_id: int, sigs: list[Any]
    ) -> list[Any]:
        self.calls.append("replace_for_fact")
        self.signatures = list(sigs)
        return sigs

    async def list_effective(self, db: Any, user_id: int, since: date, until: date) -> list[TxView]:
        return list(self.txs.values())

    async def save_evaluation(self, db: Any, user_id: int, tx_id: int, ev: Any) -> TxView:
        self.calls.append(f"save_evaluation {tx_id}")
        self.txs[tx_id] = self.txs[tx_id].replace(
            **ev.model_dump(
                exclude={
                    "goal_impact",
                    "question_hint",
                    "confidence",
                    "annotation_source",
                    "merchant",
                }
            ),
            annotation_source=ev.annotation_source,
        )
        return self.txs[tx_id]

    # engine
    async def recompute_baselines(self, db: Any, user_id: int) -> dict[str, Any]:
        self.calls.append("recompute_baselines")
        return {}

    async def on_annotation_changed(
        self, db: Any, user_id: int, tx_id: int, old: Any, new: Any
    ) -> None:
        self.calls.append(f"on_annotation_changed {tx_id} {old.effective_amount}->"
                          f"{new.effective_amount}")  # fmt: skip

    async def recompute_plan(self, db: Any, user_id: int, reason: str, ref: Any) -> PlanSummary:
        self.version += 1
        self.calls.append(f"recompute_plan {reason}")
        return PlanSummary(version=self.version, feasible=True, today_budget=Decimal(150),
                           next_7_days=(), reason=reason)  # fmt: skip

    async def forecast_goal(self, db: Any, user_id: int, version: int) -> Forecast:
        self.calls.append(f"forecast_goal {version}")
        return Forecast(probability=0.7, p10=Decimal(1), p50=Decimal(2), p90=Decimal(3))


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> _World:
    w = _World(andrei_ctx(), [asked_tv()], andrei_ctx().facts[0])
    monkeypatch.setattr(propagate, "_service", lambda name: w)
    monkeypatch.setattr(propagate, "_engine", lambda name: getattr(w, name))

    async def context(db: Any, user_id: int, today: date) -> UserContext:
        return w.ctx  # read at call time: a test may replace it

    monkeypatch.setattr(service, "_context", context)
    return w


async def test_on_fact_changed_runs_the_whole_chain(world: _World) -> None:
    with clock.use_clock(clock.FixedClock(at(TODAY, 10))):
        result = await service.on_fact_changed(None, 2, 11)
    assert result.changed_transaction_ids == (500,)
    assert result.household_scale == Decimal("1.5")
    assert result.plan is not None
    assert result.plan.version == 8
    assert result.forecast is not None
    assert result.forecast.probability == 0.7
    assert world.calls == [
        "replace_for_fact",
        "recompute_baselines",
        "save_evaluation 500",
        "on_annotation_changed 500 4500.00->4500.00",  # the ledger does not move
        "recompute_plan fact: occupation Sunt analist sportiv, lucrez de acasă",
        "forecast_goal 8",
    ]
    assert world.txs[500].purpose is Purpose.WORK_TOOL
    assert any(s.category == "electronics" for s in world.signatures)
    with clock.use_clock(clock.FixedClock(at(TODAY, 10))):  # twice: nothing more to re-read
        again = await service.on_fact_changed(None, 2, 11)
    assert again.changed_transaction_ids == ()
    assert again.plan is not None
    assert again.plan.version == 9


async def test_the_tool_path_leaves_the_plan_to_the_executor(world: _World) -> None:
    from app.agent.ports import LazyContext

    with clock.use_clock(clock.FixedClock(at(TODAY, 10))):
        result = await LazyContext().on_fact_changed(None, 2, 11)
    assert result is not None
    assert result.changed_transaction_ids == (500,)
    assert result.plan is None
    assert not any(call.startswith("recompute_plan") for call in world.calls)


async def test_an_expired_fact_loses_its_signatures(world: _World) -> None:
    world.job = world.job.replace(status=FactStatus.EXPIRED)
    world.ctx = without_job(world.ctx)
    with clock.use_clock(clock.FixedClock(at(TODAY, 10))):
        result = await propagate.reevaluate_after_fact(None, 2, 11)
    assert world.signatures == []
    assert result.changed_transaction_ids == ()  # the TV was still a waiting question
