"""WebSocket event builders (arch 5.2): `{type, data, ts}` with `ts` ISO UTC ending in Z and
money as JSON numbers. One function per event; `data` keys exactly as the arch table."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app import clock
from app.domain import models as dm
from app.domain.results import Forecast, PlanSummary

Event = dict[str, Any]


def _json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, list | tuple):
        return [_json(v) for v in value]
    if isinstance(value, dict):
        return {k: _json(v) for k, v in value.items()}
    return value


def _event(type_: str, data: dict[str, Any]) -> Event:
    ts = clock.now().astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    return {"type": type_, "data": _json(data), "ts": ts}


def agent_typing() -> Event:
    return _event("agent.typing", {})


def assistant_message(msg: dm.MessageView) -> Event:
    return _event(
        "assistant.message",
        {
            "message_id": msg.id,
            "text": msg.content,
            "quick_replies": list(msg.quick_replies),
            "speak": msg.speak,
            "speak_text": msg.speak_text,
            "action_cards": list(msg.action_cards),
            "ref_transaction_id": msg.ref_transaction_id,
        },
    )


def notification_new(n: dm.NotificationView) -> Event:
    return _event(
        "notification.new",
        {"id": n.id, "type": n.type, "title": n.title, "body": n.body, "opens_chat": n.opens_chat},
    )


def plan_updated(plan: PlanSummary) -> Event:
    return _event(
        "plan.updated",
        {"version": plan.version, "today_budget": plan.today_budget, "feasible": plan.feasible},
    )


def transaction_resolved(tx: dm.TxView) -> Event:
    return _event("transaction.resolved", {"id": tx.id, "status": tx.status})


def ledger_updated(day: dm.LedgerDay) -> Event:
    return _event(
        "ledger.updated",
        {"date": day.date, "spent": day.spent, "budget": day.budget, "status": day.status},
    )


def transaction_annotated(tx: dm.TxView, purpose_label: str | None = None) -> Event:
    return _event(
        "transaction.annotated",
        {
            "id": tx.id,
            "amount": tx.amount,
            "effective_amount": tx.effective_amount,
            "purpose": tx.purpose,
            "purpose_label": purpose_label,
            "explanation": tx.explanation,
            "decision": tx.decision,
            "receivable_id": tx.receivable_id,
            "pot_id": tx.pot_id,
        },
    )


def forecast_updated(f: Forecast) -> Event:
    return _event(
        "forecast.updated",
        {
            "probability": f.probability,
            "previous_probability": f.previous_probability,
            "last_week_probability": f.last_week_probability,
            "p10": f.p10,
            "p50": f.p50,
            "p90": f.p90,
            "expected_reach_date": f.expected_reach_date,
        },
    )


def receivable_updated(r: dm.Receivable) -> Event:
    return _event(
        "receivable.updated",
        {"id": r.id, "amount": r.amount, "debtor_label": r.debtor_label, "status": r.status},
    )


def pot_updated(p: dm.Pot) -> Event:
    return _event(
        "pot.updated",
        {
            "id": p.id,
            "name": p.name,
            "saved": p.saved,
            "target": p.target,
            "monthly_contribution": p.monthly_contribution,
            "status": p.status,
        },
    )


def fact_hypothesis(fact: dm.LifeFact, question: str) -> Event:
    return _event("fact.hypothesis", {"fact_id": fact.id, "text": fact.text, "question": question})
