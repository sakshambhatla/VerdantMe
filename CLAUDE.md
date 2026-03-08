# JobFinder — Claude Context

## Stack
- Python 3.12 · FastAPI · uvicorn · Click · Pydantic v2 · httpx · Rich · Anthropic SDK · google-genai
- React 18 · TypeScript · Vite · Tailwind CSS v4 · shadcn/ui · TanStack Query · TanStack Table · axios
- Installed as editable package in `.venv`: `source .venv/bin/activate && pip install -e .`
- Entry points: `jobfinder/cli.py` → `cli` Click group; `jobfinder/api/main.py` → FastAPI app

## Commands
| Command | Output file | Key flag |
|---------|-------------|----------|
| `jobfinder resume` | `data/resumes.json` | `--resume-dir` |
| `jobfinder discover-companies` | `data/companies.json` | `--max-companies`, `--refresh` |
| `jobfinder discover-roles` | `data/roles.json` | `--company`, `--refresh` |
| `jobfinder serve` | (starts server) | `--host`, `--port`, `--reload` |

## File Map
```
jobfinder/
  cli.py            # Click group — 4 subcommands (resume, discover-companies, discover-roles, serve)
  config.py         # AppConfig (Pydantic), load_config(), require_api_key(provider)
  api/
    main.py         # FastAPI app — CORS, mounts routes, serves ui/dist in production
    models.py       # API-specific request models (DiscoverCompaniesRequest, DiscoverRolesRequest)
    routes/
      resume.py     # POST /api/resume/upload, GET /api/resume
      companies.py  # POST /api/companies/discover, GET /api/companies
      roles.py      # POST /api/roles/discover, GET /api/roles
  resume/
    parser.py       # Regex section/skill/title extraction from .txt files
  companies/
    prompts.py      # SYSTEM_PROMPT + build_user_prompt()
    discovery.py    # discover_companies() → _call_anthropic() / _call_gemini() → _parse_response()
  roles/
    discovery.py    # discover_roles() — iterates companies, accumulates roles + flagged
    filters.py      # filter_roles() — LLM-based title/date/location filter, batched 100/call
    scorer.py       # score_roles() — LLM assigns 1-10 score + summary, batched 60/call, returns sorted
    ats/
      __init__.py   # ATS_REGISTRY dict: ats_type str → fetcher instance
      base.py       # BaseFetcher ABC, ATSFetchError, UnsupportedATSError
      greenhouse.py # boards-api.greenhouse.io/v1/boards/{token}/jobs
      lever.py      # api.lever.co/v0/postings/{company}?mode=json
      ashby.py      # api.ashbyhq.com/posting-api/job-board/{token}
      unsupported.py# raises UnsupportedATSError (Workday/LinkedIn/unknown)
  storage/
    schemas.py      # ParsedResume, DiscoveredCompany, DiscoveredRole (has relevance_score), FlaggedCompany
    store.py        # StorageManager: atomic JSON read/write (temp file + rename)
  utils/
    http.py         # get_json(url, timeout) with manual retry
    display.py      # Rich console helpers: display_companies/roles/flagged/error/success
    throttle.py     # Shared sliding-window RateLimiter; get_limiter(rpm) returns process-level instance
ui/
  src/
    App.tsx         # Three-tab layout (shadcn/ui Tabs)
    main.tsx        # React root + QueryClientProvider
    lib/
      api.ts        # axios API client + TypeScript types for all endpoints
      queryClient.ts# TanStack Query client config
    components/
      ResumeTab.tsx      # Drag-and-drop upload, parsed resume card
      CompaniesTab.tsx   # Config form, company table
      RolesTab.tsx       # Filter form, sortable TanStack Table, flagged callout
      ui/                # shadcn/ui components (button, card, tabs, badge, input, label)
  vite.config.ts    # /api proxy → :8000; @ alias → src/
```

## Config (`config.json`)
All fields optional. CLI flags override file values.
```
model_provider        "anthropic" | "gemini"            — which LLM to call
anthropic_model       string                            — Claude model name
gemini_model          string                            — Gemini model name
max_companies         int                               — LLM suggestion count
refresh               bool                              — skip cache check if true
request_timeout       int                               — httpx timeout (seconds)
resume_dir            path                              — .txt resume source dir
data_dir              path                              — JSON output dir
role_filters.title    string | null                     — semantic job title filter
role_filters.posted_after  string | null               — date filter (natural language)
role_filters.location string | null                    — location filter (natural language)
role_filters.confidence  "high" | "medium" | "low"    — LLM match threshold (default "high")
relevance_score_criteria  string | null                — keywords/description; LLM scores roles 1-10, sorted highest-first
write_preference      "overwrite" | "merge"            — overwrite replaces file; merge deduplicates + re-sorts (default "overwrite")
rpm_limit             int                              — max LLM RPM (client-side); 0 = disabled; default 4 (Gemini free tier)
```
API keys come from env only: `ANTHROPIC_API_KEY` or `GEMINI_API_KEY`.

## Key Patterns
- **Multi-provider dispatch**: `discovery.py` branches on `config.model_provider`; adding a new provider means adding `_call_<provider>()` and a branch there, plus a new key check in `config.py:require_api_key()`
- **ATS registry**: to add a new ATS, create `roles/ats/<name>.py` subclassing `BaseFetcher`, add it to `ATS_REGISTRY` in `roles/ats/__init__.py`
- **Schemas**: all JSON shapes are Pydantic models in `storage/schemas.py`; update there first when changing data structures
- **Refresh logic**: `effective_refresh = refresh or config.refresh` — either CLI flag or config triggers re-run
- **Graceful degradation**: one company's ATS failure → added to `flagged` list, not a crash; displayed at end
- **API wraps CLI**: all `api/routes/*.py` call the same core functions as `cli.py`; blocking calls run via `asyncio.to_thread()` to keep FastAPI event loop free
- **UI dev**: Vite (`pnpm dev`) proxies `/api` → FastAPI on :8000; production build (`pnpm build`) goes to `ui/dist/` which FastAPI serves as static files
- **Adding an API route**: create handler in `api/routes/<name>.py`, add request model to `api/models.py`, mount router in `api/main.py`
- **Adding a UI tab**: create component in `ui/src/components/<Name>Tab.tsx`, add tab trigger/content in `App.tsx`, add API calls to `lib/api.ts`
