from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from jobfinder.api.auth import get_current_user
from jobfinder.api.models import DiscoverRolesRequest, FetchBrowserRolesRequest
from jobfinder.company_runs.name_generator import generate_run_name
from jobfinder.config import AppConfig, RoleFilters, load_config, resolve_api_key
from jobfinder.roles.checkpoint import Checkpoint
from jobfinder.roles.discovery import discover_roles
from jobfinder.roles.errors import RateLimitError
from jobfinder.roles.metrics import RunMetricsCollector
from jobfinder.storage import get_storage_backend
from jobfinder.storage.backend import StorageBackend
from jobfinder.storage.registry import load_or_bootstrap_registry
from jobfinder.storage.schemas import DiscoveredCompany, DiscoveredRole, JobRun
from jobfinder.system_config import load_system_config
from jobfinder.utils.log_stream import get_logs_for_run, set_run_context

logger = logging.getLogger(__name__)

router = APIRouter()


def _make_checkpoint(store: StorageBackend) -> Checkpoint:
    return Checkpoint(store)


# ── Browser-agent shared helpers ──────────────────────────────────────────────

def _to_roles(
    jobs: list[dict],
    company_name: str,
    fetched_at: str,
) -> list[DiscoveredRole]:
    """Convert raw agent job dicts to DiscoveredRole objects."""
    result: list[DiscoveredRole] = []
    for j in jobs:
        try:
            result.append(
                DiscoveredRole(
                    company_name=company_name,
                    title=j.get("title", ""),
                    location=j.get("location") or "Unknown",
                    url=j.get("url") or "",
                    department=j.get("department") or None,
                    ats_type="career_page",
                    fetched_at=fetched_at,
                )
            )
        except Exception:
            pass
    return result


def _merge_to_file(
    role_dicts: list[dict],
    store: StorageBackend,
    existing_data: dict | None = None,
) -> None:
    """Upsert *role_dicts* into roles.json (dedup by URL, sort by score)."""
    data = existing_data if existing_data is not None else (store.read("roles.json") or {})
    existing = [DiscoveredRole.model_validate(r) for r in data.get("roles", [])]
    seen: dict[str, DiscoveredRole] = {r.url: r for r in existing}
    for d in role_dicts:
        try:
            r = DiscoveredRole.model_validate(d)
            if r.url:
                seen[r.url] = r
        except Exception:
            pass
    final = sorted(seen.values(), key=lambda r: -(r.relevance_score or 0))
    store.write("roles.json", {**data, "roles": [r.model_dump() for r in final]})


async def _score_browser_roles(
    company_name: str,
    config: AppConfig,
    store: StorageBackend,
    *,
    api_key: str | None = None,
) -> int:
    """Score all stored roles for *company_name*.  Returns count of scored roles."""
    if not config.relevance_score_criteria:
        return 0
    from jobfinder.roles.scorer import score_roles

    roles_data = store.read("roles.json") or {}
    all_roles = [DiscoveredRole.model_validate(r) for r in roles_data.get("roles", [])]
    company_roles = [r for r in all_roles if r.company_name == company_name]
    if not company_roles:
        return 0
    try:
        scored = await asyncio.to_thread(
            score_roles, company_roles, config.relevance_score_criteria, config,
            api_key=api_key,
        )
    except Exception:
        return 0
    other_roles = [r for r in all_roles if r.company_name != company_name]
    final = sorted(other_roles + scored, key=lambda r: -(r.relevance_score or 0))
    store.write("roles.json", {**roles_data, "roles": [r.model_dump() for r in final]})
    return len(scored)


def _persist_job_run(
    store: StorageBackend,
    job_run_id: str,
    run_name: str,
    company_run_id: str | None,
    companies_input: list[str],
    collector: RunMetricsCollector,
    started_at: str,
    *,
    status: str = "completed",
    parent_job_run_id: str | None = None,
    run_type: str = "api",
    existing_runs: list[dict] | None = None,
) -> None:
    """Build a JobRun from the collector and persist to job_runs.json."""
    sys_config = load_system_config()
    max_runs = sys_config.max_job_runs_per_user

    job_run = JobRun(
        id=job_run_id,
        run_name=run_name,
        company_run_id=company_run_id,
        parent_job_run_id=parent_job_run_id,
        run_type=run_type,
        status=status,
        companies_input=companies_input,
        metrics=collector.to_schema(),
        created_at=started_at,
        completed_at=datetime.now(timezone.utc).isoformat(),
    )

    runs = existing_runs if existing_runs is not None else (store.read("job_runs.json") or [])
    runs = [job_run.model_dump()] + runs
    store.write("job_runs.json", runs[:max_runs])


@router.post("/roles/discover")
async def discover_roles_endpoint(
    req: DiscoverRolesRequest,
    request: Request,
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Fetch open roles from ATS APIs, then apply filters and scoring.

    Set ``resume=true`` to continue a previous run that was interrupted by a
    rate-limit error.  The raw roles and partial filter/score progress are
    loaded from the checkpoint file instead of re-fetching from ATS APIs.

    Set ``company_names`` to fetch roles only for specific companies from the
    registry.  Omit to use all companies from the last discovery run.
    """
    user_id, jwt_token = _auth if _auth else (None, None)

    overrides: dict = {}
    if req.model_provider is not None:
        overrides["model_provider"] = req.model_provider
    if req.relevance_score_criteria is not None:
        overrides["relevance_score_criteria"] = req.relevance_score_criteria
    if req.role_filters is not None:
        overrides["role_filters"] = req.role_filters.model_dump()
    if req.skip_career_page is not None:
        overrides["skip_career_page"] = req.skip_career_page
    if req.enable_theirstack is not None:
        overrides["enable_theirstack"] = req.enable_theirstack
    if req.theirstack_max_results is not None:
        overrides["theirstack_max_results"] = req.theirstack_max_results

    store = get_storage_backend(user_id, jwt_token)
    cp = _make_checkpoint(store)

    # ── Create job run ────────────────────────────────────────────────────
    job_run_id = str(uuid.uuid4())
    existing_job_runs: list[dict] = store.read("job_runs.json") or []
    existing_run_names = {r.get("run_name", "") for r in existing_job_runs}
    # Also exclude company-run names for uniqueness
    existing_company_runs: list[dict] = store.read("company_runs.json") or []
    existing_run_names.update(r.get("run_name", "") for r in existing_company_runs)
    job_run_name = generate_run_name(existing_run_names)
    started_at = datetime.now(timezone.utc).isoformat()
    collector = RunMetricsCollector()
    set_run_context(job_run_id)

    companies_data = store.read("companies.json")

    # Resolve company_run_id → company_names (if provided)
    effective_company_names = req.company_names
    enable_yc_from_run = False
    if req.company_run_id and not effective_company_names:
        all_runs: list[dict] = store.read("company_runs.json") or []
        matched_run = next((r for r in all_runs if r.get("id") == req.company_run_id), None)
        if matched_run is None:
            raise HTTPException(
                status_code=404,
                detail=f"Company run '{req.company_run_id}' not found.",
            )
        effective_company_names = [c["name"] for c in matched_run.get("companies", [])]
        if matched_run.get("focus") == "startups":
            enable_yc_from_run = True

    # Auto-enable YC Jobs if the company run was tagged "startups" or explicitly requested
    if req.enable_yc_jobs or enable_yc_from_run:
        overrides["enable_yc_jobs"] = True

    config = load_config(**overrides)

    # Require companies.json only when not using explicit selection and not resuming
    if companies_data is None and not effective_company_names and not (req.resume and cp.exists()):
        raise HTTPException(
            status_code=400,
            detail="No companies found. Run company discovery first.",
        )
    companies_data = companies_data or {}

    # Resolve API key(s) for LLM features.
    # fuzzy/semantic: no API calls needed at all.
    # gemini-embedding: needs a Gemini key (for embedding API, not LLM generation).
    # llm filter / scoring: needs the configured model_provider key.
    api_key: str | None = None
    filter_api_key: str | None = None  # may differ from api_key for gemini-embedding
    _filter_strategy = (
        getattr(config.role_filters, "filter_strategy", "llm")
        if config.role_filters else "llm"
    )
    _local_strategy = _filter_strategy in ("fuzzy", "semantic", "gemini-embedding")

    if _filter_strategy == "gemini-embedding":
        try:
            filter_api_key = resolve_api_key("gemini", user_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if (config.role_filters and not _local_strategy) or config.relevance_score_criteria:
        try:
            api_key = resolve_api_key(config.model_provider, user_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # For non-gemini-embedding strategies, filter uses the same key as scoring
    if not filter_api_key:
        filter_api_key = api_key

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
        if effective_company_names:
            registry: list[dict] = load_or_bootstrap_registry(store)
            reg_map = {e["name"].lower(): e for e in registry}
            selected = [reg_map[n.lower()] for n in effective_company_names if n.lower() in reg_map]
            missing = [n for n in effective_company_names if n.lower() not in reg_map]
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

        def _on_progress(
            current_roles: list[DiscoveredRole],
            current_flagged: list,
        ) -> None:
            """Write incremental unfiltered snapshot so the UI can poll it."""
            flagged_dicts_snap = [f.model_dump() for f in current_flagged]
            store.write("roles_unfiltered.json", {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "total_roles": len(current_roles),
                "companies_fetched": len(companies) - len(flagged_dicts_snap),
                "companies_flagged": len(flagged_dicts_snap),
                "flagged_companies": flagged_dicts_snap,
                "roles": [r.model_dump() for r in current_roles],
                "in_progress": True,
            })

        try:
            roles, flagged = await asyncio.to_thread(
                discover_roles, companies, config,
                store=store, use_cache=effective_use_cache, on_progress=_on_progress,
                metrics=collector,
            )
        except Exception as exc:
            _persist_job_run(
                store, job_run_id, job_run_name, req.company_run_id,
                [c.name for c in companies], collector, started_at,
                status="failed", existing_runs=existing_job_runs,
            )
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

    # ── Persist final unfiltered snapshot ─────────────────────────────────────
    unfiltered_output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total_roles": len(roles),
        "companies_fetched": len(companies) - len(flagged_dicts),
        "companies_flagged": len(flagged_dicts),
        "flagged_companies": flagged_dicts,
        "roles": [r.model_dump() for r in roles],
        "in_progress": False,
    }
    store.write("roles_unfiltered.json", unfiltered_output)

    # ── Filter ────────────────────────────────────────────────────────────────
    # Split by source_path: ATS roles get full filter, TheirStack roles skip title.

    filtered_roles = roles
    if config.role_filters and roles:
        from jobfinder.roles.filters import filter_roles

        ats_roles = [r for r in roles if getattr(r, "source_path", "ats") != "theirstack"]
        ts_roles = [r for r in roles if getattr(r, "source_path", "ats") == "theirstack"]

        try:
            filtered_ats = (
                await asyncio.to_thread(
                    filter_roles,
                    ats_roles,
                    config.role_filters,
                    config,
                    checkpoint=cp,
                    resume_batches=resume_filter_batches,
                    resume_kept=resume_filter_kept,
                    api_key=filter_api_key,
                    metrics=collector,
                )
                if ats_roles else []
            )
            filtered_ts = (
                await asyncio.to_thread(
                    filter_roles,
                    ts_roles,
                    config.role_filters,
                    config,
                    api_key=filter_api_key,
                    skip_title=True,
                )
                if ts_roles else []
            )
            filtered_roles = filtered_ats + filtered_ts
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
                api_key=api_key,
                metrics=collector,
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
        "job_run_id": job_run_id,
        "job_run_name": job_run_name,
    }
    store.write("roles.json", output)

    # Clean up checkpoint — complete result is now in roles.json
    cp.delete()

    # ── Persist job run ───────────────────────────────────────────────────
    _persist_job_run(
        store, job_run_id, job_run_name, req.company_run_id,
        [c.name for c in companies], collector, started_at,
        status="completed", existing_runs=existing_job_runs,
    )
    set_run_context(None)

    return output


@router.post("/roles/discover/stream")
async def discover_roles_stream(
    req: DiscoverRolesRequest,
    request: Request,
    _auth: tuple[str, str] | None = Depends(get_current_user),
):
    """SSE-streaming version of role discovery.

    Keeps the connection alive via automatic keepalive pings (every 15 s)
    so reverse proxies (Render, Cloudflare, etc.) do not kill
    long-running requests.

    Events emitted:
      * ``progress`` — status message (e.g. "Fetching roles…")
      * ``done``     — final JSON result (same shape as POST /roles/discover)
      * ``error``    — error detail string
    """
    from sse_starlette.sse import EventSourceResponse

    user_id, jwt_token = _auth if _auth else (None, None)

    # ── Validate inputs (fail fast before opening the stream) ────────────
    overrides: dict = {}
    if req.model_provider is not None:
        overrides["model_provider"] = req.model_provider
    if req.relevance_score_criteria is not None:
        overrides["relevance_score_criteria"] = req.relevance_score_criteria
    if req.role_filters is not None:
        overrides["role_filters"] = req.role_filters.model_dump()
    if req.skip_career_page is not None:
        overrides["skip_career_page"] = req.skip_career_page
    if req.enable_theirstack is not None:
        overrides["enable_theirstack"] = req.enable_theirstack
    if req.theirstack_max_results is not None:
        overrides["theirstack_max_results"] = req.theirstack_max_results

    store = get_storage_backend(user_id, jwt_token)
    cp = _make_checkpoint(store)

    companies_data = store.read("companies.json")

    # Resolve company_run_id → company_names
    effective_company_names = req.company_names
    enable_yc_from_run = False
    if req.company_run_id and not effective_company_names:
        all_runs: list[dict] = store.read("company_runs.json") or []
        matched_run = next((r for r in all_runs if r.get("id") == req.company_run_id), None)
        if matched_run is None:
            raise HTTPException(
                status_code=404,
                detail=f"Company run '{req.company_run_id}' not found.",
            )
        effective_company_names = [c["name"] for c in matched_run.get("companies", [])]
        if matched_run.get("focus") == "startups":
            enable_yc_from_run = True

    if req.enable_yc_jobs or enable_yc_from_run:
        overrides["enable_yc_jobs"] = True

    config = load_config(**overrides)

    if companies_data is None and not effective_company_names and not (req.resume and cp.exists()):
        raise HTTPException(
            status_code=400,
            detail="No companies found. Run company discovery first.",
        )
    companies_data = companies_data or {}

    api_key: str | None = None
    filter_api_key: str | None = None
    _filter_strategy = (
        getattr(config.role_filters, "filter_strategy", "llm")
        if config.role_filters else "llm"
    )
    _local_strategy = _filter_strategy in ("fuzzy", "semantic", "gemini-embedding")

    if _filter_strategy == "gemini-embedding":
        try:
            filter_api_key = resolve_api_key("gemini", user_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if (config.role_filters and not _local_strategy) or config.relevance_score_criteria:
        try:
            api_key = resolve_api_key(config.model_provider, user_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not filter_api_key:
        filter_api_key = api_key

    # ── SSE generator ────────────────────────────────────────────────────

    async def event_generator():
        job_run_id = str(uuid.uuid4())
        existing_job_runs: list[dict] = store.read("job_runs.json") or []
        existing_run_names = {r.get("run_name", "") for r in existing_job_runs}
        existing_company_runs_list: list[dict] = store.read("company_runs.json") or []
        existing_run_names.update(r.get("run_name", "") for r in existing_company_runs_list)
        job_run_name = generate_run_name(existing_run_names)
        started_at = datetime.now(timezone.utc).isoformat()
        collector = RunMetricsCollector()
        set_run_context(job_run_id)

        try:
            yield {"event": "progress", "data": json.dumps({"message": "Starting role discovery…"})}

            # ── Resolve companies & fetch roles ──────────────────────────
            if req.resume and cp.exists():
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
                yield {"event": "progress", "data": json.dumps({"message": "Resumed from checkpoint."})}
            else:
                if effective_company_names:
                    registry: list[dict] = load_or_bootstrap_registry(store)
                    reg_map = {e["name"].lower(): e for e in registry}
                    selected = [reg_map[n.lower()] for n in effective_company_names if n.lower() in reg_map]
                    missing = [n for n in effective_company_names if n.lower() not in reg_map]
                    if missing:
                        yield {
                            "event": "error",
                            "data": json.dumps({"detail": f"Companies not found in registry: {', '.join(missing)}"}),
                        }
                        return
                    raw_companies = [
                        {**e, "reason": "", "discovered_at": "", "roles_fetched": False}
                        for e in selected
                    ]
                else:
                    raw_companies = companies_data.get("companies", [])

                companies = [DiscoveredCompany.model_validate(c) for c in raw_companies]
                effective_use_cache = req.use_cache and not req.refresh

                def _on_progress(
                    current_roles: list[DiscoveredRole],
                    current_flagged: list,
                ) -> None:
                    flagged_dicts_snap = [f.model_dump() for f in current_flagged]
                    store.write("roles_unfiltered.json", {
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                        "total_roles": len(current_roles),
                        "companies_fetched": len(companies) - len(flagged_dicts_snap),
                        "companies_flagged": len(flagged_dicts_snap),
                        "flagged_companies": flagged_dicts_snap,
                        "roles": [r.model_dump() for r in current_roles],
                        "in_progress": True,
                    })

                yield {"event": "progress", "data": json.dumps({"message": f"Fetching roles for {len(companies)} companies…"})}

                try:
                    roles, flagged = await asyncio.to_thread(
                        discover_roles, companies, config,
                        store=store, use_cache=effective_use_cache, on_progress=_on_progress,
                        metrics=collector,
                    )
                except Exception as exc:
                    _persist_job_run(
                        store, job_run_id, job_run_name, req.company_run_id,
                        [c.name for c in companies], collector, started_at,
                        status="failed", existing_runs=existing_job_runs,
                    )
                    yield {"event": "error", "data": json.dumps({"detail": f"Role discovery failed: {exc}"})}
                    return

                flagged_dicts = [f.model_dump() for f in flagged]
                cp.save_after_fetch(
                    raw_roles=roles,
                    flagged=flagged,
                    filter_config=config.role_filters.model_dump() if config.role_filters else None,
                    score_criteria=config.relevance_score_criteria,
                    filter_batch_size=100,
                    score_batch_size=60,
                )
                resume_filter_batches = 0
                resume_filter_kept = []
                resume_score_batches = 0

            yield {"event": "progress", "data": json.dumps({"message": f"Fetched {len(roles)} roles."})}

            # ── Persist unfiltered snapshot ───────────────────────────────
            unfiltered_output = {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "total_roles": len(roles),
                "companies_fetched": len(companies) - len(flagged_dicts),
                "companies_flagged": len(flagged_dicts),
                "flagged_companies": flagged_dicts,
                "roles": [r.model_dump() for r in roles],
                "in_progress": False,
            }
            store.write("roles_unfiltered.json", unfiltered_output)

            # ── Filter ───────────────────────────────────────────────────
            # Split by source_path: ATS roles get full filter, TheirStack skip title.
            filtered_roles = roles
            if config.role_filters and roles:
                from jobfinder.roles.filters import filter_roles

                ats_roles = [r for r in roles if getattr(r, "source_path", "ats") != "theirstack"]
                ts_roles = [r for r in roles if getattr(r, "source_path", "ats") == "theirstack"]

                yield {"event": "progress", "data": json.dumps({"message": "Filtering roles…"})}
                try:
                    filtered_ats = (
                        await asyncio.to_thread(
                            filter_roles,
                            ats_roles, config.role_filters, config,
                            checkpoint=cp,
                            resume_batches=resume_filter_batches,
                            resume_kept=resume_filter_kept,
                            api_key=filter_api_key,
                            metrics=collector,
                        )
                        if ats_roles else []
                    )
                    filtered_ts = (
                        await asyncio.to_thread(
                            filter_roles,
                            ts_roles, config.role_filters, config,
                            api_key=filter_api_key,
                            skip_title=True,
                        )
                        if ts_roles else []
                    )
                    filtered_roles = filtered_ats + filtered_ts
                except RateLimitError as exc:
                    yield {
                        "event": "error",
                        "data": json.dumps({
                            "detail": f"{exc}  ({len(roles)} raw roles saved — no re-fetching needed.)",
                            "status_code": 429,
                        }),
                    }
                    return

            # ── Score ────────────────────────────────────────────────────
            scored_roles = filtered_roles
            if config.relevance_score_criteria and filtered_roles:
                from jobfinder.roles.scorer import score_roles
                yield {"event": "progress", "data": json.dumps({"message": "Scoring roles…"})}
                try:
                    scored_roles = await asyncio.to_thread(
                        score_roles,
                        filtered_roles, config.relevance_score_criteria, config,
                        checkpoint=cp,
                        resume_batches=resume_score_batches,
                        api_key=api_key,
                        metrics=collector,
                    )
                except RateLimitError as exc:
                    yield {
                        "event": "error",
                        "data": json.dumps({
                            "detail": f"{exc}  (Filtering complete: {len(filtered_roles)} roles — no re-filtering needed.)",
                            "status_code": 429,
                        }),
                    }
                    return

            # ── Merge & persist ──────────────────────────────────────────
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
                "job_run_id": job_run_id,
                "job_run_name": job_run_name,
            }
            store.write("roles.json", output)
            cp.delete()

            _persist_job_run(
                store, job_run_id, job_run_name, req.company_run_id,
                [c.name for c in companies], collector, started_at,
                status="completed", existing_runs=existing_job_runs,
            )

            yield {"event": "done", "data": json.dumps(output)}

        except Exception as exc:
            logger.exception("Unexpected error in roles discovery stream")
            detail = str(exc)
            if "JWT expired" in detail or "PGRST303" in detail:
                detail = "Your session has expired — please refresh the page and try again."
            yield {"event": "error", "data": json.dumps({"detail": detail})}

        finally:
            set_run_context(None)

    return EventSourceResponse(event_generator(), sep="\n")


@router.get("/roles/unfiltered")
async def get_unfiltered_roles(_auth: tuple[str, str] | None = Depends(get_current_user)) -> dict:
    """Return raw/unfiltered role discovery results."""
    user_id, jwt_token = _auth if _auth else (None, None)
    store = get_storage_backend(user_id, jwt_token)
    data = store.read("roles_unfiltered.json")
    if data is None:
        raise HTTPException(status_code=404, detail="No unfiltered roles found.")
    return data


@router.get("/roles/checkpoint")
async def get_roles_checkpoint(_auth: tuple[str, str] | None = Depends(get_current_user)) -> dict:
    """Return summary of any saved checkpoint, or 404 if none exists."""
    user_id, jwt_token = _auth if _auth else (None, None)
    store = get_storage_backend(user_id, jwt_token)
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
async def get_roles(_auth: tuple[str, str] | None = Depends(get_current_user)) -> dict:
    """Return cached role discovery results."""
    user_id, jwt_token = _auth if _auth else (None, None)
    store = get_storage_backend(user_id, jwt_token)
    data = store.read("roles.json")
    if data is None:
        raise HTTPException(status_code=404, detail="No roles found. Run discovery first.")
    return data


@router.get("/roles/fetch-browser/stream")
async def stream_browser_fetch(
    company_name: str,
    request: Request,
    career_page_url_override: str | None = None,
    parent_job_run_id: str | None = None,
    _auth: tuple[str, str] | None = Depends(get_current_user),
):
    """Stream real-time browser-agent progress for a flagged company via SSE.

    Pass ``career_page_url_override`` to supply a URL when the registry entry has
    none configured (e.g. Workday companies without a stored career page URL).

    SSE event types emitted (``event`` field) and their JSON payloads:

    - ``jobs_batch``    — ``{jobs[], total_so_far}``  whenever new jobs are found
    - ``filter_result`` — ``{filtered[], kept, dropped}``  after LLM filter pipeline
    - ``score_result``  — ``{scored}``  emitted just before done/killed when scoring ran
    - ``done``          — ``{metrics}``  on clean completion
    - ``killed``        — ``{reason, partial_jobs, metrics}``  on time-limit or kill
    - ``error``         — ``{error_type, message, can_resume}``  on failure

    Connect with the browser's ``EventSource`` API.  Use ``DELETE
    /roles/fetch-browser/{company_name}`` to kill a running agent.
    """
    import asyncio
    import json
    from datetime import datetime, timezone

    from sse_starlette.sse import EventSourceResponse

    from jobfinder.roles.ats.browser_session import AgentMetrics, AgentSession
    from jobfinder.roles.ats.career_page import _run_browser_agent_streaming

    user_id, jwt_token = _auth if _auth else (None, None)

    config = load_config()
    store = get_storage_backend(user_id, jwt_token)

    # Resolve API key for LLM calls (browser agent, filters, scoring)
    try:
        api_key = resolve_api_key(config.model_provider, user_id)
    except ValueError:
        api_key = None  # Browser agent may not need LLM for all operations

    # ── Registry lookup ───────────────────────────────────────────────────────

    registry: list[dict] = load_or_bootstrap_registry(store)
    reg_map = {e["name"].lower(): e for e in registry}
    entry = reg_map.get(company_name.lower())
    if entry is None:
        raise HTTPException(
            status_code=400,
            detail=f"Company '{company_name}' not found in registry.",
        )
    career_page_url = entry.get("career_page_url") or career_page_url_override or ""
    if not career_page_url:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No career page URL on file for '{entry['name']}'. "
                f"Pass career_page_url_override to provide one."
            ),
        )

    # ── Job run setup ────────────────────────────────────────────────────────

    browser_job_run_id = str(uuid.uuid4())
    browser_existing_runs: list[dict] = store.read("job_runs.json") or []
    browser_existing_names = {r.get("run_name", "") for r in browser_existing_runs}
    browser_run_name = generate_run_name(browser_existing_names)
    browser_started_at = datetime.now(timezone.utc).isoformat()
    browser_collector = RunMetricsCollector()
    browser_collector.companies_total = 1
    set_run_context(browser_job_run_id)

    # ── Session setup ─────────────────────────────────────────────────────────

    session = AgentSession(
        company_name=entry["name"],
        event_queue=asyncio.Queue(maxsize=200),
        kill_event=asyncio.Event(),
        metrics=AgentMetrics(company_name=entry["name"]),
    )
    request.app.state.running_agents[(user_id, entry["name"])] = session

    # ── Local helpers (thin wrappers that bind entry / store / session) ─────────

    def _to_roles_local(jobs: list[dict]) -> list[DiscoveredRole]:
        return _to_roles(jobs, entry["name"], datetime.now(timezone.utc).isoformat())

    def _merge_local(role_dicts: list[dict]) -> None:
        _merge_to_file(role_dicts, store)

    async def _filter_and_post(jobs: list[dict]) -> None:
        """Run LLM filter on *jobs* and post a filter_result event to the queue."""
        if not jobs or not config.role_filters:
            return
        from jobfinder.roles.filters import filter_roles

        roles_objs = _to_roles_local(jobs)
        if not roles_objs:
            return
        # Browser-agent roles are scraped from HTML and rarely have posting dates.
        # The agent already received the date-filter hint in its task prompt, so we
        # skip posted_after here to avoid excluding every undated result.
        filters_for_agent = config.role_filters.model_copy(update={"posted_after": None})
        try:
            filtered = await asyncio.to_thread(
                filter_roles, roles_objs, filters_for_agent, config,
                api_key=api_key,
            )
        except Exception:
            return
        if filtered:
            try:
                await session.event_queue.put(
                    {
                        "type": "filter_result",
                        "filtered": [r.model_dump() for r in filtered],
                        "kept": len(filtered),
                        "dropped": len(jobs) - len(filtered),
                    }
                )
            except asyncio.QueueFull:
                pass

    # ── Start agent background task ───────────────────────────────────────────

    session.task = asyncio.create_task(
        _run_browser_agent_streaming(entry["name"], career_page_url, config, session, store, api_key=api_key)
    )

    # ── SSE generator ─────────────────────────────────────────────────────────

    async def event_generator():
        pending_filter_tasks: list[asyncio.Task] = []
        # Emit run_start so the client knows the job_run_id
        yield {
            "event": "run_start",
            "data": json.dumps({
                "type": "run_start",
                "job_run_id": browser_job_run_id,
                "run_name": browser_run_name,
                "parent_job_run_id": parent_job_run_id,
            }),
        }
        try:
            while True:
                # Kill agent when client disconnects
                if await request.is_disconnected():
                    session.kill_event.set()
                    if session.task and not session.task.done():
                        session.task.cancel()
                    break

                # Drain the event queue
                try:
                    event = session.event_queue.get_nowait()
                except asyncio.QueueEmpty:
                    # Exit if agent finished and nothing left to stream
                    if (
                        session.task is not None
                        and session.task.done()
                        and session.event_queue.empty()
                    ):
                        break
                    await asyncio.sleep(0.3)
                    continue

                event_type = event.get("type", "")

                # Kick off async filter for each batch (when filters configured)
                if event_type == "jobs_batch" and config.role_filters:
                    t = asyncio.create_task(_filter_and_post(event["jobs"]))
                    pending_filter_tasks.append(t)

                # Merge filtered roles into roles.json on each filter_result
                if event_type == "filter_result":
                    try:
                        _merge_local(event.get("filtered", []))
                    except Exception:
                        pass
                    # Prune completed tasks from the tracking list
                    pending_filter_tasks = [t for t in pending_filter_tasks if not t.done()]

                # Non-terminal: forward to the client immediately
                if event_type not in ("done", "killed", "error"):
                    yield {"event": event_type, "data": json.dumps(event)}
                    continue

                # ── Terminal event: flush filters → score → THEN yield ─────────
                # 1. Flush any in-flight filter tasks and drain late filter_results
                if pending_filter_tasks:
                    await asyncio.gather(*pending_filter_tasks, return_exceptions=True)
                    while not session.event_queue.empty():
                        try:
                            extra = session.event_queue.get_nowait()
                            if extra.get("type") == "filter_result":
                                try:
                                    _merge_local(extra.get("filtered", []))
                                except Exception:
                                    pass
                                yield {
                                    "event": "filter_result",
                                    "data": json.dumps(extra),
                                }
                        except asyncio.QueueEmpty:
                            break

                # 2. No filter configured: merge all collected partial roles at once
                if not config.role_filters and session.partial_roles:
                    all_dicts = [
                        r.model_dump()
                        for r in _to_roles_local(session.partial_roles)
                        if r.url
                    ]
                    try:
                        _merge_local(all_dicts)
                    except Exception:
                        pass

                # 3. Apply scoring (skip on "error" — roles may be incomplete)
                if event_type != "error" and config.relevance_score_criteria:
                    try:
                        n_scored = await _score_browser_roles(entry["name"], config, store, api_key=api_key)
                        if n_scored:
                            yield {
                                "event": "score_result",
                                "data": json.dumps(
                                    {"type": "score_result", "scored": n_scored}
                                ),
                            }
                    except Exception:
                        pass

                # 4. Persist browser job run metrics
                _status = {"done": "completed", "killed": "killed", "error": "failed"}.get(
                    event_type, "completed"
                )
                n_jobs = len(session.partial_roles)
                browser_collector.record_browser_agent(entry["name"], n_jobs)
                if n_jobs > 0:
                    browser_collector.companies_succeeded = 1
                else:
                    browser_collector.companies_failed = 1
                _persist_job_run(
                    store, browser_job_run_id, browser_run_name, None,
                    [entry["name"]], browser_collector, browser_started_at,
                    status=_status, parent_job_run_id=parent_job_run_id,
                    run_type="browser", existing_runs=browser_existing_runs,
                )

                # 5. Now yield the terminal event — client calls onDone() after scoring
                yield {"event": event_type, "data": json.dumps(event)}
                break

        finally:
            # Cancel any still-running filter tasks on exit
            for t in pending_filter_tasks:
                if not t.done():
                    t.cancel()
            request.app.state.running_agents.pop((user_id, entry["name"]), None)
            set_run_context(None)

    return EventSourceResponse(event_generator(), sep="\n")


@router.delete("/roles/fetch-browser/{company_name}")
async def kill_browser_fetch(
    company_name: str,
    request: Request,
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Kill a running browser-use agent by company name.

    Returns ``{killed, partial_jobs}`` on success; 404 if no agent is running.
    """
    user_id = _auth[0] if _auth else None
    running: dict = request.app.state.running_agents

    # Exact match first, then case-insensitive fallback — scoped to this user
    session = running.get((user_id, company_name))
    if session is None:
        for key, val in running.items():
            if key[0] == user_id and key[1].lower() == company_name.lower():
                session = val
                company_name = key[1]
                break

    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"No running browser agent for '{company_name}'.",
        )

    session.kill_event.set()
    if session.task and not session.task.done():
        session.task.cancel()

    return {"killed": True, "partial_jobs": len(session.partial_roles)}


@router.post("/roles/fetch-browser")
async def fetch_browser_roles(
    req: FetchBrowserRolesRequest,
    request: Request,
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Use a browser-use agent to fetch roles for a single flagged company.

    The company must exist in the registry (i.e. it was previously discovered).
    Newly found roles are merged into roles.json (deduped by URL).

    Returns ``{ company_name, roles_found, roles }``.
    """
    user_id, jwt_token = _auth if _auth else (None, None)
    config = load_config()
    store = get_storage_backend(user_id, jwt_token)

    # Resolve API key for browser agent LLM
    try:
        api_key = resolve_api_key(config.model_provider, user_id)
    except ValueError:
        api_key = None

    # Look up the company in the per-user registry
    registry: list[dict] = load_or_bootstrap_registry(store)
    reg_map = {e["name"].lower(): e for e in registry}
    entry = reg_map.get(req.company_name.lower())
    if entry is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Company '{req.company_name}' not found in registry. "
                "Run discover-companies first."
            ),
        )

    career_page_url = entry.get("career_page_url") or ""
    if not career_page_url:
        raise HTTPException(
            status_code=400,
            detail=f"No career page URL on file for '{req.company_name}'.",
        )

    # Run the browser agent in a thread pool to avoid blocking the event loop
    from jobfinder.roles.ats.career_page import fetch_career_page_roles_browser

    try:
        roles = await asyncio.to_thread(
            fetch_career_page_roles_browser,
            entry["name"],
            career_page_url,
            config,
        )
    except RuntimeError as exc:
        # browser-use / langchain not installed
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Browser agent failed: {exc}"
        ) from exc

    # Merge new roles into roles.json (new wins on URL collision)
    _merge_to_file([r.model_dump() for r in roles], store)

    # Apply relevance scoring to the newly stored roles
    if config.relevance_score_criteria:
        await _score_browser_roles(entry["name"], config, store, api_key=api_key)

    return {
        "company_name": entry["name"],
        "roles_found": len(roles),
        "roles": [r.model_dump() for r in roles],
    }
