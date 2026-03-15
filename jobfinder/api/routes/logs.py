"""SSE endpoint for streaming backend logs to the UI."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from jobfinder.utils.log_stream import get_current_seq, get_logs_since

router = APIRouter()


@router.get("/logs/stream")
async def stream_logs(request: Request):
    """Stream log entries as SSE events.

    Each event has type ``"log"`` with JSON payload::

        {"seq": 42, "timestamp": "14:32:01", "level": "info", "message": "..."}

    Clients start from the current position (no replay of historical logs).
    Multiple clients can connect simultaneously — each tracks its own cursor.
    """

    async def event_generator():
        last_seq = get_current_seq()
        try:
            while True:
                if await request.is_disconnected():
                    break
                entries, last_seq = get_logs_since(last_seq)
                for entry in entries:
                    yield {"event": "log", "data": json.dumps(entry)}
                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            pass

    return EventSourceResponse(event_generator())
