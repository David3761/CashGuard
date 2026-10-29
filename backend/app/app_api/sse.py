"""Server-Sent Events framing, as the app's `EventStreamClient` reads it.

- Every frame names its event (`event:`): a frame without one defaults to `message` in the app
  and would be parsed as a chat message.
- `data` is one line of JSON (`json.dumps` escapes newlines inside strings), UTF-8, no ASCII
  escaping, so diacritics and emoji arrive as themselves.
- A line starting with `:` is a comment: the app ignores it, so it's the keep-alive.
"""

import json
from typing import Any, Final

KEEP_ALIVE: Final = b": keep-alive\n\n"
MEDIA_TYPE: Final = "text/event-stream; charset=utf-8"
HEADERS: Final = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def frame(event: str, data: Any) -> bytes:
    """`event: <event>\\ndata: <json>\\n\\n` as UTF-8 bytes."""
    if not event or any(ch in event for ch in "\r\n:"):
        raise ValueError(f"bad SSE event name {event!r}")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n".encode()
