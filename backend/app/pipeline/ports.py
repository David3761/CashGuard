"""The teammates' functions the platform calls (arch 15.1), in one place (bomboe's B8 ports).

Since the integration these are the real modules: the context layer (C6/C7, async shells), the
engine (danutu's E1-E13, async shells) and the agent (A6/A7, async). Where a caller's expected
signature differs from ours, the adapter is here, not in the callers (`apply_annotation`,
`on_fact_changed` and `rank_products` are ours now: A3, C9, C12).
Tests replace these attributes (monkeypatch) to spy on the calls.
"""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.agent import templates
from app.agent.handlers.transactions import apply_annotation as agent_apply_annotation
from app.agent.language import detect_language as detect_language
from app.agent.loop import run_agent as run_agent
from app.agent.pg_ports import pg_services
from app.agent.proactive import run_proactive as run_proactive
from app.context import products as c12
from app.context import questions
from app.context import service as context_service
from app.context.service import evaluate_transaction as evaluate_transaction
from app.context.service import infer_hypotheses as infer_hypotheses
from app.context.service import pick_question as pick_question
from app.context.service import signatures_for_fact as signatures_for_fact
from app.domain import models as dm
from app.domain.enums import AnnotationSource, Beneficiary, Category, Purpose
from app.domain.models import TxView
from app.domain.money import to_money
from app.domain.results import PropagationResult
from app.domain.user_context import UserContext
from app.engine.service import apply_transaction as apply_transaction
from app.engine.service import auto_save as auto_save
from app.engine.service import forecast_goal as forecast_goal
from app.engine.service import recompute_baselines as recompute_baselines
from app.engine.service import recompute_plan as recompute_plan
from app.i18n import format as i18n_format
from app.i18n import labels as i18n_labels
from app.services import transactions


async def apply_annotation(
    db: AsyncSession,
    user_id: int,
    tx_id: int,
    purpose: Purpose,
    beneficiary: Beneficiary,
    own_amount: Decimal | None = None,
    people_count: int | None = None,
    others_will_repay: bool = False,
    debtor_label: str | None = None,
    source: AnnotationSource = AnnotationSource.USER_EDIT,
) -> TxView:
    """Our A3 `apply_annotation` (the tool's logic: own share, receivable, ledger delta through
    the engine, C8 learning, the open question answered) on bomboe's Postgres services; his
    callers get the annotated transaction back."""
    await agent_apply_annotation(
        db,
        user_id,
        tx_id,
        purpose,
        beneficiary,
        own_amount=own_amount,
        people_count=people_count,
        others_will_repay=others_will_repay,
        debtor_label=debtor_label,
        source=source,
        services=pg_services(db),
    )
    return await transactions.get(db, user_id, tx_id)


async def on_fact_changed(db: AsyncSession, user_id: int, fact_id: int) -> PropagationResult:
    """C9 (`app.context.service.on_fact_changed`): re-read the last 30 days, re-plan, forecast."""
    return await context_service.on_fact_changed(db, user_id, fact_id)


def rank_products(ctx: UserContext, items: list[dm.Product]) -> list[tuple[dm.Product, str | None]]:
    """C12 (`app.context.products.rank_products`): the products ranked for this person, each
    with its reason in the user's language."""
    by_id = {p.id: p for p in items}
    lang = ctx.profile.language
    ranked = c12.rank_products(ctx, items, clock.today())
    return [(by_id[r.product.id], r.why(lang)) for r in ranked if r.product.id in by_id]


def default_reading(tx: TxView) -> tuple[Purpose, float]:
    """C7's default reading as (purpose, confidence), the shape B11's expiry job stores."""
    reading = questions.default_reading(tx)
    return reading.purpose, reading.confidence


def fallback_reply(language: str) -> str:
    """Our A-templates fallback for a failed agent run (`fallback_reply("llm_down", lang)`)."""
    return templates.fallback_reply("llm_down", language)


def label(value: str | None, lang: str) -> str | None:
    """C1's label of a category / purpose / beneficiary value; None stays None, an unknown
    value is shown as itself."""
    if value is None:
        return None
    for enum in (Category, Purpose, Beneficiary):
        try:
            return i18n_labels.label(enum(value), lang)
        except ValueError:
            continue
    return str(value)


def format_money(amount: Decimal | float | int, lang: str) -> str:
    """C1's display form ("500 lei", "30,40 lei"), half-up to the cent first."""
    return i18n_format.format_money(to_money(amount), lang)
