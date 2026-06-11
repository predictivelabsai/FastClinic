"""Tiny server-sent-events helper for the streaming chat endpoint."""
from __future__ import annotations

import json
from typing import Any


def sse(event: str, data: Any) -> str:
    """Format one SSE message: `event: <name>\\ndata: <json>\\n\\n`."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
