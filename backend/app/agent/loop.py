"""The agent loop (arch 6.3): S0 stub of `run_agent` with the exact §15 signature.

A6 replaces the body with the real tool-use loop. Until then every run answers with an echo, so
bomboe's `/chat` (B9) has a reply to save and push.
"""

from app.domain.results import AgentResult


def run_agent(
    user_id: int, trigger: str, user_message: str | None, input_mode: str = "text"
) -> AgentResult:
    """Stub of A6: "Am primit: <the message>" ("Am primit." with no message)."""
    text = f"Am primit: {user_message}" if user_message else "Am primit."
    return AgentResult(text=text, speak_text=text if len(text) <= 300 else "Am primit.")
