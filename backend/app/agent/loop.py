"""The agent loop (arch 6.3): S0 stub of `run_agent` with the exact §15 signature.

A6 replaces the body with the real tool-use loop. Until then every run answers with an echo, so
bomboe's `/chat` (B9) has a reply to save and push.
"""

from typing import Literal

from app.domain.models import DomainModel

# ── TODO(F2): placeholders with F2's planned names (F2.md step 7). Replace with the imports from ──
# ── app.domain.results when F2 lands. ───────────────────────────────────────────────────────


class ActionCard(DomainModel):  # TODO(F2): app.domain.results.ActionCard
    type: Literal["request_payment"]
    receivable_id: int
    label: str


class AgentResult(DomainModel):  # TODO(F2): app.domain.results.AgentResult
    text: str
    speak_text: str | None = None
    quick_replies: tuple[str, ...] = ()
    action_cards: tuple[ActionCard, ...] = ()
    plan_changed: bool = False
    ref_transaction_id: int | None = None


def run_agent(
    user_id: int, trigger: str, user_message: str | None, input_mode: str = "text"
) -> AgentResult:
    """Stub of A6: "Am primit: <the message>" ("Am primit." with no message)."""
    text = f"Am primit: {user_message}" if user_message else "Am primit."
    return AgentResult(text=text, speak_text=text)
