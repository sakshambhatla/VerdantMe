# jobfinder/roles — Claude Context

Handles everything after companies are discovered: fetching roles from ATS APIs, LLM filtering, and LLM relevance scoring.

## File Map
```
discovery.py   # discover_roles(companies, config) → (list[DiscoveredRole], list[FlaggedCompany])
filters.py     # filter_roles(roles, filters, config) → list[DiscoveredRole]
scorer.py      # score_roles(roles, criteria, config) → list[DiscoveredRole]  (sorted by score)
ats/
  __init__.py       # ATS_REGISTRY: dict[str, BaseFetcher] — maps ats_type → fetcher instance
  base.py           # BaseFetcher ABC; ATSFetchError, UnsupportedATSError
  greenhouse.py     # boards-api.greenhouse.io/v1/boards/{token}/jobs
  lever.py          # api.lever.co/v0/postings/{company}?mode=json
  ashby.py          # api.ashbyhq.com/posting-api/job-board/{token}
  unsupported.py    # raises UnsupportedATSError (Workday/LinkedIn/unknown)
  browser_session.py# AgentSession (queue + kill_event + task), AgentMetrics, RateLimitStrategy
  career_page.py    # Tier 2 HTML scraping + Tier 3 browser agent; _StreamingLLMWrapper,
                    # _run_browser_agent_streaming, _build_task_prompt, _maybe_save_api_profile
```

## ATS Fetching (`discovery.py`)
- Iterates companies, looks up fetcher via `ATS_REGISTRY[company.ats_type]`
- `UnsupportedATSError` → added to `flagged` list with career page URL for manual check
- `ATSFetchError` or any exception → also added to `flagged`, processing continues
- All three supported ATS (Greenhouse, Lever, Ashby) are **explicitly public APIs** — no auth, no ToS risk

**Adding a new ATS:**
1. Create `ats/<name>.py` subclassing `BaseFetcher`, implement `fetch(company) -> list[DiscoveredRole]`
2. Add entry to `ATS_REGISTRY` in `ats/__init__.py`
3. Update `DiscoveredCompany.ats_type` literal in `storage/schemas.py`
4. Update the LLM prompt in `companies/prompts.py` so it can emit the new type

## LLM Filtering (`filters.py`)
- **Batch size**: 100 roles/call
- **Input per role**: `title | location | date` (minimal tokens)
- **Output**: JSON array of matching 0-based indices — e.g. `[0, 3, 7]`
- **Confidence levels**: `high` (strict) · `medium` · `low` (inclusive) — maps to different system prompt instructions
- **Throttled**: calls `get_limiter(config.rpm_limit).wait()` before every LLM call
- Filter criteria are all optional; if none are set, returns the full list unchanged

## LLM Scoring (`scorer.py`)
- **Batch size**: 60 roles/call
- **Input per role**: `title | company | location | dept` (no date — not relevant to relevance)
- **Output**: JSON object `{"0": {"score": 9, "summary": "Platform eng, Spark"}, ...}`
- Both `score` (1–10) and `summary` (≤15 words) come from a single call
- Sets `role.relevance_score` and `role.summary` on each `DiscoveredRole`
- Returns list sorted by `relevance_score` descending
- `max_tokens=1024` (raised from 512 to fit summaries for large batches)
- **Throttled**: same rate limiter as filters

## Shared Rate Limiter
All LLM `_call_anthropic()` / `_call_gemini()` functions in this package call:
```python
from jobfinder.utils.throttle import get_limiter
get_limiter(config.rpm_limit).wait()
```
The limiter is a process-level singleton, so filter + scorer calls share the same sliding window.

## Browser Agent (Tier 3 — `ats/career_page.py`)

Used when a company's career page can't be read via a public API or static HTML scraping.

**Streaming architecture** (`_run_browser_agent_streaming`):
- `_StreamingLLMWrapper` wraps the LLM passed to `browser-use`. It intercepts every `ainvoke`/`invoke` call, parses the model's JSON response for a `jobs` array, and posts a `jobs_batch` event to `session.event_queue` in real time — so the SSE endpoint can stream partial results to the UI without waiting for the full run.
- The agent runs as a separate `asyncio.Task` via `_run_with_kill_check()`, which polls `session.kill_event.is_set()` every 500 ms. Setting the kill event causes the task to cancel cleanly.
- Hard time budget: `asyncio.wait_for(agent.run(), timeout=max_seconds)` in `_run_browser_agent_streaming`. A `TimeoutError` results in a `killed` (time_limit) terminal event.

**Kill signal flow**:
```
DELETE /roles/fetch-browser/{name}
  → session.kill_event.set()
  → session.task.cancel()
  → generator finally-block posts killed event and removes session from app.state.running_agents
```

**API profile injection** (`_build_task_prompt`):
- `load_profile(career_page_url, store)` — looks up the company domain in `data/api_profiles.json`
- If a profile exists (endpoint URL + query params from a prior successful run), it is injected verbatim into the task prompt so the agent skips re-discovery and goes straight to extraction
- On success, `_maybe_save_api_profile` writes the discovered endpoint back to `api_profiles.json`

**`AgentSession`** (`ats/browser_session.py`):
```python
@dataclass
class AgentSession:
    event_queue: asyncio.Queue      # maxsize=200; events streamed to SSE generator
    kill_event: asyncio.Event       # set by DELETE endpoint or time limit
    metrics: AgentMetrics           # steps_taken, jobs_collected, rate_limit_hits, …
    partial_roles: list             # accumulated DiscoveredRole objects
    task: asyncio.Task | None       # the running asyncio task; None until started
```
