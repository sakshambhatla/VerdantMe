from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from jobfinder.api.models import DiscoverRolesRequest
from jobfinder.config import RoleFilters, load_config, require_api_key
from jobfinder.roles.checkpoint import CHECKPOINT_FILENAME, Checkpoint
from jobfinder.roles.discovery import discover_roles
from jobfinder.roles.errors import RateLimitError
from jobfinder.storage.schemas import DiscoveredCompany, DiscoveredRole
from jobfinder.storage.store import StorageManager

router = APIRouter()


def _make_checkpoint(store: StorageManager) -> Checkpoint:
    return Checkpoint(store.data_dir / CHECKPOINT_FILENAME)


@router.post("/roles/discover")
async def discover_roles_endpoint(req: DiscoverRolesRequest, request: Request) -> dict:
    """Fetch open roles from ATS APIs, then apply filters and scoring.

    Set ``resume=true`` to continue a previous run that was interrupted by a
    rate-limit error.  The raw roles and partial filter/score progress are
    loaded from the checkpoint file instead of re-fetching from ATS APIs.

    Set ``company_names`` to fetch roles only for specific companies from the
    registry.  Omit to use all companies from the last discovery run.
    """
    overrides: dict = {}
    if req.model_provider is not None:
        overrides["model_provider"] = req.model_provider
    if req.relevance_score_criteria is not None:
        overrides["relevance_score_criteria"] = req.relevance_score_criteria
    if req.role_filters is not None:
        overrides["role_filters"] = req.role_filters.model_dump()

    config = load_config(**overrides)
    store = StorageManager(config.data_dir)
    cp = _make_checkpoint(store)

    companies_data = store.read("companies.json")
    # Require companies.json only when not using registry selection and not resuming
    if companies_data is None and not req.company_names and not (req.resume and cp.exists()):
        raise HTTPException(
            status_code=400,
            detail="No companies found. Run company discovery first.",
        )
    companies_data = companies_data or {}

    # Ensure API key is present if LLM features are needed
    if config.role_filters or config.relevance_score_criteria:
        try:
            require_api_key(config.model_provider)
        except SystemExit as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # ── Determine whether to resume or start fresh ────────────────────────────

    if req.resume and cp.exists():
        # Load saved state — skip ATS fetching entirely
        cp.load()
        raw_companies = companies_data.get("companies", [])
        companies = [DiscoveredCompany.model_validate(c) for c in raw_companies]
        roles = [DiscoveredRole.model_validate(r) for r in cp.raw_roles]
        flagged_dicts = cp.flagged_companies
        resume_filter_batches = cp.filter_batches_done
        resume_filter_kept = [
            DiscoveredRole.model_validate(r) for r in cp.filter_kept_roles
        ]
        resume_score_batches = cp.score_batches_done
    else:
        # Fresh run — resolve companies from registry or last-run file
        if req.company_names:
            registry: list[dict] = request.app.state.registry
            reg_map = {e["name"].lower(): e for e in registry}
            selected = [reg_map[n.lower()] for n in req.company_names if n.lower() in reg_map]
            missing = [n for n in req.company_names if n.lower() not in reg_map]
            if missing:
                raise HTTPException(
                    status_code=404,
                    detail=f"Companies not found in registry: {', '.join(missing)}",
                )
            raw_companies = [
                {**e, "reason": "", "discovered_at": "", "roles_fetched": False}
                for e in selected
            ]
        else:
            raw_companies = companies_data.get("companies", [])

        companies = [DiscoveredCompany.model_validate(c) for c in raw_companies]

        # --refresh overrides --use-cache: a fresh fetch always wins
        effective_use_cache = req.use_cache and not req.refresh
        try:
            roles, flagged = await asyncio.to_thread(
                discover_roles, companies, config, effective_use_cache
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Role discovery failed: {exc}"
            ) from exc

        flagged_dicts = [f.model_dump() for f in flagged]

        # Save checkpoint after successful ATS fetch so raw roles are never lost
        cp.save_after_fetch(
            raw_roles=roles,
            flagged=flagged,
            filter_config=config.role_filters.model_dump() if config.role_filters else None,
            score_criteria=config.relevance_score_criteria,
            filter_batch_size=100,   # mirrors filters.BATCH_SIZE
            score_batch_size=60,     # mirrors scorer.BATCH_SIZE
        )

        resume_filter_batches = 0
        resume_filter_kept = []
        resume_score_batches = 0

    # ── Filter ────────────────────────────────────────────────────────────────

    filtered_roles = roles
    if config.role_filters and roles:
        from jobfinder.roles.filters import filter_roles
        try:
            filtered_roles = await asyncio.to_thread(
                filter_roles,
                roles,
                config.role_filters,
                config,
                checkpoint=cp,
                resume_batches=resume_filter_batches,
                resume_kept=resume_filter_kept,
            )
        except RateLimitError as exc:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"{exc}  "
                    f"({len(roles)} raw roles saved — no re-fetching needed.)"
                ),
            ) from exc

    # ── Score ─────────────────────────────────────────────────────────────────

    scored_roles = filtered_roles
    if config.relevance_score_criteria and filtered_roles:
        from jobfinder.roles.scorer import score_roles
        try:
            scored_roles = await asyncio.to_thread(
                score_roles,
                filtered_roles,
                config.relevance_score_criteria,
                config,
                checkpoint=cp,
                resume_batches=resume_score_batches,
            )
        except RateLimitError as exc:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"{exc}  "
                    f"(Filtering complete: {len(filtered_roles)} roles — no re-filtering needed.)"
                ),
            ) from exc

    # ── Merge with existing if configured ────────────────────────────────────

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
        "companies_fetched": len(companies) - len(flagged_dicts),
        "companies_flagged": len(flagged_dicts),
        "flagged_companies": flagged_dicts,
        "roles": [r.model_dump() for r in final_roles],
    }
    store.write("roles.json", output)

    # Clean up checkpoint — complete result is now in roles.json
    cp.delete()

    return output


@router.get("/roles/checkpoint")
async def get_roles_checkpoint() -> dict:
    """Return summary of any saved checkpoint, or 404 if none exists."""
    config = load_config()
    store = StorageManager(config.data_dir)
    cp = _make_checkpoint(store)
    if not cp.exists():
        raise HTTPException(status_code=404, detail="No checkpoint found.")
    cp.load()
    return {
        "exists": True,
        "phase": cp.phase,
        "filter_batches_done": cp.filter_batches_done,
        "filter_total_batches": cp.filter_total_batches,
        "raw_roles_count": len(cp.raw_roles),
        "filter_kept_count": len(cp.filter_kept_roles),
        "summary": cp.summary(),
    }


@router.get("/roles")
async def get_roles() -> dict:
    """Return cached role discovery results."""
    config = load_config()
    store = StorageManager(config.data_dir)
    data = store.read("roles.json")
    if data is None:
        raise HTTPException(status_code=404, detail="No roles found. Run discovery first.")
    return data
