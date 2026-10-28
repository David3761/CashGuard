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


def enum_check(column: str, enum: type[StrEnum]) -> CheckConstraint:
    """`column IN ('a', 'b', …)`; NULL passes (nullable columns stay optional)."""
    values = ", ".join(f"'{member.value}'" for member in enum)
    return CheckConstraint(f"{column} IN ({values})", name=column)


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
    merchant_id: Mapped[str | None] = mapped_column(String(64))  # FK added with merchants
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
    # links to the life-context tables (FKs added in step 4)
    matched_fact_id: Mapped[int | None]
    matched_rule_id: Mapped[int | None]
    pot_id: Mapped[int | None]
    receivable_id: Mapped[int | None]


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
    pot_id: Mapped[int | None]  # FK added with pots
    income_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = created_at()
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
