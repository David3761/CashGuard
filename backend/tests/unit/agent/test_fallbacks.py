"""A9: the demo's chips map to deterministic actions while Claude is down."""

from decimal import Decimal
from typing import Any

import pytest

from app.agent.fallbacks import _TEXTS, PotRef, chip_key
from app.agent.llm import LLMUnavailable
from app.agent.loop import run_agent
from app.agent.style import find_banned
from app.agent.templates import HOW_MANY_OPTIONS, fallback_reply, how_many_followup
from app.domain.results import AgentResult
from tests.fakes.fake_agent_services import FakeAgentServices
from tests.fakes.fake_llm import FakeLLM, end_turn, tool_round, tool_use

SPLIT = {
    "transaction_id": 918,
    "purpose": "on_behalf_of_others",
    "beneficiary": "shared",
    "people_count": 5,
    "others_will_repay": True,
    "debtor_label": "colegi",
}


async def _down(services: FakeAgentServices, text: str) -> AgentResult:
    """One chat turn while Claude is down."""
    fake = FakeLLM([LLMUnavailable("down")])
    result = await run_agent(1, "chat", text, llm=fake, services=services)
    fake.assert_consumed()
    return result


async def test_scene_a_via_the_chips_matches_the_llm_path() -> None:
    llm_path = FakeAgentServices()
    fake = FakeLLM(
        [
            tool_round(tool_use("annotate_transaction", SPLIT, tool_use_id="toolu_1")),
            tool_round(tool_use("offer_payment_request", {"receivable_id": 9}, tool_use_id="t2")),
            end_turn("Am înțeles! Cheltuiala ta reală e 100 de lei. Ai 400 de lei de recuperat."),
        ]
    )
    await run_agent(
        1, "chat", "Am luat și pentru colegi, suntem cinci.", llm=fake, services=llm_path
    )
    fake.assert_consumed()

    chips = FakeAgentServices()
    first = await _down(chips, "Și pentru alții")
    assert first.text == how_many_followup("ro")
    assert first.quick_replies == HOW_MANY_OPTIONS
    assert chips.executed == []  # nothing changed yet

    second = await _down(chips, "5")
    assert chips.state() == llm_path.state()
    assert chips.transactions[918].effective_amount == Decimal("100.00")
    assert [r["amount"] for r in chips.receivables.values()] == [Decimal("400.00")]
    assert "100 de lei" in second.text
    assert "400 de lei" in second.text
    [card] = second.action_cards
    assert card.receivable_id == 9
    assert second.plan_changed is True
    assert second.ref_transaction_id == 918


async def test_unknown_text_changes_nothing() -> None:
    services = FakeAgentServices()
    before = services.state()
    result = await _down(services, "am luat niște chestii pentru petrecere")
    assert result.text == fallback_reply("llm_down", "ro")
    assert services.executed == []
    assert services.state() == before


async def test_a_chip_without_an_open_question_changes_nothing() -> None:
    services = FakeAgentServices(open_question=None)
    result = await _down(services, "Doar pentru mine")
    assert result.text == fallback_reply("llm_down", "ro")
    assert services.executed == []


@pytest.mark.parametrize(("label", "lang"), [("Doar pentru mine", "ro"), ("just for me", "en")])
async def test_just_me_is_self_with_a_purpose_by_category(label: str, lang: str) -> None:
    services = FakeAgentServices(language=lang)
    result = await _down(services, label)
    tx = services.transactions[918]
    assert (tx.purpose, tx.beneficiary) == ("essential_living", "self")  # groceries
    assert tx.effective_amount == Decimal("500.00")
    assert "Mega Image" in result.text


async def test_english_for_others_asks_how_many() -> None:
    result = await _down(FakeAgentServices(language="en"), "For others too")
    assert result.text == how_many_followup("en")
    assert result.quick_replies == HOW_MANY_OPTIONS


async def test_rather_not_say_is_unknown_and_suppresses_similar() -> None:
    services = FakeAgentServices()
    await _down(services, "Prefer sa nu spun")  # no diacritics: still the chip
    assert services.transactions[918].purpose == "unknown"
    assert services.rules == [
        {"kind": "suppress", "match": {"merchant_id": "mega_image"}, "outcome": {}}
    ]


async def test_planned_links_the_only_pot() -> None:
    services = FakeAgentServices(pots=(PotRef(4, "Petrecere"),))
    result = await _down(services, "Ceva plănuit")
    assert services.transactions[918].pot_id == 4
    assert "Petrecere" in result.text


async def test_planned_with_several_pots_asks_which_then_links() -> None:
    services = FakeAgentServices(pots=(PotRef(4, "Petrecere"), PotRef(5, "Vacanță august")))
    ask = await _down(services, "Ceva plănuit")
    assert ask.quick_replies == ("Petrecere", "Vacanță august")
    assert services.executed == []
    await _down(services, "Vacanță august")
    assert services.transactions[918].pot_id == 5


async def test_a_failing_tool_gives_the_polite_reply() -> None:
    services = FakeAgentServices()

    def broken(args: dict[str, Any]) -> dict[str, Any]:
        raise ValueError("annotate failed")

    services.overrides["annotate_transaction"] = broken
    result = await _down(services, "Doar pentru mine")
    assert result.text == fallback_reply("llm_down", "ro")


def test_chip_keys_and_texts() -> None:
    assert chip_key("  ȘI PENTRU ALȚII! ") == "for_others"
    assert chip_key("I'd rather not say") == "rather_not_say"
    assert chip_key("6+") == "count:6"
    assert chip_key("salut") is None
    for forms in _TEXTS.values():
        for text in forms.values():
            assert find_banned(text) == [], text
