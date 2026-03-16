from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from jobfinder.api.auth import get_current_user
from jobfinder.api.models import DiscoverRolesRequest, FetchBrowserRolesRequest
from jobfinder.config import AppConfig, RoleFilters, load_config, require_api_key
from jobfinder.roles.checkpoint import Checkpoint
from jobfinder.roles.discovery import discover_roles
from jobfinder.roles.errors import RateLimitError
from jobfinder.storage import get_storage_backend
from jobfinder.storage.backend import StorageBackend
from jobfinder.storage.schemas import DiscoveredCompany, DiscoveredRole

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
            score_roles, company_roles, config.relevance_score_criteria, config
        )
    except Exception:
        return 0
    other_roles = [r for r in all_roles if r.company_name != company_name]
    final = sorted(other_roles + scored, key=lambda r: -(r.relevance_score or 0))
    store.write("roles.json", {**roles_data, "roles": [r.model_dump() for r in final]})
    return len(scored)


@router.post("/roles/discover")
async def discover_roles_endpoint(
    req: DiscoverRolesRequest,
    request: Request,
    user_id: str | None = Depends(get_current_user),
) -> dict:
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
    store = get_storage_backend(user_id)
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


@router.get("/roles/unfiltered")
async def get_unfiltered_roles(user_id: str | None = Depends(get_current_user)) -> dict:
    """Return raw/unfiltered role discovery results."""
    store = get_storage_backend(user_id)
    data = store.read("roles_unfiltered.json")
    if data is None:
        raise HTTPException(status_code=404, detail="No unfiltered roles found.")
    return data


@router.get("/roles/checkpoint")
async def get_roles_checkpoint(user_id: str | None = Depends(get_current_user)) -> dict:
    """Return summary of any saved checkpoint, or 404 if none exists."""
    store = get_storage_backend(user_id)
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
async def get_roles(user_id: str | None = Depends(get_current_user)) -> dict:
    """Return cached role discovery results."""
    store = get_storage_backend(user_id)
    data = store.read("roles.json")
    if data is None:
        raise HTTPException(status_code=404, detail="No roles found. Run discovery first.")
    return data


@router.get("/roles/fetch-browser/stream")
async def stream_browser_fetch(
    company_name: str,
    request: Request,
    career_page_url_override: str | None = None,
    user_id: str | None = Depends(get_current_user),
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

    config = load_config()
    store = get_storage_backend(user_id)

    # ── Registry lookup ───────────────────────────────────────────────────────

    registry: list[dict] = request.app.state.registry
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

    # ── Session setup ─────────────────────────────────────────────────────────

    session = AgentSession(
        company_name=entry["name"],
        event_queue=asyncio.Queue(maxsize=200),
        kill_event=asyncio.Event(),
        metrics=AgentMetrics(company_name=entry["name"]),
    )
    request.app.state.running_agents[entry["name"]] = session

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
                filter_roles, roles_objs, filters_for_agent, config
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
        _run_browser_agent_streaming(entry["name"], career_page_url, config, session, store)
    )

    # ── SSE generator ─────────────────────────────────────────────────────────

    async def event_generator():
        pending_filter_tasks: list[asyncio.Task] = []
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
                        n_scored = await _score_browser_roles(entry["name"], config, store)
                        if n_scored:
                            yield {
                                "event": "score_result",
                                "data": json.dumps(
                                    {"type": "score_result", "scored": n_scored}
                                ),
                            }
                    except Exception:
                        pass

                # 4. Now yield the terminal event — client calls onDone() after scoring
                yield {"event": event_type, "data": json.dumps(event)}
                break

        finally:
            # Cancel any still-running filter tasks on exit
            for t in pending_filter_tasks:
                if not t.done():
                    t.cancel()
            request.app.state.running_agents.pop(entry["name"], None)

    return EventSourceResponse(event_generator())


@router.delete("/roles/fetch-browser/{company_name}")
async def kill_browser_fetch(
    company_name: str,
    request: Request,
    user_id: str | None = Depends(get_current_user),
) -> dict:
    """Kill a running browser-use agent by company name.

    Returns ``{killed, partial_jobs}`` on success; 404 if no agent is running.
    """
    running: dict = request.app.state.running_agents

    # Exact match first, then case-insensitive fallback
    session = running.get(company_name)
    if session is None:
        for key, val in running.items():
            if key.lower() == company_name.lower():
                session = val
                company_name = key
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
    user_id: str | None = Depends(get_current_user),
) -> dict:
    """Use a browser-use agent to fetch roles for a single flagged company.

    The company must exist in the registry (i.e. it was previously discovered).
    Newly found roles are merged into roles.json (deduped by URL).

    Returns ``{ company_name, roles_found, roles }``.
    """
    config = load_config()
    store = get_storage_backend(user_id)

    # Look up the company in the in-memory registry
    registry: list[dict] = request.app.state.registry
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
        await _score_browser_roles(entry["name"], config, store)

    return {
        "company_name": entry["name"],
        "roles_found": len(roles),
        "roles": [r.model_dump() for r in roles],
    }
