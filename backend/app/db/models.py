"""Every table of arch §4 (4.1 + 4.2 + 4.4) and plan_preferences (6.7).

Conventions (B2): money NUMERIC(12,2); JSON as JSONB; times timestamptz from `app.clock.now()`
(never the DB clock: the simulator owns "now"); enums as text + CHECK generated from
`app.domain.enums`, so adding a value there is the only change. Deleting a user removes every
row it owns (ON DELETE CASCADE), which `/sim/reset` relies on.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app import clock
from app.domain import enums as e

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Money = Numeric(12, 2)
Score = Numeric(5, 4)  # 0–1 scores and confidences, 4 decimals


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def enum_in(column: str, enum: type[StrEnum]) -> str:
    """`column IN ('a', 'b', …)`; NULL passes (nullable columns stay optional)."""
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"


def enum_check(column: str, enum: type[StrEnum]) -> CheckConstraint:
    """Named `ck_<table>_<column>` by the naming convention. Changing the enum needs a migration
    with `app.db.migration_helpers.replace_enum_check` (autogenerate doesn't see CHECKs)."""
    return CheckConstraint(enum_in(column, enum), name=column)


def _now() -> datetime:
    return clock.now()


def user_fk() -> Any:
    return ForeignKey("users.id", ondelete="CASCADE")


def created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=_now, nullable=False)


# ── 4.1 / 4.2: profile & plan inputs ──────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        enum_check("language", e.Language),
        enum_check("coach_style", e.CoachStyle),
        CheckConstraint("household_scale >= 1", name="household_scale"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    keycloak_sub: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    age: Mapped[int | None]
    language: Mapped[str] = mapped_column(String(2), default=e.Language.RO)
    coach_style: Mapped[str] = mapped_column(String(10), default=e.CoachStyle.WARM)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Bucharest")
    city: Mapped[str | None] = mapped_column(String(100))
    household_scale: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("1.00"))
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()


class Account(Base):
    __tablename__ = "accounts"

    user_id: Mapped[int] = mapped_column(user_fk(), primary_key=True)
    current_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    # kept for compatibility: mirrors the goal pot's `saved` (arch 4.4)
    savings_pot: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))


class Goal(Base):
    __tablename__ = "goals"
    __table_args__ = (
        enum_check("status", e.GoalStatus),
        CheckConstraint("amount > 0", name="amount_positive"),
        # one active goal per user (D17)
        Index(
            "uq_goals_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk(), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    deadline: Mapped[date] = mapped_column(Date)
    motivation: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default=e.GoalStatus.ACTIVE)
    # soft: the deadline may move (E9 offers "move the deadline" only for soft goals)
    soft: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = created_at()


class IncomeSource(Base):
    __tablename__ = "income_sources"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("day_of_month BETWEEN 1 AND 31", name="day_of_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk(), index=True)
    source: Mapped[str] = mapped_column(String(100))
    amount: Mapped[Decimal] = mapped_column(Money)
    day_of_month: Mapped[int] = mapped_column(Integer)


class FixedCost(Base):
    __tablename__ = "fixed_costs"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("day_of_month BETWEEN 1 AND 31", name="day_of_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk(), index=True)
    name: Mapped[str] = mapped_column(String(100))
    amount: Mapped[Decimal] = mapped_column(Money)
    day_of_month: Mapped[int] = mapped_column(Integer)


class LifeEvent(Base):
    __tablename__ = "life_events"
    __table_args__ = (
        enum_check("type", e.LifeEventType),
        enum_check("status", e.LifeEventStatus),
        CheckConstraint("est_cost >= 0", name="est_cost_not_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk(), index=True)
    name: Mapped[str] = mapped_column(String(200))
    date: Mapped[date] = mapped_column(Date)
    est_cost: Mapped[Decimal] = mapped_column(Money)
    type: Mapped[str] = mapped_column(String(20))
    source: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(10), default=e.LifeEventStatus.PLANNED)


class LifeProfile(Base):
    """Soft coaching notes only (arch 4.3 v0.8); facts live in life_facts."""

    __tablename__ = "life_profile"

    user_id: Mapped[int] = mapped_column(user_fk(), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class PlanPreferences(Base):
    __tablename__ = "plan_preferences"
    __table_args__ = (CheckConstraint("buffer_pct BETWEEN 0 AND 0.3", name="buffer_pct"),)

    user_id: Mapped[int] = mapped_column(user_fk(), primary_key=True)
    weekday_weights: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    pinned_days: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    category_caps: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    buffer_pct: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0.10"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Product(Base):
    """Mock product catalogue (data/products.json); `id` is the file's slug."""

    __tablename__ = "products"
    __table_args__ = (
        enum_check("kind", e.ProductKind),
        enum_check("liquidity", e.Liquidity),
        CheckConstraint("min_months <= max_months", name="months_range"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20))
    rate: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    liquidity: Mapped[str] = mapped_column(String(10))
    description: Mapped[str | None] = mapped_column(Text)
    min_months: Mapped[int | None]
    max_months: Mapped[int | None]
    mock: Mapped[bool] = mapped_column(Boolean, default=True)


class SimClock(Base):
    """The demo's fake "now" (one row, id = 1)."""

    __tablename__ = "sim_clock"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(primary_key=True, default=1, autoincrement=False)
    today: Mapped[date] = mapped_column(Date)


# ── 4.1 / 4.4: money flow ────────────────────────────────────────────────────────────────


def _amount_default(context: Any) -> Any:
    """effective_amount = amount until the transaction is annotated (arch F2)."""
    return context.get_current_parameters()["amount"]


class Transaction(Base):
    """The queue (D4): unresolved → processing → resolved | failed."""

    __tablename__ = "transactions"
    __table_args__ = (
        enum_check("status", e.TransactionStatus),
        enum_check("source", e.TransactionSource),
        enum_check("direction", e.Direction),
        enum_check("category", e.Category),
        enum_check("purpose", e.Purpose),
        enum_check("beneficiary", e.Beneficiary),
        enum_check("annotation_source", e.AnnotationSource),
        enum_check("decision", e.Decision),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("effective_amount BETWEEN 0 AND amount", name="effective_amount_range"),
        Index(None, "user_id", "status"),
        Index(None, "user_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk())
    amount: Mapped[Decimal] = mapped_column(Money)
    direction: Mapped[str] = mapped_column(String(6), default=e.Direction.DEBIT)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    merchant_raw: Mapped[str] = mapped_column(String(200))
    mcc: Mapped[str | None] = mapped_column(String(4))
    items: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(4), default=e.TransactionSource.SIM)
    # queue
    status: Mapped[str] = mapped_column(String(10), default=e.TransactionStatus.UNRESOLVED)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()
    # evaluation / annotation (arch 4.4, 5.3.4)
    merchant_id: Mapped[str | None] = mapped_column(ForeignKey("merchants.id", ondelete="SET NULL"))
    merchant: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str | None] = mapped_column(String(20))
    effective_amount: Mapped[Decimal] = mapped_column(Money, default=_amount_default)
    purpose: Mapped[str | None] = mapped_column(String(30))
    beneficiary: Mapped[str | None] = mapped_column(String(10))
    annotation_source: Mapped[str | None] = mapped_column(String(10))
    annotation_confidence: Mapped[Decimal | None] = mapped_column(Score)
    explanation: Mapped[str | None] = mapped_column(Text)
    life_fit: Mapped[Decimal | None] = mapped_column(Score)
    anomaly_score: Mapped[Decimal | None] = mapped_column(Score)
    unexplained: Mapped[Decimal | None] = mapped_column(Score)
    decision: Mapped[str | None] = mapped_column(String(10))
    matched_fact_id: Mapped[int | None] = mapped_column(
        ForeignKey("life_facts.id", ondelete="SET NULL")
    )
    matched_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("pattern_rules.id", ondelete="SET NULL")
    )
    pot_id: Mapped[int | None] = mapped_column(ForeignKey("pots.id", ondelete="SET NULL"))
    # receivables.transaction_id points back here: the cycle is closed with ALTER TABLE
    receivable_id: Mapped[int | None] = mapped_column(
        ForeignKey("receivables.id", ondelete="SET NULL", use_alter=True)
    )


class DayLedger(Base):
    __tablename__ = "day_ledger"
    __table_args__ = (enum_check("status", e.LedgerStatus),)

    user_id: Mapped[int] = mapped_column(user_fk(), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    budget: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    spent: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(10), default=e.LedgerStatus.OK)


class Plan(Base):
    """Every plan version is kept (arch 4.1)."""

    __tablename__ = "plans"
    __table_args__ = (Index(None, "user_id", "version", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk())
    version: Mapped[int] = mapped_column(Integer)
    feasible: Mapped[bool] = mapped_column(Boolean)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    reason: Mapped[str | None] = mapped_column(Text)
    trigger_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at()


class Slip(Base):
    __tablename__ = "slips"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk(), index=True)
    date: Mapped[date] = mapped_column(Date)
    amount_over: Mapped[Decimal] = mapped_column(Money)
    reason: Mapped[str | None] = mapped_column(String(100))
    detail: Mapped[str | None] = mapped_column(Text)
    recurring: Mapped[bool] = mapped_column(Boolean, default=False)


class Reflection(Base):
    __tablename__ = "reflections"
    __table_args__ = (CheckConstraint("motivation BETWEEN 1 AND 5", name="motivation"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk(), index=True)
    week_start: Mapped[date] = mapped_column(Date)
    motivation: Mapped[int | None]
    answer: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)


class Transfer(Base):
    """Money moved to savings: by `transfer_to_savings` or the payday auto-save (D37)."""

    __tablename__ = "transfers"
    __table_args__ = (
        enum_check("kind", e.TransferKind),
        CheckConstraint("amount > 0", name="amount_positive"),
        # one auto-save per salary transaction: a re-run of the pipeline can't save twice
        Index(
            "uq_transfers_one_auto_save_per_income",
            "income_transaction_id",
            unique=True,
            postgresql_where=text("kind = 'auto_save'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk(), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    kind: Mapped[str] = mapped_column(String(10), default=e.TransferKind.MANUAL)
    pot_id: Mapped[int | None] = mapped_column(ForeignKey("pots.id", ondelete="SET NULL"))
    income_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = created_at()
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ── 4.1 / 4.2 / 4.4: conversation ────────────────────────────────────────────────────────

# Dedup (arch 4.4): transaction-level events are unique per transaction, every other type is
# unique per day. Adding an AgentEventType means putting it in one of these two groups.
TRANSACTION_EVENT_TYPES: tuple[e.AgentEventType, ...] = (e.AgentEventType.TRANSACTION_QUESTION,)
DAY_LEVEL_EVENT_TYPES: tuple[e.AgentEventType, ...] = tuple(
    t for t in e.AgentEventType if t not in TRANSACTION_EVENT_TYPES
)


def _in(values: tuple[StrEnum, ...]) -> str:
    return "type IN (" + ", ".join(f"'{v.value}'" for v in values) + ")"


class AgentEvent(Base):
    """Something worth talking about: pending → asked → answered / handled / expired."""

    __tablename__ = "agent_events"
    __table_args__ = (
        enum_check("type", e.AgentEventType),
        enum_check("status", e.AgentEventStatus),
        CheckConstraint(
            f"NOT ({_in(TRANSACTION_EVENT_TYPES)}) OR ref_transaction_id IS NOT NULL",
            name="transaction_event_has_ref",
        ),
        Index(
            "uq_agent_events_day_level",
            "user_id",
            "type",
            "event_date",
            unique=True,
            postgresql_where=text(_in(DAY_LEVEL_EVENT_TYPES)),
        ),
        Index(
            "uq_agent_events_transaction_level",
            "user_id",
            "type",
            "ref_transaction_id",
            unique=True,
            postgresql_where=text(_in(TRANSACTION_EVENT_TYPES)),
        ),
        Index(None, "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk())
    type: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(10), default=e.AgentEventStatus.PENDING)
    # the Bucharest (sim) day the event belongs to; stored so the unique index can use it
    event_date: Mapped[date] = mapped_column(Date)
    ref_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = created_at()
    asked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        enum_check("role", e.MessageRole),
        enum_check("input_mode", e.InputMode),
        Index(None, "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk())
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    quick_replies: Mapped[list[str]] = mapped_column(JSONB, default=list)
    action_cards: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    input_mode: Mapped[str | None] = mapped_column(String(12))
    speak: Mapped[bool] = mapped_column(Boolean, default=False)
    speak_text: Mapped[str | None] = mapped_column(Text)
    agent_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_events.id", ondelete="SET NULL")
    )
    ref_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = created_at()


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index(None, "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk())
    type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    opens_chat: Mapped[bool] = mapped_column(Boolean, default=False)
    agent_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_events.id", ondelete="SET NULL")
    )
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at()


class AgentRun(Base):
    """One row per agent loop (audit, B15). Never stores prompts or transcripts (Q27)."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        enum_check("trigger", e.AgentTrigger),
        enum_check("status", e.AgentRunStatus),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk(), index=True)
    trigger: Mapped[str] = mapped_column(String(10))
    model: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(10), default=e.AgentRunStatus.RUNNING)
    iterations: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ToolCall(Base):
    __tablename__ = "tool_calls"
    __table_args__ = (enum_check("status", e.ToolCallStatus),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(user_fk())
    tool_name: Mapped[str] = mapped_column(String(64))
    input: Mapped[dict[str, Any]] = mapped_column(JSONB)
    output: Mapped[Any] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(5))
    created_at: Mapped[datetime] = created_at()


# ── 4.4: life context & savings ──────────────────────────────────────────────────────────


class LifeFact(Base):
    """One statement about the person's life (arch 5.3)."""

    __tablename__ = "life_facts"
    __table_args__ = (
        enum_check("type", e.FactType),
        enum_check("source", e.FactSource),
        enum_check("status", e.FactStatus),
        enum_check("persistence", e.Persistence),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence"),
        CheckConstraint("valid_to >= valid_from", name="validity_window"),
        CheckConstraint(
            "persistence <> 'temporary' OR valid_to IS NOT NULL", name="temporary_has_end"
        ),
        Index(None, "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk())
    type: Mapped[str] = mapped_column(String(20))
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    text: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(12), default=e.FactStatus.CONFIRMED)
    confidence: Mapped[Decimal] = mapped_column(Score, default=Decimal("0.95"))
    persistence: Mapped[str] = mapped_column(String(10), default=e.Persistence.PERMANENT)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    evidence: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class SpendingSignature(Base):
    """What a fact predicts about spending (arch 5.3.3)."""

    __tablename__ = "spending_signatures"
    __table_args__ = (
        enum_check("effect", e.SignatureEffect),
        enum_check("category", e.Category),
        enum_check("purpose", e.Purpose),
        enum_check("origin", e.SignatureOrigin),
        CheckConstraint("strength BETWEEN 0 AND 1", name="strength"),
        CheckConstraint("amount_min <= amount_max", name="amount_range"),
        CheckConstraint("multiplier > 0", name="multiplier_positive"),
        CheckConstraint("replacement_cycle_days > 0", name="replacement_cycle_positive"),
        Index(None, "user_id", "active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk())
    fact_id: Mapped[int] = mapped_column(
        ForeignKey("life_facts.id", ondelete="CASCADE"), index=True
    )
    effect: Mapped[str] = mapped_column(String(20))
    category: Mapped[str | None] = mapped_column(String(20))
    merchant_hints: Mapped[list[str]] = mapped_column(JSONB, default=list)
    item_keywords: Mapped[list[str]] = mapped_column(JSONB, default=list)
    amount_min: Mapped[Decimal | None] = mapped_column(Money)
    amount_max: Mapped[Decimal | None] = mapped_column(Money)
    multiplier: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    time_window: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    expected_date: Mapped[date | None] = mapped_column(Date)
    expected_amount: Mapped[Decimal | None] = mapped_column(Money)
    replacement_cycle_days: Mapped[int | None]
    purpose: Mapped[str] = mapped_column(String(30))
    strength: Mapped[Decimal] = mapped_column(Score)
    origin: Mapped[str] = mapped_column(String(10))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = created_at()


class PatternRule(Base):
    """A learned pattern: "every Friday is lunch with the team" (arch 5.3.7)."""

    __tablename__ = "pattern_rules"
    __table_args__ = (
        enum_check("kind", e.RuleKind),
        enum_check("source", e.RuleSource),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence"),
        Index(None, "user_id", "active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk())
    kind: Mapped[str] = mapped_column(String(10))
    match: Mapped[dict[str, Any]] = mapped_column(JSONB)
    outcome: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    confidence: Mapped[Decimal] = mapped_column(Score)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    misses: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(10))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = created_at()
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Receivable(Base):
    """Money other people owe the user; the payment request is a mock (D31)."""

    __tablename__ = "receivables"
    __table_args__ = (
        enum_check("status", e.ReceivableStatus),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("people_count > 0", name="people_count_positive"),
        Index(None, "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk())
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL")
    )
    amount: Mapped[Decimal] = mapped_column(Money)
    debtor_label: Mapped[str] = mapped_column(String(100))
    people_count: Mapped[int | None]
    amount_each: Mapped[Decimal | None] = mapped_column(Money)
    expected_by: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(10), default=e.ReceivableStatus.OPEN)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()


class Pot(Base):
    """A named savings pot; the goal has its own (kind = goal)."""

    __tablename__ = "pots"
    __table_args__ = (
        enum_check("kind", e.PotKind),
        enum_check("status", e.PotStatus),
        CheckConstraint("target > 0", name="target_positive"),
        CheckConstraint("saved >= 0", name="saved_not_negative"),
        CheckConstraint("monthly_contribution >= 0", name="contribution_not_negative"),
        Index(
            "uq_pots_one_per_goal",
            "goal_id",
            unique=True,
            postgresql_where=text("kind = 'goal'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk(), index=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(10))
    goal_id: Mapped[int | None] = mapped_column(ForeignKey("goals.id", ondelete="SET NULL"))
    life_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("life_events.id", ondelete="SET NULL")
    )
    fact_id: Mapped[int | None] = mapped_column(ForeignKey("life_facts.id", ondelete="SET NULL"))
    target: Mapped[Decimal] = mapped_column(Money)
    saved: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    deadline: Mapped[date | None] = mapped_column(Date)
    monthly_contribution: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(10), default=e.PotStatus.ACTIVE)
    created_at: Mapped[datetime] = created_at()


class GoalForecast(Base):
    """Goal probability history: "81%, vs 72% last week" (arch 6.7)."""

    __tablename__ = "goal_forecasts"
    __table_args__ = (
        CheckConstraint("probability BETWEEN 0 AND 1", name="probability"),
        CheckConstraint("p10 <= p50 AND p50 <= p90", name="percentiles_ordered"),
        Index(None, "user_id", "computed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk())
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"))
    plan_version: Mapped[int] = mapped_column(Integer)
    sim_date: Mapped[date] = mapped_column(Date)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    probability: Mapped[Decimal] = mapped_column(Score)
    p10: Mapped[Decimal] = mapped_column(Money)
    p50: Mapped[Decimal] = mapped_column(Money)
    p90: Mapped[Decimal] = mapped_column(Money)
    expected_reach_date: Mapped[date | None] = mapped_column(Date)
    drivers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    options: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    is_weekly_snapshot: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(Text)


class CategoryBaseline(Base):
    """Cached per-category baselines, recomputed by the engine (arch 5.3.5)."""

    __tablename__ = "category_baselines"
    __table_args__ = (enum_check("category", e.Category),)

    user_id: Mapped[int] = mapped_column(user_fk(), primary_key=True)
    category: Mapped[str] = mapped_column(String(20), primary_key=True)
    personal_median: Mapped[Decimal | None] = mapped_column(Money)
    personal_mad: Mapped[Decimal | None] = mapped_column(Money)
    n: Mapped[int] = mapped_column(Integer, default=0)
    prior_median: Mapped[Decimal | None] = mapped_column(Money)
    household_multiplier: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("1"))
    expected_median: Mapped[Decimal | None] = mapped_column(Money)
    monthly_expected: Mapped[Decimal | None] = mapped_column(Money)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Merchant(Base):
    """Merchant catalogue (data/merchants.json); `id` is the file's slug, e.g. "mega_image"."""

    __tablename__ = "merchants"
    __table_args__ = (enum_check("category", e.Category),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(100), unique=True)
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list)
    category: Mapped[str] = mapped_column(String(20))
    mcc: Mapped[str | None] = mapped_column(String(4))
    typical_basket: Mapped[Decimal | None] = mapped_column(Money)
    multi_category: Mapped[bool] = mapped_column(Boolean, default=False)


# ── the app API (David V.'s Flutter contract): push devices ───────────────────────────────


class DevicePlatform(StrEnum):
    """`POST /devices` platform (API_SPEC.md). Lives here, not in app.domain.enums: it's an
    app-transport value, not part of the architecture's domain."""

    ANDROID = "android"
    IOS = "ios"


class Device(Base):
    """A phone's FCM token. Owned by a login (`user_sub` = users.keycloak_sub), not by a users
    row: `/sim/reset` deletes and re-creates every user with a new id, and the phone's
    registration must survive that (no FK, so no cascade)."""

    __tablename__ = "devices"
    __table_args__ = (enum_check("platform", DevicePlatform),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fcm_token: Mapped[str] = mapped_column(String(512), unique=True)  # FCM tokens are ~160 chars
    platform: Mapped[str] = mapped_column(String(7))
    user_sub: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
