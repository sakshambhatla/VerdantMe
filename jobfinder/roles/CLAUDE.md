# jobfinder/roles — Claude Context

Handles everything after companies are discovered: fetching roles from ATS APIs, filtering (LLM or local), LLM relevance scoring, and browser-agent fallback for unsupported career pages.

## File Map
```
discovery.py      # discover_roles(companies, config, store, use_cache, on_progress, metrics)
                  #   → (list[DiscoveredRole], list[FlaggedCompany])
filters.py        # filter_roles(roles, filters, config, checkpoint, ...) — LLM batch filtering
local_filters.py  # filter_roles_local(roles, filters) — fuzzy (rapidfuzz) + semantic (fastembed)
scorer.py         # score_roles(roles, criteria, config, checkpoint, ...) — LLM batch scoring
checkpoint.py     # Save/load/delete resumable pipeline state after rate-limit errors
cache.py          # RolesCache: 2-day TTL per company+ATS pair
metrics.py        # RunMetricsCollector: mutable metrics tracker → freezes to JobRunMetrics
errors.py         # RateLimitError exception
ats/
  __init__.py       # ATS_REGISTRY: dict[str, BaseFetcher] — maps ats_type → fetcher instance
  base.py           # BaseFetcher ABC; ATSFetchError, UnsupportedATSError
  greenhouse.py     # boards-api.greenhouse.io/v1/boards/{token}/jobs
  lever.py          # api.lever.co/v0/postings/{company}?mode=json
  ashby.py          # api.ashbyhq.com/posting-api/job-board/{token}
  unsupported.py    # raises UnsupportedATSError (Workday/LinkedIn/YCombinator/unknown)
  browser_session.py# AgentSession (queue + kill_event + task), AgentMetrics, RateLimitStrategy
  career_page.py    # Tier 2 HTML scraping + Tier 3 browser agent; _StreamingLLMWrapper,
                    # _run_browser_agent_streaming, _build_task_prompt, _maybe_save_api_profile
sources/
  __init__.py       # SOURCE_REGISTRY: dict[str, BaseJobSource]; get_enabled_sources(config)
  base.py           # BaseJobSource ABC; JobSourceError
  ycombinator.py    # Y Combinator Jobs via RapidAPI (free-y-combinator-jobs-api)
  cache.py          # ExternalSourceCache: per-source TTL (12h for YC)
```

## TheirStack Fallback (`theirstack/client.py`)

Pass 1.5 — used for companies with `ats_type="unknown"` when a `THEIRSTACK_API_KEY` is present.

**What we send to `/v1/jobs/search`:**
| Field | Source | Notes |
|-------|--------|-------|
| `company_name_or` | company name from registry | Exact-ish match — "Shopify" works, "Amazon" (vs "Amazon.com Services LLC") may not |
| `job_title_or` | `analyze_title(filters.title).broadened_title` | Seniority prefix stripped, abbreviations expanded |
| `job_seniority_or` | `analyze_title(filters.title).seniority` | Only if detected (e.g. "Senior" → `"senior"`) |
| `employment_statuses_or` | `analyze_title(filters.title).employment_type` | Only if detected (e.g. "Intern" → `"internship"`) |
| `job_location_pattern_or` | `map_location_to_theirstack_params(filters.location)` | City/metro regex patterns |
| `posted_at_max_age_days` | `filters.to_max_age_days()` | Converted from natural-language date |

**Critical pitfalls:**
- **Do NOT send `remote: true`** — TheirStack treats it as a strict AND (only remote-only postings), not an OR. Combined with `posted_at_max_age_days` it kills recall to near zero. Remote filtering is done post-fetch by the filter pipeline.
- **`company_name_or` is exact-ish** — large companies with subsidiary names (e.g. Amazon is "Amazon.com Services LLC" in TheirStack) may return 0 results. No workaround currently; use the debug log to diagnose.
- **All filters AND together** — every field you add further restricts results. TheirStack is a last-resort fallback, so prefer fewer filters for max recall.
- **Debug logs** — `client.py` logs the full request body and response count at `INFO` level so you can see exactly what was sent and returned.

## Discovery Pipeline (`discovery.py`)

Three-pass orchestrator with cache + progress callbacks:

**Pass 0 — External job boards** (if enabled): Queries aggregator APIs (e.g. YC Jobs via RapidAPI) that return roles across many companies. Controlled by `config.enable_yc_jobs`. Uses `ExternalSourceCache` (12h TTL for YC). Requires `RAPIDAPI_KEY` env var (server-level credential, not per-user). Gracefully skips if key not set or source fails.

**Pass 1 — ATS APIs**: Iterates companies, looks up fetcher via `ATS_REGISTRY[company.ats_type]`.
- `UnsupportedATSError` → added to `flagged` list with career page URL
- `ATSFetchError` or any exception → also added to `flagged`, processing continues
- All three supported ATS (Greenhouse, Lever, Ashby) are **explicitly public APIs** — no auth, no ToS risk
- If `use_cache=True`, checks `RolesCache` first (2-day TTL); skips fetch if fresh

**Pass 2 — Career page fallback** (if not `skip_career_page`): For flagged companies, tries `fetch_career_page_roles()` — Playwright HTML parsing + LLM extraction. Roles deduplicated by URL and merged with ATS results.

**Adding a new ATS:**
1. Create `ats/<name>.py` subclassing `BaseFetcher`, implement `fetch(company) -> list[DiscoveredRole]`
2. Add entry to `ATS_REGISTRY` in `ats/__init__.py`
3. Update `DiscoveredCompany.ats_type` literal in `storage/schemas.py`
4. Update the LLM prompt in `companies/prompts.py` so it can emit the new type

**Adding a new external job source (e.g. another RapidAPI):**
1. Create `sources/<name>.py` subclassing `BaseJobSource`, implement `fetch_all(api_key, timeout) -> list[DiscoveredRole]`
2. Add entry to `_REGISTRY` in `sources/__init__.py`
3. Add config flag (e.g. `enable_<name>: bool`) to `config.py:AppConfig`
4. Wire flag in `get_enabled_sources()` in `sources/__init__.py`
5. Add CLI flag (`--enable-<name>`) to `cli.py`

## LLM Filtering (`filters.py`)
- **Batch size**: 100 roles/call
- **Input per role**: `title | location | date` (minimal tokens)
- **Output**: JSON object `{"matches": [{"index": 0, "score": 92}, ...]}` — each match includes a 0-100 confidence score stored as `role.filter_score`
- **Confidence levels**: `high` (strict) · `medium` · `low` (inclusive) — maps to different system prompt instructions
- **Throttled**: calls `get_limiter(config.rpm_limit).wait()` before every LLM call
- Filter criteria are all optional; if none are set, returns the full list unchanged
- Supports checkpoint resume: skips already-processed batches via `checkpoint.filter_batches_done`

## Local Filtering (`local_filters.py`)

Non-LLM-generation alternatives — instant, free filtering:

**Fuzzy** (`filter_strategy="fuzzy"`): Uses rapidfuzz `token_set_ratio`. Confidence thresholds: high=82, medium=72, low=60. Zero memory overhead.

**Semantic** (`filter_strategy="semantic"`): Uses fastembed ONNX embeddings (cosine similarity). Requires `pip install "jobfinder[semantic]"`. Thresholds: high=0.72, medium=0.60, low=0.48. **Warning**: loads ~250 MB into memory (ONNX Runtime + model weights) — will OOM on Render free tier (512 MB).

**Gemini Embedding** (`filter_strategy="gemini-embedding"`): Uses Google's `text-embedding-005` API via `google-genai` SDK (already a dependency). Thresholds: high=0.70, medium=0.58, low=0.45. Zero local memory overhead — all embedding done server-side by Google. Free tier (1,500 req/min). Requires `GEMINI_API_KEY`. Batches at 100 texts per API call. Recommended for hosted/managed mode.

All three support metro-aware location matching with alias sets (e.g., SF/Bay Area/Silicon Valley/San Jose all match each other). Posted-after filtering uses `python-dateutil` for natural language date parsing.

**`filter_score`**: All four strategies (LLM, fuzzy, semantic, gemini-embedding) set `role.filter_score` (0–100 int) on each matched role — the title match confidence. Fuzzy: `token_set_ratio` (natively 0–100). Semantic/Gemini: cosine similarity × 100. LLM: prompt-reported confidence. Displayed in the UI "Match" column. `None` when no title filter was applied.

**API key threading for gemini-embedding**: The API route resolves a separate `filter_api_key` (Gemini) from the main `api_key` (model_provider, used for scoring). This allows gemini-embedding filtering with anthropic-based scoring.

## LLM Scoring (`scorer.py`)
- **Batch size**: 60 roles/call
- **Input per role**: `title | company | location | dept` (no date — not relevant to relevance)
- **Output**: JSON object `{"0": {"score": 9, "summary": "Platform eng, Spark"}, ...}`
- Both `score` (1–10) and `summary` (≤15 words) come from a single call
- Sets `role.relevance_score` (1–10) and `role.summary` on each `DiscoveredRole`
- Returns list sorted by `relevance_score` descending
- `max_tokens=1024` (raised from 512 to fit summaries for large batches)
- **Throttled**: same rate limiter as filters
- Supports checkpoint resume via `checkpoint.score_batches_done`

## Checkpoint / Resume (`checkpoint.py`)

Saves pipeline state after rate-limit errors so `--continue` can resume:
- **Created**: automatically after ATS fetch completes, before filter/score phases
- **Deleted**: after successful completion of filter + score
- **Key fields**: `phase` (filter/score), `raw_roles[]`, `flagged_companies[]`, `filter_config`, `filter_batches_done`, `filter_kept_roles[]`, `score_criteria`, `score_batches_done`, `partially_scored_roles[]`
- CLI `--continue` flag or API checkpoint route triggers resume from saved state

## Cache (`cache.py`)

Per-company, per-ATS role cache with 2-day TTL:
- **Key format**: `{company_name.lower()}|{ats_type}`
- `RolesCache.get(company, ats_type)` → `list[DiscoveredRole] | None`
- `RolesCache.put(company, ats_type, roles)` → saves with timestamp
- `RolesCache.age_hours(company, ats_type)` → hours since cached
- Stored as `RolesCacheEntry[]` in `data/roles_cache.json`

## Metrics (`metrics.py`)

`RunMetricsCollector` — mutable tracker populated during discovery:
- `companies_total / succeeded / failed`
- `ats_visits{}` — count per ATS type
- `jobs_per_ats{}`, `jobs_per_company{}` — role counts
- `playwright_uses`, `browser_agent_uses`
- `total_roles_fetched / after_filter / after_score`
- `filter_batches`, `score_batches`
- `errors[]`, `elapsed_seconds`
- `to_schema() → dict` — freezes to `JobRunMetrics` for persistence

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
