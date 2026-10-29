"""C7: the question policy (arch 5.3.6, D25, D49), pure.

- At most 1 question a day across every `QUESTION_EVENT_TYPES` source (receivable_reminder,
  hypotheses and inform cards never count) and at most 4 a week (ISO week, soft cap).
- Quiet hours 22:00-08:00 (Bucharest) queue the question; off in sim_mode.
- priority = unexplained x goal_impact; ties: the older transaction first, then the lower id.
  The others become ask_later; a candidate older than 48 h expires with the default reading.
- Back-off: the last 2 asked questions both ignored → 1 question every 2 days for 7 days.
- Skipped: a transaction already answered or already asked about, or matched by a suppress rule.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Final

from app.clock import APP_TZ
from app.context.life_fit import best_rule
from app.domain.enums import (
    QUESTION_EVENT_TYPES,
    AgentEventStatus,
    AnnotationSource,
    Beneficiary,
    Category,
    Decision,
    Purpose,
    RuleKind,
)
from app.domain.models import AgentEventView, TxView
from app.domain.results import Evaluation, QuestionCandidate
from app.domain.user_context import UserContext

DAILY_CAP: Final = 1
WEEKLY_CAP: Final = 4
QUIET_FROM: Final = time(22, 0)
QUIET_TO: Final = time(8, 0)
ASK_LATER_HOURS: Final = 48
IGNORED_AFTER: Final = timedelta(hours=24)
BACKOFF_DAYS: Final = 7
BACKOFF_GAP_DAYS: Final = 2
DEFAULT_CONFIDENCE: Final = 0.3


@dataclass(frozen=True, slots=True)
class BudgetState:
    """How much of the question budget is used on `today`."""

    asked_today: int
    asked_this_week: int
    last_asked_on: date | None
    backoff_until: date | None  # exclusive

    def allows(self, today: date) -> bool:
        if self.asked_today >= DAILY_CAP or self.asked_this_week >= WEEKLY_CAP:
            return False
        if self.backoff_until is not None and today < self.backoff_until:
            gap = (today - self.last_asked_on).days if self.last_asked_on else BACKOFF_GAP_DAYS
            return gap >= BACKOFF_GAP_DAYS
        return True


@dataclass(frozen=True, slots=True)
class QuestionPlan:
    """What to do with today's candidates: ask one, keep the rest, expire the old ones."""

    ask: QuestionCandidate | None
    ask_later: tuple[QuestionCandidate, ...]
    expired: tuple[QuestionCandidate, ...]


def _local_day(moment: datetime) -> date:
    return moment.astimezone(APP_TZ).date()


def _question_events(ctx: UserContext) -> list[AgentEventView]:
    events = {e.id: e for e in (*ctx.recent_questions, *ctx.agent_events)}
    asked = [e for e in events.values() if e.type in QUESTION_EVENT_TYPES and e.asked_at]
    return sorted(asked, key=lambda e: (e.asked_at or e.created_at, e.id))


def _ignored(event: AgentEventView, now: datetime) -> bool:
    if event.answered_at is not None or event.status is AgentEventStatus.ANSWERED:
        return False
    if event.status is AgentEventStatus.EXPIRED:
        return True
    return event.asked_at is not None and now - event.asked_at >= IGNORED_AFTER


def budget_state(ctx: UserContext, today: date, now: datetime | None = None) -> BudgetState:
    """The day's and the ISO week's question count, and the back-off window (5.3.6 #1, #5)."""
    events = _question_events(ctx)
    days = [_local_day(e.asked_at) for e in events if e.asked_at is not None]
    asked_today = max(ctx.questions_asked_today, sum(1 for d in days if d == today))
    week = today.isocalendar()[:2]
    asked_this_week = sum(1 for d in days if d.isocalendar()[:2] == week)
    backoff_until = None
    if now is not None and len(events) >= 2 and all(_ignored(e, now) for e in events[-2:]):
        backoff_until = days[-1] + timedelta(days=BACKOFF_DAYS)
    return BudgetState(
        asked_today=asked_today,
        asked_this_week=asked_this_week,
        last_asked_on=days[-1] if days else None,
        backoff_until=backoff_until,
    )


def is_quiet(now: datetime, sim_mode: bool) -> bool:
    """22:00-08:00 Bucharest time is quiet (22:00 and 07:59 are, 08:00 isn't); never in sim."""
    if sim_mode:
        return False
    local = now.astimezone(APP_TZ).time()
    return local >= QUIET_FROM or local < QUIET_TO


def _skipped(candidate: QuestionCandidate, ctx: UserContext) -> bool:
    for event in (*ctx.recent_questions, *ctx.agent_events):
        if event.ref_transaction_id == candidate.transaction_id and (
            event.asked_at is not None or event.status is AgentEventStatus.ANSWERED
        ):
            return True
    tx = next((t for t in ctx.transactions if t.id == candidate.transaction_id), None)
    if tx is None:
        return False
    if tx.annotation_source in (AnnotationSource.ANSWER, AnnotationSource.USER_EDIT):
        return True
    return best_rule(ctx.rules, tx, RuleKind.SUPPRESS) is not None


def _order(candidates: Iterable[QuestionCandidate]) -> list[QuestionCandidate]:
    return sorted(candidates, key=lambda c: (-c.priority, c.occurred_at, c.transaction_id))


def plan_questions(
    candidates: Iterable[QuestionCandidate], ctx: UserContext, now: datetime, sim_mode: bool
) -> QuestionPlan:
    """Split today's candidates into the one to ask (if any), ask_later and expired."""
    live: list[QuestionCandidate] = []
    expired: list[QuestionCandidate] = []
    for candidate in candidates:
        if _skipped(candidate, ctx):
            continue
        too_old = now - candidate.occurred_at > timedelta(hours=ASK_LATER_HOURS)
        (expired if too_old else live).append(candidate)
    ordered = _order(live)
    today = _local_day(now)
    can_ask = bool(ordered) and not is_quiet(now, sim_mode)
    if can_ask and budget_state(ctx, today, now).allows(today):
        return QuestionPlan(ordered[0], tuple(ordered[1:]), tuple(_order(expired)))
    return QuestionPlan(None, tuple(ordered), tuple(_order(expired)))


def pick_question(
    candidates: Iterable[QuestionCandidate], ctx: UserContext, now: datetime, sim_mode: bool
) -> QuestionCandidate | None:
    """The one question to ask now, or None (budget used, quiet hours, nothing to ask)."""
    return plan_questions(candidates, ctx, now, sim_mode).ask


def default_reading(tx: TxView) -> Evaluation:
    """The reading when nobody answered (5.3.6 #7): the whole amount, unplanned_discretionary,
    confidence 0.3, source default; editable from the feed."""
    return Evaluation(
        category=tx.category or Category.OTHER,
        merchant_id=tx.merchant_id,
        merchant=tx.merchant,
        purpose=Purpose.UNPLANNED_DISCRETIONARY,
        beneficiary=Beneficiary.SELF,
        effective_amount=tx.amount,
        annotation_source=AnnotationSource.DEFAULT,
        confidence=DEFAULT_CONFIDENCE,
        life_fit=tx.life_fit or 0.0,
        anomaly_score=tx.anomaly_score or 0.0,
        unexplained=tx.unexplained or 0.0,
        decision=Decision.AUTO,
    )
