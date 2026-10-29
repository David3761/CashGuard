"""Notification texts, RO + EN (B13). Never judgmental (D33): no "de ce", "prea mult", "iar"…"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Template:
    opens_chat: bool
    ro: tuple[str, str]  # (title, body)
    en: tuple[str, str]


TEMPLATES: dict[str, Template] = {
    "overspend": Template(
        True,
        (
            "Planul s-a actualizat",
            "Azi ai cheltuit cu {over} peste plan. Bugetul nou: {budget}/zi.",
        ),
        (
            "Your plan was updated",
            "Today you spent {over} more than planned. New budget: {budget}/day.",
        ),
    ),
    "plan_updated": Template(
        False,
        ("Planul s-a actualizat", "Bugetul tău de azi: {budget}."),
        ("Your plan was updated", "Today's budget: {budget}."),
    ),
    "streak": Template(
        False,
        ("{days} zile în plan", "Ești în plan de {days} zile la rând. 👏"),
        ("{days} days on plan", "You've stayed on plan for {days} days in a row. 👏"),
    ),
    "auto_save": Template(
        False,
        ("Economii", "Am pus {amount} deoparte pentru {pot} · Anulează"),
        ("Savings", "I put {amount} aside for {pot} · Undo"),
    ),
    "payment_request_sent": Template(
        False,
        ("Cerere trimisă", "Cerere trimisă: {count} × {each}"),
        ("Request sent", "Request sent: {count} × {each}"),
    ),
    "receivable_reminder": Template(
        True,
        ("De recuperat", "Ai {amount} de recuperat de la {debtor}."),
        ("To collect", "You have {amount} to collect from {debtor}."),
    ),
    "goal_completed": Template(
        True,
        ("Obiectiv atins 🎉", "Ai strâns {amount} pentru {goal}!"),
        ("Goal reached 🎉", "You saved {amount} for {goal}!"),
    ),
}
