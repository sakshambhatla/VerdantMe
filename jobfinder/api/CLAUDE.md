# jobfinder/api — Claude Context

FastAPI layer that wraps the existing Python core functions and serves the React UI.

## File Map
```
main.py       # App factory: CORS, router mounting, lifespan, StaticFiles for ui/dist
auth.py       # get_current_user() dependency — JWT decode → (user_id, raw_jwt) | None
models.py     # Request-only Pydantic models (responses use storage/schemas.py directly)
routes/
  resume.py       # POST /api/resume/upload · GET /api/resume · DELETE /api/resume/{filename}
  companies.py    # POST /api/companies/discover · GET /api/companies · GET /api/companies/registry
  roles.py        # POST /api/roles/discover · GET /api/roles · GET /api/roles/unfiltered
                  # GET /api/roles/checkpoint · GET /api/roles/fetch-browser/stream (SSE)
                  # DELETE /api/roles/fetch-browser/{name} · POST /api/roles/fetch-browser
  company_runs.py # GET /api/company-runs · GET /api/company-runs/{id}
  job_runs.py     # GET /api/job-runs · GET /api/job-runs/{id}
  settings.py     # GET /api/settings/api-keys · POST /api/settings/api-keys
                  # POST /api/settings/api-keys/{provider}/validate
                  # DELETE /api/settings/api-keys/{provider}
  logs.py         # GET /api/logs/stream (SSE — dev/local mode only; 403 in managed mode)
```

## Endpoints

| Method | Path | What it does |
|--------|------|--------------|
| POST | `/api/resume/upload` | Saves `.txt` file, calls `parse_resumes()`, writes `resumes.json` |
| GET | `/api/resume` | Reads `resumes.json`, 404 if absent |
| DELETE | `/api/resume/{filename}` | Removes resume entry + deletes `.txt` file |
| POST | `/api/companies/discover` | LLM company discovery; writes `companies.json` + `company_runs.json`; upserts registry. Accepts `focus` ("regular"\|"startups") — stored on run, auto-enables YC Jobs in role discovery |
| POST | `/api/companies/discover/stream` | SSE-streaming version of company discovery; emits `progress`, `done`, `error`; auto-keepalive via sse_starlette pings (15 s) — used by the UI to avoid proxy timeouts |
| GET | `/api/companies` | Reads `companies.json`, 404 if absent |
| GET | `/api/companies/registry` | Returns perpetual per-user company registry |
| POST | `/api/roles/discover` | ATS fetch + filter + score; writes `roles.json` + `job_runs.json` |
| POST | `/api/roles/discover/stream` | SSE-streaming version of role discovery; emits `progress`, `done`, `error`; auto-keepalive via sse_starlette pings (15 s) — used by the UI to avoid proxy timeouts |
| GET | `/api/roles` | Reads `roles.json`, 404 if absent |
| GET | `/api/roles/unfiltered` | Reads `roles_unfiltered.json` |
| GET | `/api/roles/checkpoint` | Returns checkpoint summary for resume-able runs |
| GET | `/api/roles/fetch-browser/stream` | SSE — browser agent for flagged company; emits `jobs_batch`, `filter_result`, `score_result`, `done`, `killed`, `error` |
| DELETE | `/api/roles/fetch-browser/{company_name}` | Kill a running browser agent; returns `{killed, partial_jobs}` |
| POST | `/api/roles/fetch-browser` | Non-streaming browser fetch (CLI path) |
| GET | `/api/company-runs` | Paginated list of company discovery runs (summary, no companies list) |
| GET | `/api/company-runs/{id}` | Single company run with full companies list |
| GET | `/api/job-runs` | Paginated list of role-discovery runs (summary, no log entries) |
| GET | `/api/job-runs/{id}` | Single job run with metrics + buffered log entries |
| GET | `/api/settings/api-keys` | Returns `{anthropic: bool, gemini: bool}` — never key values |
| POST | `/api/settings/api-keys` | Store (or replace) LLM API key; validates against provider before storing |
| POST | `/api/settings/api-keys/{provider}/validate` | Re-validate a stored key |
| DELETE | `/api/settings/api-keys/{provider}` | Delete a stored key |
| GET | `/api/logs/stream` | SSE log stream (dev/local only; 403 in managed/Supabase mode) |

## Key Patterns

### Auth + JWT threading (critical — follow this in every new endpoint)

`get_current_user()` in `auth.py` returns `tuple[str, str] | None`:
- **Managed mode** (SUPABASE_URL set): returns `(user_id, raw_jwt)` after validating the JWT
- **Dev mode** (no SUPABASE_URL): returns `None` — no auth required

Supports both `Authorization: Bearer <token>` header and `?token=<jwt>` query param (for SSE — EventSource doesn't support custom headers).

Every route handler that needs the user or storage must unpack the tuple:
```python
async def my_endpoint(
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    user_id, jwt_token = _auth if _auth else (None, None)
    store = get_storage_backend(user_id, jwt_token)
    ...
```

**Why `_auth` not `user_id`**: The raw JWT must be threaded to `get_storage_backend` so the Supabase client uses the anon key + per-user JWT (enforcing RLS). Handlers that only need user_id (e.g., vault calls in settings.py) can use `user_id = _auth[0] if _auth else None`.

**Do NOT pass the service role key to storage** — `vault.py` is the only code that uses `SUPABASE_SECRET_KEY` (required for SECURITY DEFINER vault functions). All data queries use `SUPABASE_PUBLISHABLE_KEY` + JWT.

### CORS

Configured in `main.py`. Defaults to `http://localhost:5173,http://127.0.0.1:5173`. Override with `CORS_ORIGINS` env var (comma-separated).

### Blocking calls → thread pool

All LLM and HTTP-heavy functions are sync; wrap with `asyncio.to_thread()`:
```python
companies = await asyncio.to_thread(discover_companies, resumes, config)
```

### Config overrides

Build an `overrides` dict from request fields, pass as kwargs to `load_config(**overrides)`. Only include keys where the request value is not `None`:
```python
overrides: dict = {}
if req.max_companies is not None:
    overrides["max_companies"] = req.max_companies
config = load_config(**overrides)
```

### API key resolution (managed mode)

Routes that call LLMs use `resolve_api_key(provider, user_id)` — checks user's Vault first, falls back to server env vars:
```python
try:
    api_key = resolve_api_key(config.model_provider, user_id)
except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
```
Then pass `api_key=api_key` to `discover_companies()`, `discover_roles()`, etc.

### Merge logic

Dedup companies by `name.lower()`, roles by `url`. New results take precedence. Sort roles by `relevance_score` descending.

### SSE streaming (browser agent)

`GET /roles/fetch-browser/stream` uses `EventSourceResponse` from `sse_starlette`. The async generator drains `session.event_queue`, applies filter + scoring, then yields the terminal event — guaranteeing the client refetches scored data.

**SSE event ordering**: `score_result` is always emitted *before* `done`/`killed`, so `onDone()` (which invalidates the roles query) fires after scoring is complete — the UI refetch retrieves roles with `relevance_score` already set.

### `app.state.running_agents`

Keyed by `(user_id, company_name)` tuple — scoped per user to prevent cross-user collision. Holds live `AgentSession` objects. Populated at stream start, removed in the `finally` block. The DELETE endpoint looks up sessions here to set `kill_event` and cancel the task:
```python
session = running.get((user_id, company_name))
```

### Production static files

`main.py` mounts `ui/dist/` at `/` only if the directory exists — server works in development without a built UI.

## Adding a New Endpoint

1. Add request model to `models.py` (if needed)
2. Create handler in `routes/<name>.py` following the auth pattern above
3. Import and include the router in `main.py`
4. Mirror the same logic in `cli.py` if it should also be a CLI command
5. Add the API call + TypeScript type to `ui/src/lib/api.ts`
