"""The context snapshot the agent reads (arch 6.5, A4): S0 shell of `build_snapshot`.

A4 replaces the body with the real snapshot (profile, plan, forecast, facts, open questions …).
The stub gives a minimal text with the user, the app date and the trigger.
"""

from typing import Any

from app import clock


def build_snapshot(db: Any, user_id: int, trigger: str, event_id: int | None) -> str:
    """Stub of A4: a few lines of plain text (`db` is unused until bomboe's session exists)."""
    lines = [f"user: {user_id}", f"today: {clock.today().isoformat()}", f"trigger: {trigger}"]
    if event_id is not None:
        lines.append(f"event: {event_id}")
    return "\n".join(lines)
