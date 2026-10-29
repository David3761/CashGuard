"""The service contract (arch 15.1 + Bomboe.md B3/B4): names and parameters other people code
against. Changing one of these is a contract change: tell David G. and danutu, update this list.
"""

import importlib
import inspect

import pytest

# "module.function": parameters in order (keyword-only ones after "*")
CONTRACT = {
    # profile & plan inputs (B3 step 1)
    "users.get": "db user_id",
    "users.get_by_sub": "db keycloak_sub",
    "users.create": "db * keycloak_sub name age language city",
    "users.update": "db user_id * language coach_style household_scale city",
    "users.set_onboarded": "db user_id",
    "accounts.get": "db user_id",
    "accounts.create": "db user_id * current_balance savings_pot",
    "accounts.adjust_balance": "db user_id delta",
    "goals.get": "db user_id goal_id",
    "goals.get_active": "db user_id",
    "goals.create": "db user_id * amount deadline motivation soft",
    "goals.update": "db user_id goal_id * amount deadline motivation soft",
    "goals.complete": "db user_id goal_id",
    "income_sources.list_all": "db user_id",
    "income_sources.create": "db user_id * source amount day_of_month",
    "income_sources.update": "db user_id income_id * source amount day_of_month",
    "income_sources.delete": "db user_id income_id",
    "fixed_costs.list_all": "db user_id",
    "fixed_costs.create": "db user_id * name amount day_of_month",
    "fixed_costs.update": "db user_id cost_id * name amount day_of_month",
    "fixed_costs.delete": "db user_id cost_id",
    "life_events.get": "db user_id event_id",
    "life_events.list_planned": "db user_id",
    "life_events.create": "db user_id * name date est_cost type source",
    "life_events.update": "db user_id event_id * name date est_cost type",
    "life_events.cancel": "db user_id event_id",
    "life_events.mark_done": "db user_id event_id",
    "life_profile.get": "db user_id",
    "life_profile.set_key": "db user_id key value",
    "life_profile.delete_key": "db user_id key",
    "plan_preferences.get": "db user_id",
    "plan_preferences.update": "db user_id * weekday_weights pinned_days category_caps buffer_pct",
    "products.list_all": "db",
    "merchants.list_all": "db",
    "merchants.get": "db merchant_id",
    # money flow (B3 step 2)
    "transactions.get": "db user_id tx_id",
    "transactions.list_all": "db user_id * since until status",
    "transactions.list_effective": "db user_id since until category",
    "transactions.save_evaluation": "db user_id tx_id evaluation",
    "transactions.annotate": (
        "db user_id tx_id * purpose beneficiary effective_amount source explanation confidence"
    ),
    "transactions.set_pot": "db user_id tx_id pot_id",
    "transactions.set_receivable": "db user_id tx_id receivable_id",
    "transactions.mark_resolved": "db user_id tx_id",
    "transactions.mark_failed": "db user_id tx_id error",
    "transactions.bump_attempts": "db user_id tx_id error",
    "ledger.get": "db user_id day",
    "ledger.get_or_create": "db user_id day",
    "ledger.update": "db user_id day * budget spent status",
    "ledger.add_spent": "db user_id day delta",
    "ledger.between": "db user_id since until",
    "plans.latest": "db user_id",
    "plans.by_version": "db user_id version",
    "plans.history": "db user_id",
    "plans.next_version": "db user_id",
    "plans.save": "db user_id result * reason trigger_ref",
    "transfers.get": "db user_id transfer_id",
    "transfers.create": "db user_id * amount kind pot_id income_transaction_id",
    "transfers.for_income": "db user_id income_transaction_id",
    "transfers.undo": "db user_id transfer_id",
    # conversation (B3 step 3)
    "agent_events.get": "db user_id event_id",
    "agent_events.create": "db user_id * type event_date payload ref_transaction_id",
    "agent_events.mark_asked": "db user_id event_id",
    "agent_events.mark_answered": "db user_id event_id",
    "agent_events.mark_handled": "db user_id event_id",
    "agent_events.expire": "db user_id event_id",
    "agent_events.pending_for": "db user_id",
    "agent_events.open_question": "db user_id",
    "agent_events.question_asked_today": "db user_id day",
    "messages.save_user": "db user_id text input_mode",
    "messages.save_assistant": (
        "db user_id * text speak_text quick_replies action_cards ref_transaction_id "
        "agent_event_id speak"
    ),
    "messages.list_all": "db user_id * since limit",
    "messages.recent": "db user_id limit",
    "notifications.create": ("db user_id * type title body opens_chat agent_event_id message_id"),
    "notifications.list_all": "db user_id * since unread_only",
    "notifications.mark_read": "db user_id notification_id",
    "notifications.unread_count": "db user_id",
    "agent_runs.start": "db user_id * trigger model",
    "agent_runs.finish": "db user_id run_id * status iterations error",
    "agent_runs.is_running": "db user_id",
    "tool_calls.log": "db user_id run_id * tool_name input output status",
    # life context & savings (B3 step 4)
    "life_facts.get": "db user_id fact_id",
    "life_facts.create": "db user_id fact",
    "life_facts.update": (
        "db user_id fact_id * value text persistence valid_from valid_to confidence"
    ),
    "life_facts.expire": "db user_id fact_id valid_to",
    "life_facts.delete": "db user_id fact_id",
    "life_facts.list_all": "db user_id status",
    "life_facts.list_active": "db user_id on_date",
    "life_facts.list_hypotheses": "db user_id",
    "life_facts.confirm": "db user_id fact_id",
    "life_facts.reject": "db user_id fact_id",
    "signatures.replace_for_fact": "db user_id fact_id signatures",
    "signatures.list_active": "db user_id effect",
    "signatures.list_for_fact": "db user_id fact_id",
    "pattern_rules.get": "db user_id rule_id",
    "pattern_rules.create": "db user_id rule",
    "pattern_rules.list_active": "db user_id",
    "pattern_rules.record_hit": "db user_id rule_id",
    "pattern_rules.record_miss": "db user_id rule_id",
    "pattern_rules.set_confidence": "db user_id rule_id confidence",
    "pattern_rules.deactivate": "db user_id rule_id",
    "receivables.get": "db user_id receivable_id",
    "receivables.create": (
        "db user_id * amount debtor_label expected_by transaction_id people_count amount_each"
    ),
    "receivables.list_all": "db user_id status",
    "receivables.list_open": "db user_id",
    "receivables.update_status": "db user_id receivable_id status",
    "receivables.cancel": "db user_id receivable_id",
    "pots.get": "db user_id pot_id",
    "pots.create": (
        "db user_id * name kind target deadline goal_id life_event_id fact_id monthly_contribution"
    ),
    "pots.update": "db user_id pot_id * name target deadline monthly_contribution",
    "pots.close": "db user_id pot_id",
    "pots.list_active": "db user_id",
    "pots.goal_pot": "db user_id",
    "pots.add_saved": "db user_id pot_id delta",
    "forecasts.save": "db user_id forecast * goal_id reason",
    "forecasts.latest": "db user_id",
    "forecasts.last_weekly_snapshot": "db user_id",
    "forecasts.weekly_history": "db user_id",
    "baselines.replace_all": "db user_id baselines",
    "baselines.list_all": "db user_id",
    # B4
    "context_loader.load_user_context": "db user_id today history_days",
}


def params(fn) -> str:
    out, star = [], False
    for p in inspect.signature(fn).parameters.values():
        if p.kind is p.KEYWORD_ONLY and not star:
            out.append("*")
            star = True
        out.append(p.name)
    return " ".join(out)


@pytest.mark.parametrize("name", sorted(CONTRACT))
def test_service_function_matches_the_contract(name):
    module_name, func_name = name.split(".")
    module = importlib.import_module(f"app.services.{module_name}")
    fn = getattr(module, func_name, None)
    assert fn is not None, f"app.services.{name} is missing"
    assert inspect.iscoroutinefunction(fn), f"{name} must be async"
    assert params(fn) == CONTRACT[name]
    assert fn.__doc__, f"{name} needs a docstring (it's what the others read)"
