"""Golden value lists copied from arch 4.4 / 4.5. A missing or misspelt value fails here."""

import pytest

from app.domain import enums as e

GOLDEN = {
    e.Category: (
        "groceries restaurants food_delivery transport fuel electronics clothing sport "
        "health_pharmacy kids education books entertainment subscriptions travel housing_rent "
        "utilities telecom gifts pets household_goods personal_care transfers income savings other"
    ),
    e.Purpose: (
        "essential_living household_care work_tool self_investment identity_joy "
        "social_connection planned_event on_behalf_of_others unplanned_discretionary "
        "emergency unknown"
    ),
    e.Beneficiary: "self household shared others employer",
    e.Decision: "ignore auto inform ask ask_later",
    e.Direction: "debit credit",
    e.FactType: (
        "occupation employment income_pattern household_member pet housing city vehicle "
        "commute activity social_pattern life_event rhythm priority custom"
    ),
    e.FactStatus: "hypothesis confirmed rejected expired",
    e.FactSource: "onboarding chat voice user_edit inferred seed",
    e.Persistence: "permanent temporary recurring",
    e.SignatureEffect: "explains scales_baseline expects_event protects",
    e.SignatureOrigin: "library llm",
    e.RuleKind: "classify suppress",
    e.RuleSource: "answer explicit learned",
    e.ReceivableStatus: "open requested paid cancelled",
    e.PotKind: "goal event emergency custom",
    e.PotStatus: "active completed closed",
    e.AnnotationSource: "auto rule fact pot answer user_edit default",
    e.InputMode: "text voice quick_reply",
    e.AgentEventType: (
        "overspend warning underspend_week life_change infeasible_plan weekly_reflection "
        "preemptive_checkin goal_completed category_cap transaction_question hypothesis_check "
        "receivable_reminder"
    ),
    e.AgentEventStatus: "pending asked answered handled expired",
    e.Language: "ro en",
    e.CoachStyle: "warm direct",
    e.TransferKind: "manual auto_save",
    e.ProductKind: "flexible_pot savings_account term_deposit",
    e.Liquidity: "instant notice locked",
    e.TransactionStatus: "unresolved processing resolved failed",
    e.TransactionSource: "seed sim",
    e.GoalStatus: "active completed",
    e.LifeEventType: "trip gift social purchase education other",
    e.LifeEventStatus: "planned done cancelled",
    e.LedgerStatus: "ok warning overspent under",
    e.MessageRole: "user assistant",
}


@pytest.mark.parametrize("enum", list(GOLDEN), ids=lambda en: en.__name__)
def test_enum_values_match_arch_doc(enum):
    assert [m.value for m in enum] == GOLDEN[enum].split()


def test_enum_members_compare_equal_to_their_strings():
    assert e.Category.GROCERIES == "groceries"
    assert e.Purpose("work_tool") is e.Purpose.WORK_TOOL
