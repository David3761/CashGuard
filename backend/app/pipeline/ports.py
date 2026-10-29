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
