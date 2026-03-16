from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from jobfinder.api.auth import get_current_user
from jobfinder.api.models import DiscoverCompaniesRequest
from jobfinder.companies.discovery import discover_companies
from jobfinder.config import load_config, require_api_key
from jobfinder.storage import get_storage_backend
from jobfinder.storage.registry import upsert_registry
from jobfinder.storage.schemas import DiscoveredCompany

router = APIRouter()


@router.post("/companies/discover")
async def discover_companies_endpoint(
    req: DiscoverCompaniesRequest,
    request: Request,
    user_id: str | None = Depends(get_current_user),
) -> dict:
    """Run LLM-based company discovery and return the results."""
    overrides: dict = {}
    if req.max_companies is not None:
        overrides["max_companies"] = req.max_companies
    if req.model_provider is not None:
        overrides["model_provider"] = req.model_provider

    config = load_config(**overrides)
    store = get_storage_backend(user_id)

    # Ensure API key is present before starting
    try:
        require_api_key(config.model_provider)
    except SystemExit as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    seed_companies = req.seed_companies or None
    resumes: list[dict] = []

    if not seed_companies:
        resumes = store.read("resumes.json") or []
        if not resumes:
            raise HTTPException(
                status_code=400,
                detail="No resume found. Upload a resume first.",
            )

    # Run blocking LLM call in a thread pool
    try:
        companies = await asyncio.to_thread(
            discover_companies, resumes, config, seed_companies=seed_companies
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Company discovery failed: {exc}") from exc

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

    import hashlib
    resume_text = "".join(r.get("full_text", "") for r in resumes)
    resume_hash = hashlib.sha256(resume_text.encode()).hexdigest()[:16]

    output = {
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "source_resume_hash": resume_hash,
        "companies": [c.model_dump() for c in companies],
    }
    store.write("companies.json", output)

    # Upsert discovered companies into the perpetual registry
    upsert_registry(store, companies)
    from jobfinder.api.main import reload_registry
    reload_registry(request.app)

    return output


@router.get("/companies/registry")
async def get_company_registry(request: Request) -> dict:
    """Return all companies from the perpetual registry (served from memory)."""
    return {"companies": request.app.state.registry}


@router.get("/companies")
async def get_companies(user_id: str | None = Depends(get_current_user)) -> dict:
    """Return cached company discovery results."""
    store = get_storage_backend(user_id)
    data = store.read("companies.json")
    if data is None:
        raise HTTPException(status_code=404, detail="No companies found. Run discovery first.")
    return data
