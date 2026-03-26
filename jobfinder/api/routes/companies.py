from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from jobfinder.api.auth import get_current_user
from jobfinder.api.models import DiscoverCompaniesRequest
from jobfinder.companies.discovery import discover_companies
from jobfinder.company_runs.name_generator import generate_run_name
from jobfinder.config import load_config, resolve_api_key
from jobfinder.storage import get_storage_backend
from jobfinder.storage.registry import load_or_bootstrap_registry, upsert_registry
from jobfinder.storage.schemas import DiscoveredCompany
from jobfinder.system_config import load_system_config

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/companies/discover")
async def discover_companies_endpoint(
    req: DiscoverCompaniesRequest,
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Run LLM-based company discovery and return the results."""
    user_id, jwt_token = _auth if _auth else (None, None)

    overrides: dict = {}
    if req.max_companies is not None:
        overrides["max_companies"] = req.max_companies
    if req.model_provider is not None:
        overrides["model_provider"] = req.model_provider

    config = load_config(**overrides)
    sys_config = load_system_config()
    store = get_storage_backend(user_id, jwt_token)

    # Resolve API key: user Vault → server env var fallback
    try:
        api_key = resolve_api_key(config.model_provider, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    seed_companies = req.seed_companies or None
    resumes: list[dict] = []
    source_id: str

    if seed_companies:
        # Seed mode: generate a transient UUID for this seed list
        source_id = str(uuid.uuid4())
    else:
        # Resume mode: look up the selected resume by ID
        all_resumes = store.read("resumes.json") or []
        if not all_resumes:
            raise HTTPException(status_code=400, detail="No resume found. Upload a resume first.")

        if req.resume_id:
            available_ids = [r.get("id") for r in all_resumes]
            logger.warning(
                "Looking up resume_id=%s among %d resume(s): %s",
                req.resume_id, len(all_resumes), available_ids,
            )
            matched = [r for r in all_resumes if r.get("id") == req.resume_id]
            if not matched:
                logger.warning(
                    "Resume ID mismatch: requested=%s, available=%s, raw_data_keys=%s",
                    req.resume_id, available_ids,
                    [list(r.keys()) for r in all_resumes],
                )
                raise HTTPException(
                    status_code=400,
                    detail=f"Resume with id '{req.resume_id}' not found.",
                )
            resumes = matched
            source_id = req.resume_id
        else:
            # Fallback: use the first resume when no ID is specified
            resumes = all_resumes[:1]
            source_id = resumes[0].get("id") or str(uuid.uuid4())

    # Load motivation summary if a completed one exists
    motivation_summary: str | None = None
    try:
        motivation = store.read("user_motivation.json")
        if motivation and motivation.get("status") == "completed" and motivation.get("summary"):
            motivation_summary = motivation["summary"]
    except Exception:
        pass  # Table may not exist yet; gracefully skip

    # Run blocking LLM call in a thread pool
    try:
        companies = await asyncio.to_thread(
            discover_companies, resumes, config,
            seed_companies=seed_companies, api_key=api_key,
            motivation_summary=motivation_summary,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Company discovery failed: {exc}") from exc

    # Merge with existing companies.json if configured (legacy last-run store)
    if config.write_preference == "merge" and store.exists("companies.json"):
        existing_data = store.read("companies.json") or {}
        existing = [
            DiscoveredCompany.model_validate(c)
            for c in existing_data.get("companies", [])
        ]
        seen: dict[str, DiscoveredCompany] = {c.name.lower(): c for c in existing}
        for c in companies:
            seen[c.name.lower()] = c
        companies = list(seen.values())

    discovered_at = datetime.now(timezone.utc).isoformat()

    # Write legacy companies.json (backwards-compat for "last-run" source mode)
    legacy_output = {
        "discovered_at": discovered_at,
        "companies": [c.model_dump() for c in companies],
    }
    store.write("companies.json", legacy_output)

    # ── Create and persist the company run ────────────────────────────────────
    existing_runs: list[dict] = store.read("company_runs.json") or []
    existing_names = {r["run_name"] for r in existing_runs}
    run_name = generate_run_name(existing_names)
    run_id = str(uuid.uuid4())

    new_run = {
        "id": run_id,
        "run_name": run_name,
        "source_type": "seed" if seed_companies else "resume",
        "source_id": source_id,
        "seed_companies": list(seed_companies) if seed_companies else None,
        "focus": req.focus,
        "companies": [c.model_dump() for c in companies],
        "created_at": discovered_at,
    }

    # Prepend new run; evict oldest if over the limit
    updated_runs = [new_run] + existing_runs
    max_runs = sys_config.max_company_runs_per_user
    if len(updated_runs) > max_runs:
        updated_runs = updated_runs[:max_runs]

    store.write("company_runs.json", updated_runs)

    # Upsert discovered companies into the perpetual registry
    upsert_registry(store, companies)

    return {
        **legacy_output,
        "run_id": run_id,
        "run_name": run_name,
    }


@router.post("/companies/discover/stream")
async def discover_companies_stream(
    req: DiscoverCompaniesRequest,
    _auth: tuple[str, str] | None = Depends(get_current_user),
):
    """SSE-streaming version of company discovery.

    Keeps the connection alive via automatic keepalive pings (every 15 s)
    so reverse proxies (Render, Cloudflare, etc.) do not kill
    long-running requests.

    Events emitted:
      * ``progress`` — status message
      * ``done``     — final JSON result (same shape as POST /companies/discover)
      * ``error``    — error detail string
    """
    from sse_starlette.sse import EventSourceResponse

    user_id, jwt_token = _auth if _auth else (None, None)

    # ── Validate inputs (fail fast before opening the stream) ────────────
    overrides: dict = {}
    if req.max_companies is not None:
        overrides["max_companies"] = req.max_companies
    if req.model_provider is not None:
        overrides["model_provider"] = req.model_provider

    config = load_config(**overrides)
    sys_config = load_system_config()
    store = get_storage_backend(user_id, jwt_token)

    try:
        api_key = resolve_api_key(config.model_provider, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    seed_companies = req.seed_companies or None
    resumes: list[dict] = []
    source_id: str

    if seed_companies:
        source_id = str(uuid.uuid4())
    else:
        all_resumes = store.read("resumes.json") or []
        if not all_resumes:
            raise HTTPException(status_code=400, detail="No resume found. Upload a resume first.")

        if req.resume_id:
            matched = [r for r in all_resumes if r.get("id") == req.resume_id]
            if not matched:
                raise HTTPException(
                    status_code=400,
                    detail=f"Resume with id '{req.resume_id}' not found.",
                )
            resumes = matched
            source_id = req.resume_id
        else:
            resumes = all_resumes[:1]
            source_id = resumes[0].get("id") or str(uuid.uuid4())

    motivation_summary: str | None = None
    try:
        motivation = store.read("user_motivation.json")
        if motivation and motivation.get("status") == "completed" and motivation.get("summary"):
            motivation_summary = motivation["summary"]
    except Exception:
        pass

    # ── SSE generator ────────────────────────────────────────────────────

    async def event_generator():
        try:
            yield {"event": "progress", "data": json.dumps({"message": "Discovering companies…"})}

            try:
                companies = await asyncio.to_thread(
                    discover_companies, resumes, config,
                    seed_companies=seed_companies, api_key=api_key,
                    motivation_summary=motivation_summary,
                )
            except Exception as exc:
                yield {"event": "error", "data": json.dumps({"detail": f"Company discovery failed: {exc}"})}
                return

            # Merge with existing if configured
            if config.write_preference == "merge" and store.exists("companies.json"):
                existing_data = store.read("companies.json") or {}
                existing = [
                    DiscoveredCompany.model_validate(c)
                    for c in existing_data.get("companies", [])
                ]
                seen: dict[str, DiscoveredCompany] = {c.name.lower(): c for c in existing}
                for c in companies:
                    seen[c.name.lower()] = c
                companies = list(seen.values())

            discovered_at = datetime.now(timezone.utc).isoformat()

            legacy_output = {
                "discovered_at": discovered_at,
                "companies": [c.model_dump() for c in companies],
            }
            store.write("companies.json", legacy_output)

            # Create and persist company run
            existing_runs: list[dict] = store.read("company_runs.json") or []
            existing_names = {r["run_name"] for r in existing_runs}
            run_name = generate_run_name(existing_names)
            run_id = str(uuid.uuid4())

            new_run = {
                "id": run_id,
                "run_name": run_name,
                "source_type": "seed" if seed_companies else "resume",
                "source_id": source_id,
                "seed_companies": list(seed_companies) if seed_companies else None,
                "focus": req.focus,
                "companies": [c.model_dump() for c in companies],
                "created_at": discovered_at,
            }

            updated_runs = [new_run] + existing_runs
            max_runs = sys_config.max_company_runs_per_user
            if len(updated_runs) > max_runs:
                updated_runs = updated_runs[:max_runs]
            store.write("company_runs.json", updated_runs)

            upsert_registry(store, companies)

            output = {**legacy_output, "run_id": run_id, "run_name": run_name}
            yield {"event": "done", "data": json.dumps(output)}

        except Exception as exc:
            logger.exception("Unexpected error in company discovery stream")
            yield {"event": "error", "data": json.dumps({"detail": str(exc)})}

    return EventSourceResponse(event_generator())


@router.get("/companies/registry")
async def get_company_registry(_auth: tuple[str, str] | None = Depends(get_current_user)) -> dict:
    """Return all companies from the perpetual registry (per-user)."""
    user_id, jwt_token = _auth if _auth else (None, None)
    store = get_storage_backend(user_id, jwt_token)
    return {"companies": load_or_bootstrap_registry(store)}


@router.get("/companies")
async def get_companies(_auth: tuple[str, str] | None = Depends(get_current_user)) -> dict:
    """Return cached company discovery results."""
    user_id, jwt_token = _auth if _auth else (None, None)
    store = get_storage_backend(user_id, jwt_token)
    data = store.read("companies.json")
    if data is None:
        raise HTTPException(status_code=404, detail="No companies found. Run discovery first.")
    return data
