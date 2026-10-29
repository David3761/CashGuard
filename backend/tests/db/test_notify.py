"""B13: notification templates (RO + EN), money formats, banned phrases, push after commit."""

import asyncio
import re
import string
import unicodedata
from decimal import Decimal

import pytest

from app.i18n.notifications import TEMPLATES
from app.services.notify import notify, render
from app.ws import manager
from tests import factories as f

D = Decimal
PARAMS = {
    "over": D("85"),
    "budget": D("30.40"),
    "days": 4,
    "amount": D("10000"),
    "pot": "Fond 10.000",
    "count": 4,
    "each": D("100"),
    "debtor": "colegi",
    "goal": "Fond 10.000",
}
BANNED = {  # arch 6.9 (A5's find_banned replaces this list)
    "ro": [
        "de ce",
        "prea mult",
        "risipa",
        "ar fi trebuit",
        "iar",
        "din nou",
        "iresponsabil",
        "nu-ti permiti",
    ],
    "en": [
        "why did you",
        "too much",
        "waste",
        "should have",
        "again",
        "irresponsible",
        "can't afford",
    ],
}


def fold(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn"
    )


@pytest.mark.parametrize("type_", sorted(TEMPLATES))
@pytest.mark.parametrize("lang", ["ro", "en"])
def test_every_template_fills_its_params_without_banned_phrases(type_, lang):
    title, body = render(type_, PARAMS, lang)
    for text in (title, body):
        assert "{" not in text
        for phrase in BANNED[lang]:
            assert not re.search(rf"\b{re.escape(phrase)}\b", fold(text)), (type_, phrase)
    fields = {
        f
        for t in (TEMPLATES[type_].ro + TEMPLATES[type_].en)
        for _, f, _, _ in string.Formatter().parse(t)
        if f
    }
    assert fields <= set(PARAMS)


def test_money_is_formatted_per_language():
    assert render("auto_save", {"amount": D("10000"), "pot": "X"}, "ro")[1].startswith(
        "Am pus 10.000 lei"
    )
    assert "30,40 lei" in render("overspend", {"over": D("85"), "budget": D("30.40")}, "ro")[1]
    assert "1,234.50 lei" in render("plan_updated", {"budget": D("1234.5")}, "en")[1]
    assert render("payment_request_sent", {"count": 4, "each": D("100")}, "ro")[1] == (
        "Cerere trimisă: 4 × 100 lei"
    )


def test_opens_chat_per_type():
    assert {t for t, tpl in TEMPLATES.items() if tpl.opens_chat} == {
        "overspend",
        "receivable_reminder",
        "goal_completed",
    }


async def test_unknown_type_is_refused(db):
    u = await f.user(db)
    with pytest.raises(Exception, match="No template"):
        await notify(db, u.id, "nag", {})


async def test_notify_uses_the_users_language_and_pushes_after_commit(db_committed):
    u = await f.user(db_committed, language="en")
    await db_committed.commit()

    class Sock:
        def __init__(self):
            self.got = []

        async def send_json(self, data):
            self.got.append(data)

    sock = Sock()
    manager.connect(u.id, sock)
    try:
        n = await notify(db_committed, u.id, "auto_save", {"amount": D("760"), "pot": "Fund"})
        assert n.body == "I put 760 lei aside for Fund · Undo" and sock.got == []
        await db_committed.commit()
        await asyncio.sleep(0)
    finally:
        manager.disconnect(u.id, sock)
    assert [e["type"] for e in sock.got] == ["notification.new"]
