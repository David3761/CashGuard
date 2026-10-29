"""`UserContext`: the AI's view of one user, built by bomboe's B4 `load_user_context` (F2 step 8).

Its own module because it needs both `models` and `results` (one file would be an import cycle,
plan R5). Every pure core takes it; the extras beyond B4's list default to empty, so B4's stub
can leave them out.
"""

from collections.abc import Mapping
from datetime import date as Date
from typing import Annotated, Self

from pydantic import Field, JsonValue, model_validator

from app.domain.enums import Category, FactStatus, PotKind
from app.domain.models import (
    Account,
    AgentEventView,
    Baseline,
    DomainModel,
    FixedCost,
    Goal,
    Id,
    IncomeSource,
    LedgerDay,
    LifeEvent,
    LifeFact,
    PatternRule,
    PlanPreferences,
    Pot,
    Product,
    Receivable,
    Reflection,
    Signature,
    Slip,
    TxView,
    UserProfile,
)
from app.domain.results import Forecast, PlanSummary


class UserContext(DomainModel):
    """One user's state on `as_of` (WB B4's content list + the plan's Q6 extras)."""

    user_id: Id
    as_of: Date  # the day the view was built for; cores still take `today` explicitly
    profile: UserProfile
    account: Account
    goal: Goal | None = None
    goal_pot: Pot | None = None
    income_sources: tuple[IncomeSource, ...] = ()
    fixed_costs: tuple[FixedCost, ...] = ()
    life_events: tuple[LifeEvent, ...] = ()  # planned
    pots: tuple[Pot, ...] = ()  # active
    receivables: tuple[Receivable, ...] = ()  # open / requested
    facts: tuple[LifeFact, ...] = ()  # confirmed and active on as_of
    hypotheses: tuple[LifeFact, ...] = ()
    signatures: tuple[Signature, ...] = ()  # active
    rules: tuple[PatternRule, ...] = ()  # active
    plan_preferences: PlanPreferences = PlanPreferences()
    baselines: Mapping[Category, Baseline] = Field(default_factory=dict)
    transactions: tuple[TxView, ...] = ()  # resolved, the last 180 days
    plan: PlanSummary | None = None
    forecast: Forecast | None = None
    last_weekly_forecast: Forecast | None = None
    agent_events: tuple[AgentEventView, ...] = ()  # pending / asked
    questions_asked_today: Annotated[int, Field(ge=0, strict=True)] = 0
    # Q6 extras (A4's snapshot 6.5, C7's weekly cap and back-off, C12):
    recent_questions: tuple[AgentEventView, ...] = ()  # question events of the last 7 days
    recent_days: tuple[LedgerDay, ...] = ()  # the last 14 days
    slips: tuple[Slip, ...] = ()  # the last 5
    reflections: tuple[Reflection, ...] = ()  # the last 5
    life_notes: Mapping[str, JsonValue] = Field(default_factory=dict)  # life_profile soft notes
    products: tuple[Product, ...] = ()

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        for fact in self.facts:
            if fact.status is not FactStatus.CONFIRMED or not fact.active_on(self.as_of):
                raise ValueError(f"fact {fact.id} is not confirmed and active on {self.as_of}")
        for fact in self.hypotheses:
            if fact.status is not FactStatus.HYPOTHESIS:
                raise ValueError(f"fact {fact.id} in hypotheses is {fact.status}")
        if self.goal_pot is not None and self.goal_pot.kind is not PotKind.GOAL:
            raise ValueError(f"goal_pot {self.goal_pot.id} is a {self.goal_pot.kind} pot")
        for category, baseline in self.baselines.items():
            if baseline.category is not category:
                raise ValueError(f"the baseline under {category} is for {baseline.category}")
        return self
