"""`HANDLERS`: tool name → handler (A3). The executor whitelists A2's specs that appear here."""

from app.agent.handlers import (
    events,
    facts,
    goals,
    income_costs,
    pots,
    reads,
    receivables,
    rules,
    shaping,
    transactions,
    ui,
)
from app.agent.handlers.common import Handler

HANDLERS: dict[str, Handler] = {
    # transactions & receivables
    "annotate_transaction": transactions.annotate_transaction,
    "create_receivable": receivables.create_receivable,
    "cancel_receivable": receivables.cancel_receivable,
    "mark_receivable_paid": receivables.mark_receivable_paid,
    "offer_payment_request": receivables.offer_payment_request,
    # life facts & rules
    "add_life_fact": facts.add_life_fact,
    "update_life_fact": facts.update_life_fact,
    "expire_life_fact": facts.expire_life_fact,
    "confirm_hypothesis": facts.confirm_hypothesis,
    "create_pattern_rule": rules.create_pattern_rule,
    # pots & goals
    "create_pot": pots.create_pot,
    "update_pot": pots.update_pot,
    "close_pot": pots.close_pot,
    "link_transaction_to_pot": pots.link_transaction_to_pot,
    "set_goal": goals.set_goal,
    "update_goal": goals.update_goal,
    # income, fixed costs, life events
    "add_income_source": income_costs.add_income_source,
    "update_income_source": income_costs.update_income_source,
    "remove_income_source": income_costs.remove_income_source,
    "add_fixed_cost": income_costs.add_fixed_cost,
    "update_fixed_cost": income_costs.update_fixed_cost,
    "remove_fixed_cost": income_costs.remove_fixed_cost,
    "add_life_event": events.add_life_event,
    "update_life_event": events.update_life_event,
    "cancel_life_event": events.cancel_life_event,
    # shaping & coaching
    "shape_budget": shaping.shape_budget,
    "record_slip_reason": shaping.record_slip_reason,
    "record_reflection": shaping.record_reflection,
    "update_life_profile": shaping.update_life_profile,
    "transfer_to_savings": shaping.transfer_to_savings,
    "complete_onboarding": shaping.complete_onboarding,
    # reads
    "get_transaction": reads.get_transaction,
    "get_transactions": reads.get_transactions,
    "get_spending_summary": reads.get_spending_summary,
    "get_plan_status": reads.get_plan_status,
    "get_goal_forecast": reads.get_goal_forecast,
    "simulate_plan": reads.simulate_plan,
    "suggest_savings_products": reads.suggest_savings_products,
    # ui
    "show_quick_replies": ui.show_quick_replies,
    "mark_event_handled": ui.mark_event_handled,
}
