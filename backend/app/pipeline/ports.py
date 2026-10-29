"""The teammates' functions the pipeline calls (arch 15.1), in one place.

Each name is the real implementation when its module exists, else the stand-in from
`_fallbacks.py`. Tests replace these attributes (monkeypatch) to spy on the calls.
"""

# mypy: disable-error-code="no-redef,assignment,attr-defined,import-not-found,unused-ignore"

from app.pipeline import _fallbacks

try:
    from app.context.service import evaluate_transaction, pick_question
except ImportError:
    evaluate_transaction = _fallbacks.evaluate_transaction
    pick_question = _fallbacks.pick_question

try:
    from app.engine.service import apply_transaction, auto_save, forecast_goal, recompute_plan
except ImportError:
    apply_transaction = _fallbacks.apply_transaction
    auto_save = _fallbacks.auto_save
    forecast_goal = _fallbacks.forecast_goal
    recompute_plan = _fallbacks.recompute_plan

try:
    from app.agent.proactive import run_proactive
except ImportError:
    run_proactive = _fallbacks.run_proactive

try:
    from app.context.service import (
        default_reading,
        infer_hypotheses,
        on_fact_changed,
        signatures_for_fact,
    )
except ImportError:
    default_reading = _fallbacks.default_reading
    infer_hypotheses = _fallbacks.infer_hypotheses
    on_fact_changed = _fallbacks.on_fact_changed
    signatures_for_fact = _fallbacks.signatures_for_fact

try:
    from app.engine.service import recompute_baselines
except ImportError:
    recompute_baselines = _fallbacks.recompute_baselines

try:
    from app.agent.loop import run_agent
except ImportError:
    run_agent = _fallbacks.run_agent

try:
    from app.agent.language import detect_language
except ImportError:
    detect_language = _fallbacks.detect_language

try:
    from app.agent.templates import fallback_reply
except ImportError:
    fallback_reply = _fallbacks.fallback_reply

try:
    from app.agent.handlers.transactions import apply_annotation
except ImportError:
    apply_annotation = _fallbacks.apply_annotation

try:
    from app.i18n.format import format_money
    from app.i18n.labels import label
except ImportError:
    format_money = _fallbacks.format_money
    label = _fallbacks.label

try:
    from app.context.products import rank_products
except ImportError:
    rank_products = _fallbacks.rank_products
