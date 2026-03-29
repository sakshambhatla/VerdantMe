"""SSE endpoint for streaming backend logs to the UI.

In managed mode, restricted to users with ``devtest`` role or higher.
"""
from __future__ import annotations

import asyncio
import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from jobfinder.api.auth import get_current_user
from jobfinder.api.rbac import get_user_role, role_at_least
from jobfinder.utils.log_stream import get_current_seq, get_logs_since

router = APIRouter()


@router.get("/logs/stream")
async def stream_logs(
    request: Request,
    _auth: tuple[str, str] | None = Depends(get_current_user),
):
    """Stream log entries as SSE events.

    Each event has type ``"log"`` with JSON payload::

        {"seq": 42, "timestamp": "14:32:01", "level": "info", "message": "..."}

    Clients start from the current position (no replay of historical logs).
    Multiple clients can connect simultaneously — each tracks its own cursor.

    Requires ``devtest`` role or higher in managed mode.
    """
    if os.environ.get("SUPABASE_URL"):
        user_id, jwt_token = _auth if _auth else (None, None)
        if not user_id:
            raise HTTPException(status_code=401, detail="Not authenticated")
        role = await asyncio.to_thread(get_user_role, user_id, jwt_token)
        if not role_at_least(role, "devtest"):
            raise HTTPException(
                status_code=403,
                detail="Log stream requires devtest role or higher.",
            )

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
