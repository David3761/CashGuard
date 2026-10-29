"""The teammates' functions the platform calls (arch 15.1), in one place (bomboe's B8 ports).

Since the integration these are the real modules: the context layer (C6/C7, async shells), the
engine (danutu's E1-E13, async shells) and the agent (A6/A7, async). Where a caller's expected
signature differs from ours, the adapter is here, not in the callers. Three stand-ins remain in
`_fallbacks.py` until their owners' versions are async or exist (TODO(INT) each).
Tests replace these attributes (monkeypatch) to spy on the calls.
"""

from decimal import Decimal

from app.agent import templates
from app.agent.language import detect_language as detect_language
from app.agent.loop import run_agent as run_agent
from app.agent.proactive import run_proactive as run_proactive
from app.context import questions
from app.context.service import evaluate_transaction as evaluate_transaction
from app.context.service import infer_hypotheses as infer_hypotheses
from app.context.service import pick_question as pick_question
from app.context.service import signatures_for_fact as signatures_for_fact
from app.domain.enums import Beneficiary, Category, Purpose
from app.domain.models import TxView
from app.domain.money import to_money
from app.engine.service import apply_transaction as apply_transaction
from app.engine.service import auto_save as auto_save
from app.engine.service import forecast_goal as forecast_goal
from app.engine.service import recompute_baselines as recompute_baselines
from app.engine.service import recompute_plan as recompute_plan
from app.i18n import format as i18n_format
from app.i18n import labels as i18n_labels
from app.pipeline import _fallbacks

# TODO(INT): our `app.agent.handlers.transactions.apply_annotation` is sync over the in-memory
# Services port; it replaces this stand-in once the async handler refactor lands (D42).
apply_annotation = _fallbacks.apply_annotation
# TODO(INT): ours (C9) is still a no-op stub; bomboe's stand-in re-plans, which /life-facts needs.
on_fact_changed = _fallbacks.on_fact_changed
# TODO(INT): C12 (`app.context.products.rank_products`) doesn't exist yet.
rank_products = _fallbacks.rank_products


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
