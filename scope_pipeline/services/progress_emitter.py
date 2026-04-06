"""
scope_pipeline/services/progress_emitter.py — SSE event generation.

Agents call emitter.emit(event_type, data) during execution.
The router streams events to the client via SSE.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any


_TERMINAL_EVENTS = frozenset({
    "pipeline_complete", "pipeline_failed", "pipeline_partial",
})


class ProgressEmitter:
    """Thread-safe event emitter backed by asyncio.Queue."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._closed = False

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self._closed:
            return
        event = {"type": event_type, "data": data}
        self._queue.put_nowait(event)
        if event_type in _TERMINAL_EVENTS:
            self._closed = True

    async def stream(self):
        while True:
            try:
                event = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                if self._closed:
                    return
                await asyncio.sleep(0.05)
                continue
            yield event
            if event["type"] in _TERMINAL_EVENTS:
                return

    @staticmethod
    def format_sse(event_type: str, data: dict[str, Any]) -> str:
        payload = json.dumps(data, default=str)
        return f"event: {event_type}\ndata: {payload}\n\n"
