from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from jobfinder.api.auth import get_current_user
from jobfinder.api.models import (
    ApplySyncSuggestionsRequest,
    CreatePipelineEntryRequest,
    CreatePipelineUpdateRequest,
    PipelineSyncRequest,
    ReorderPipelineRequest,
    UpdatePipelineEntryRequest,
)
from jobfinder.storage import get_storage_backend

router = APIRouter()


# ── Entries ──────────────────────────────────────────────────────────────────


@router.get("/pipeline/entries")
async def list_pipeline_entries(
    stage: str | None = None,
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Return all pipeline entries, optionally filtered by stage."""
    user_id, jwt_token = _auth if _auth else (None, None)
    store = get_storage_backend(user_id, jwt_token)
    entries: list[dict] = store.read("pipeline_entries.json") or []
    if stage:
        entries = [e for e in entries if e.get("stage") == stage]
    return {"entries": entries, "total": len(entries)}


@router.get("/pipeline/entries/{entry_id}")
async def get_pipeline_entry(
    entry_id: str,
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Return a single pipeline entry."""
    user_id, jwt_token = _auth if _auth else (None, None)
    store = get_storage_backend(user_id, jwt_token)
    entries: list[dict] = store.read("pipeline_entries.json") or []
    for entry in entries:
        if entry.get("id") == entry_id:
            return entry
    raise HTTPException(status_code=404, detail=f"Pipeline entry '{entry_id}' not found.")


@router.post("/pipeline/entries")
async def create_pipeline_entry(
    req: CreatePipelineEntryRequest,
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Create a new pipeline entry and auto-generate a 'created' changelog update."""
    user_id, jwt_token = _auth if _auth else (None, None)
    store = get_storage_backend(user_id, jwt_token)

    now = datetime.now(timezone.utc).isoformat()
    entries: list[dict] = store.read("pipeline_entries.json") or []

    # Compute sort_order: place at end of the target stage
    stage_entries = [e for e in entries if e.get("stage") == req.stage]
    max_order = max((e.get("sort_order", 0) for e in stage_entries), default=-1)

    new_entry = {
        "id": str(uuid.uuid4()),
        "company_name": req.company_name,
        "role_title": req.role_title,
        "stage": req.stage,
        "note": req.note,
        "next_action": req.next_action,
        "badge": req.badge,
        "tags": req.tags,
        "sort_order": max_order + 1,
        "created_at": now,
        "updated_at": now,
    }
    entries.append(new_entry)
    store.write("pipeline_entries.json", entries)

    # Auto-create a "created" changelog update
    updates: list[dict] = store.read("pipeline_updates.json") or []
    updates.insert(0, {
        "id": str(uuid.uuid4()),
        "entry_id": new_entry["id"],
        "update_type": "created",
        "from_stage": None,
        "to_stage": req.stage,
        "message": f"Added {req.company_name} to pipeline",
        "created_at": now,
    })
    store.write("pipeline_updates.json", updates)

    return new_entry


@router.put("/pipeline/entries/{entry_id}")
async def update_pipeline_entry(
    entry_id: str,
    req: UpdatePipelineEntryRequest,
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Update an existing pipeline entry. Auto-creates a changelog entry on stage change."""
    user_id, jwt_token = _auth if _auth else (None, None)
    store = get_storage_backend(user_id, jwt_token)

    entries: list[dict] = store.read("pipeline_entries.json") or []
    target = None
    for entry in entries:
        if entry.get("id") == entry_id:
            target = entry
            break
    if target is None:
        raise HTTPException(status_code=404, detail=f"Pipeline entry '{entry_id}' not found.")

    now = datetime.now(timezone.utc).isoformat()
    old_stage = target.get("stage")

    # Apply partial updates
    for field in ("company_name", "role_title", "stage", "note", "next_action", "badge", "tags", "sort_order"):
        val = getattr(req, field, None)
        if val is not None:
            target[field] = val
    target["updated_at"] = now

    store.write("pipeline_entries.json", entries)

    # Auto-create stage_change update if stage changed
    new_stage = target.get("stage")
    if req.stage is not None and new_stage != old_stage:
        updates: list[dict] = store.read("pipeline_updates.json") or []
        updates.insert(0, {
            "id": str(uuid.uuid4()),
            "entry_id": entry_id,
            "update_type": "stage_change",
            "from_stage": old_stage,
            "to_stage": new_stage,
            "message": f"{target.get('company_name', '')} moved from {old_stage} to {new_stage}",
            "created_at": now,
        })
        store.write("pipeline_updates.json", updates)

    return target


@router.delete("/pipeline/entries/{entry_id}")
async def delete_pipeline_entry(
    entry_id: str,
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Delete a pipeline entry. Associated updates are cascade-deleted by the DB."""
    user_id, jwt_token = _auth if _auth else (None, None)
    store = get_storage_backend(user_id, jwt_token)

    entries: list[dict] = store.read("pipeline_entries.json") or []
    new_entries = [e for e in entries if e.get("id") != entry_id]
    if len(new_entries) == len(entries):
        raise HTTPException(status_code=404, detail=f"Pipeline entry '{entry_id}' not found.")

    store.write("pipeline_entries.json", new_entries)

    # Also remove updates for this entry (for local/JSON mode; DB cascade handles Supabase)
    updates: list[dict] = store.read("pipeline_updates.json") or []
    updates = [u for u in updates if u.get("entry_id") != entry_id]
    store.write("pipeline_updates.json", updates)

    return {"ok": True}


@router.post("/pipeline/entries/reorder")
async def reorder_pipeline_entries(
    req: ReorderPipelineRequest,
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Batch update sort_order and stage for drag-and-drop moves."""
    user_id, jwt_token = _auth if _auth else (None, None)
    store = get_storage_backend(user_id, jwt_token)

    entries: list[dict] = store.read("pipeline_entries.json") or []
    entry_map = {e["id"]: e for e in entries}

    now = datetime.now(timezone.utc).isoformat()
    stage_changes: list[tuple[dict, str, str]] = []

    for move in req.moves:
        entry = entry_map.get(move.get("id", ""))
        if not entry:
            continue
        old_stage = entry["stage"]
        entry["sort_order"] = move.get("sort_order", entry["sort_order"])
        entry["updated_at"] = now
        new_stage = move.get("stage")
        if new_stage and new_stage != old_stage:
            entry["stage"] = new_stage
            stage_changes.append((entry, old_stage, new_stage))

    store.write("pipeline_entries.json", list(entry_map.values()))

    # Auto-create stage_change updates
    if stage_changes:
        updates: list[dict] = store.read("pipeline_updates.json") or []
        for entry, old_s, new_s in stage_changes:
            updates.insert(0, {
                "id": str(uuid.uuid4()),
                "entry_id": entry["id"],
                "update_type": "stage_change",
                "from_stage": old_s,
                "to_stage": new_s,
                "message": f"{entry.get('company_name', '')} moved from {old_s} to {new_s}",
                "created_at": now,
            })
        store.write("pipeline_updates.json", updates)

    return {"ok": True}


# ── Updates (Changelog) ─────────────────────────────────────────────────────


@router.get("/pipeline/updates")
async def list_pipeline_updates(
    entry_id: str | None = None,
    limit: int = 50,
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Return pipeline changelog updates, optionally filtered by entry_id."""
    user_id, jwt_token = _auth if _auth else (None, None)
    store = get_storage_backend(user_id, jwt_token)
    updates: list[dict] = store.read("pipeline_updates.json") or []
    if entry_id:
        updates = [u for u in updates if u.get("entry_id") == entry_id]
    if limit > 0:
        updates = updates[:limit]
    return {"updates": updates, "total": len(updates)}


@router.post("/pipeline/updates")
async def create_pipeline_update(
    req: CreatePipelineUpdateRequest,
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Create a manual changelog update/note for a pipeline entry."""
    user_id, jwt_token = _auth if _auth else (None, None)
    store = get_storage_backend(user_id, jwt_token)

    # Verify the entry exists
    entries: list[dict] = store.read("pipeline_entries.json") or []
    if not any(e.get("id") == req.entry_id for e in entries):
        raise HTTPException(status_code=404, detail=f"Pipeline entry '{req.entry_id}' not found.")

    now = datetime.now(timezone.utc).isoformat()
    new_update = {
        "id": str(uuid.uuid4()),
        "entry_id": req.entry_id,
        "update_type": "note",
        "from_stage": None,
        "to_stage": None,
        "message": req.message,
        "created_at": now,
    }
    updates: list[dict] = store.read("pipeline_updates.json") or []
    updates.insert(0, new_update)
    store.write("pipeline_updates.json", updates)

    return new_update


# ── Stats ────────────────────────────────────────────────────────────────────


@router.get("/pipeline/stats")
async def get_pipeline_stats(
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Return per-stage counts for funnel visualization."""
    user_id, jwt_token = _auth if _auth else (None, None)
    store = get_storage_backend(user_id, jwt_token)
    entries: list[dict] = store.read("pipeline_entries.json") or []
    counts: dict[str, int] = {}
    for e in entries:
        s = e.get("stage", "not_started")
        counts[s] = counts.get(s, 0) + 1
    return {"stage_counts": counts, "total": len(entries)}


# ── Sync (Gmail + Calendar + LLM) ────────────────────────────────────────────


@router.post("/pipeline/sync")
async def sync_pipeline(
    req: PipelineSyncRequest | None = None,
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Sync pipeline with external sources (Gmail, Calendar) and run LLM reasoning.

    Returns signals and suggestions for the user to review before applying.
    """
    user_id, jwt_token = _auth if _auth else (None, None)
    store = get_storage_backend(user_id, jwt_token)
    entries: list[dict] = store.read("pipeline_entries.json") or []

    google_connected = False
    gmail_signals: list[dict] = []
    calendar_signals: list[dict] = []

    # ── Gmail + Calendar scan (requires Google tokens) ────────────────────
    if user_id and os.environ.get("SUPABASE_URL"):
        from jobfinder.storage.vault import get_google_tokens

        tokens = get_google_tokens(user_id)
        if tokens and tokens.get("refresh_token"):
            google_connected = True

            from jobfinder.pipeline.gmail import scan_gmail
            from jobfinder.pipeline.calendar import scan_calendar

            raw_gmail = await asyncio.to_thread(scan_gmail, tokens, entries)
            gmail_signals = [s.to_dict() for s in raw_gmail]

            raw_calendar = await asyncio.to_thread(scan_calendar, tokens, entries)
            calendar_signals = [s.to_dict() for s in raw_calendar]

    # ── LLM reasoning (requires user's API key) ──────────────────────────
    llm_available = False
    suggestions: list[dict] = []
    new_companies: list[dict] = []
    summary: str | None = None

    if gmail_signals or calendar_signals:
        from jobfinder.config import load_config, resolve_api_key

        overrides: dict = {}
        if req and req.model_provider:
            overrides["model_provider"] = req.model_provider
        config = load_config(**overrides)

        try:
            api_key = resolve_api_key(config.model_provider, user_id)
            llm_available = True

            from jobfinder.pipeline.reasoning import reason_pipeline

            result = await asyncio.to_thread(
                reason_pipeline,
                entries,
                gmail_signals,
                calendar_signals,
                api_key,
                config.model_provider,
            )
            suggestions = [s.to_dict() for s in result.suggestions]
            new_companies = [c.to_dict() for c in result.new_companies]
            summary = result.summary
        except ValueError:
            pass  # No API key configured — skip LLM reasoning

    return {
        "gmail_signals": gmail_signals,
        "calendar_signals": calendar_signals,
        "suggestions": suggestions,
        "new_companies": new_companies,
        "summary": summary,
        "google_connected": google_connected,
        "llm_available": llm_available,
    }


@router.post("/pipeline/sync/apply")
async def apply_sync_suggestions(
    req: ApplySyncSuggestionsRequest,
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Apply accepted sync suggestions to the pipeline.

    The frontend sends the full suggestion data (cached from the sync response)
    for each suggestion the user approved.
    """
    user_id, jwt_token = _auth if _auth else (None, None)
    store = get_storage_backend(user_id, jwt_token)
    entries: list[dict] = store.read("pipeline_entries.json") or []
    updates: list[dict] = store.read("pipeline_updates.json") or []
    now = datetime.now(timezone.utc).isoformat()

    applied = 0
    created = 0

    # Build entry lookup by ID
    entry_map = {e["id"]: e for e in entries}

    # ── Apply updates to existing entries ─────────────────────────────────
    for suggestion in req.suggestions:
        if not suggestion.entry_id or suggestion.entry_id not in entry_map:
            continue

        entry = entry_map[suggestion.entry_id]
        old_stage = entry.get("stage")

        if suggestion.suggested_stage and suggestion.suggested_stage != old_stage:
            entry["stage"] = suggestion.suggested_stage
            updates.insert(0, {
                "id": str(uuid.uuid4()),
                "entry_id": entry["id"],
                "update_type": "stage_change",
                "from_stage": old_stage,
                "to_stage": suggestion.suggested_stage,
                "message": f"{entry.get('company_name', '')} → {suggestion.suggested_stage} ({suggestion.source}: {suggestion.reason})",
                "created_at": now,
            })

        if suggestion.suggested_badge is not None:
            entry["badge"] = suggestion.suggested_badge or None
        if suggestion.suggested_next_action:
            entry["next_action"] = suggestion.suggested_next_action

        entry["updated_at"] = now
        applied += 1

    # ── Create new pipeline entries ───────────────────────────────────────
    for new_co in req.new_companies:
        stage = new_co.suggested_stage or "not_started"
        stage_entries = [e for e in entries if e.get("stage") == stage]
        max_order = max((e.get("sort_order", 0) for e in stage_entries), default=-1)

        new_entry = {
            "id": str(uuid.uuid4()),
            "company_name": new_co.company_name,
            "role_title": None,
            "stage": stage,
            "note": f"Detected via {new_co.source}: {new_co.reason}",
            "next_action": new_co.suggested_next_action,
            "badge": "new",
            "tags": [],
            "sort_order": max_order + 1,
            "created_at": now,
            "updated_at": now,
        }
        entries.append(new_entry)

        updates.insert(0, {
            "id": str(uuid.uuid4()),
            "entry_id": new_entry["id"],
            "update_type": "created",
            "from_stage": None,
            "to_stage": stage,
            "message": f"Added {new_co.company_name} (detected via {new_co.source})",
            "created_at": now,
        })
        created += 1

    store.write("pipeline_entries.json", entries)
    store.write("pipeline_updates.json", updates)

    return {"applied": applied, "created": created}
