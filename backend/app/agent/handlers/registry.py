"""`HANDLERS`: tool name → handler (A3). The executor whitelists A2's specs that appear here."""

from app.agent.handlers.common import Handler

HANDLERS: dict[str, Handler] = {}
