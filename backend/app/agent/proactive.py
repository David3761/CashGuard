"""Proactive runs (arch 6.3, A7): S0 stub of `run_proactive` with the exact signature.

A7 replaces the body (event-specific instructions, read-only tools, the 5 s template fallback,
saving the message, marking the event asked). Until then it returns the template question.
"""

from typing import Final

from app.domain.results import AgentResult

TEMPLATE_QUESTION: Final = "Am văzut o plată nouă. Ce a fost?"
QUICK_REPLIES: Final = ("Doar pentru mine", "Și pentru alții", "Ceva plănuit", "Prefer să nu spun")
"""A9's known chip labels (DGAdavid1 A9)."""


def run_proactive(user_id: int, event_id: int) -> AgentResult:
    """Stub of A7: the template question with the default quick replies."""
    return AgentResult(
        text=TEMPLATE_QUESTION, speak_text=TEMPLATE_QUESTION, quick_replies=QUICK_REPLIES
    )
