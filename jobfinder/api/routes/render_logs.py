"""SSE endpoint for streaming Render platform logs to the UI.

Proxies the Render REST API log endpoint, polling every few seconds and
re-emitting entries as SSE events.  Restricted to ``devtest`` role or higher.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from jobfinder.api.auth import get_current_user
from jobfinder.api.rbac import get_user_role, role_at_least

logger = logging.getLogger(__name__)

router = APIRouter()

RENDER_API_BASE = "https://api.render.com/v1"
POLL_INTERVAL_SECONDS = 3


def _flatten_labels(labels: list[dict]) -> dict[str, str]:
    """Convert Render's ``[{name, value}, ...]`` labels to a flat dict."""
    return {item["name"]: item["value"] for item in labels}


@router.get("/render-logs/stream")
async def stream_render_logs(
    request: Request,
    _auth: tuple[str, str] | None = Depends(get_current_user),
):
    """Stream Render platform logs as SSE events.

    Requires ``RENDER_API_KEY`` and ``RENDER_SERVICE_ID`` environment variables.
    Requires ``devtest`` role or higher in managed mode.
    """
    # ── RBAC ─────────────────────────────────────────────────────────────────
    if os.environ.get("SUPABASE_URL"):
        user_id, jwt_token = _auth if _auth else (None, None)
        if not user_id:
            raise HTTPException(status_code=401, detail="Not authenticated")
        role = await asyncio.to_thread(get_user_role, user_id, jwt_token)
        if not role_at_least(role, "devtest"):
            raise HTTPException(
                status_code=403,
                detail="Render log stream requires devtest role or higher.",
            )

    # ── Render config ────────────────────────────────────────────────────────
    render_api_key = os.environ.get("RENDER_API_KEY")
    render_service_id = os.environ.get("RENDER_SERVICE_ID")
    if not render_api_key or not render_service_id:
        raise HTTPException(
            status_code=503,
            detail="Render log streaming not configured (missing RENDER_API_KEY or RENDER_SERVICE_ID).",
        )

    async def event_generator():
        seen_ids: set[str] = set()
        cursor_end: str | None = None

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                while True:
                    if await request.is_disconnected():
                        break

                    # Build query params
                    params: dict[str, str | int] = {
                        "resource[]": render_service_id,
                        "direction": "backward",
                        "limit": 50,
                    }
                    if cursor_end:
                        params["endTime"] = cursor_end

                    try:
                        resp = await client.get(
                            f"{RENDER_API_BASE}/logs",
                            params=params,
                            headers={
                                "Authorization": f"Bearer {render_api_key}",
                                "Accept": "application/json",
                            },
                        )
                        resp.raise_for_status()
                        data = resp.json()
                    except Exception:
                        logger.warning("Render log poll failed", exc_info=True)
                        await asyncio.sleep(POLL_INTERVAL_SECONDS)
                        continue

                    logs = data.get("logs", [])

                    # Reverse so we emit oldest-first within each batch
                    new_entries = []
                    for entry in reversed(logs):
                        log_id = entry.get("id", "")
                        if log_id in seen_ids:
                            continue
                        seen_ids.add(log_id)
                        labels = _flatten_labels(entry.get("labels", []))
                        new_entries.append({
                            "id": log_id,
                            "timestamp": entry.get("timestamp", ""),
                            "level": labels.get("level", "info"),
                            "type": labels.get("type", "app"),
                            "instance": labels.get("instance", ""),
                            "message": entry.get("message", ""),
                        })

                    for flat in new_entries:
                        yield {"event": "render-log", "data": json.dumps(flat)}

                    # Advance cursor for next poll
                    next_end = data.get("nextEndTime")
                    if next_end:
                        cursor_end = next_end

                    # Cap seen_ids to avoid unbounded memory growth
                    if len(seen_ids) > 5000:
                        seen_ids.clear()

                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                pass

    return EventSourceResponse(event_generator())
