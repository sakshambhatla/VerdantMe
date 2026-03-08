from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from jobfinder.api.models import DiscoverRolesRequest
from jobfinder.config import RoleFilters, load_config, require_api_key
from jobfinder.roles.discovery import discover_roles
from jobfinder.storage.schemas import DiscoveredCompany, DiscoveredRole
from jobfinder.storage.store import StorageManager

router = APIRouter()


@router.post("/roles/discover")
async def discover_roles_endpoint(req: DiscoverRolesRequest) -> dict:
    """Fetch open roles from ATS APIs, then apply filters and scoring."""
    overrides: dict = {}
    if req.relevance_score_criteria is not None:
        overrides["relevance_score_criteria"] = req.relevance_score_criteria
    if req.role_filters is not None:
        overrides["role_filters"] = req.role_filters.model_dump()

    config = load_config(**overrides)
    store = StorageManager(config.data_dir)

    companies_data = store.read("companies.json")
    if not companies_data:
        raise HTTPException(
            status_code=400,
            detail="No companies found. Run company discovery first.",
        )

    raw_companies = companies_data.get("companies", [])

    # Filter to specific company if requested
    if req.company:
        raw_companies = [
            c for c in raw_companies if req.company.lower() in c["name"].lower()
        ]
        if not raw_companies:
            raise HTTPException(
                status_code=404,
                detail=f"No company matching '{req.company}' found.",
            )

    companies = [DiscoveredCompany.model_validate(c) for c in raw_companies]

    # Ensure API key is present if LLM features are needed
    if config.role_filters or config.relevance_score_criteria:
        try:
            require_api_key(config.model_provider)
        except SystemExit as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Fetch roles from ATS APIs (blocking HTTP calls → thread pool)
    try:
        roles, flagged = await asyncio.to_thread(discover_roles, companies, config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Role discovery failed: {exc}") from exc

    # Apply LLM-based filters if configured
    filtered_roles = roles
    if config.role_filters and roles:
        from jobfinder.roles.filters import filter_roles
        filtered_roles = await asyncio.to_thread(
            filter_roles, roles, config.role_filters, config
        )

    # Apply LLM-based relevance scoring if configured
    scored_roles = filtered_roles
    if config.relevance_score_criteria and filtered_roles:
        from jobfinder.roles.scorer import score_roles
        scored_roles = await asyncio.to_thread(
            score_roles, filtered_roles, config.relevance_score_criteria, config
        )

    # Merge with existing roles if configured
    final_roles = scored_roles
    if config.write_preference == "merge" and store.exists("roles.json"):
        existing_data = store.read("roles.json") or {}
        existing_roles = [
            DiscoveredRole.model_validate(r)
            for r in existing_data.get("roles", [])
        ]
        seen: dict[str, DiscoveredRole] = {r.url: r for r in existing_roles}
        for r in scored_roles:
            seen[r.url] = r
        final_roles = sorted(seen.values(), key=lambda r: -(r.relevance_score or 0))

    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total_roles": len(roles),
        "roles_after_filter": len(filtered_roles),
        "companies_fetched": len(companies) - len(flagged),
        "companies_flagged": len(flagged),
        "flagged_companies": [f.model_dump() for f in flagged],
        "roles": [r.model_dump() for r in final_roles],
    }
    store.write("roles.json", output)
    return output


@router.get("/roles")
async def get_roles() -> dict:
    """Return cached role discovery results."""
    config = load_config()
    store = StorageManager(config.data_dir)
    data = store.read("roles.json")
    if data is None:
        raise HTTPException(status_code=404, detail="No roles found. Run discovery first.")
    return data
