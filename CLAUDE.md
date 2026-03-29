# JobFinder — Claude Context

## Stack
- **Backend**: Python 3.12 · FastAPI · uvicorn · Click · Pydantic v2 · httpx · Rich · Anthropic SDK · google-genai
- **Frontend**: React 18 · TypeScript · Vite · Tailwind CSS v4 · shadcn/ui · TanStack Query · TanStack Table · axios
- **Storage**: JSON files (local mode) · Supabase Postgres + RLS (managed mode)
- Install: `source .venv/bin/activate && pip install -e .`
- Entry points: `jobfinder/cli.py` (CLI) · `jobfinder/api/main.py` (FastAPI)

## Commands
| Command | Output | Key flags |
|---------|--------|-----------|
| `jobfinder resume` | `data/resumes.json` | `--resume-dir` |
| `jobfinder discover-companies` | `data/companies.json` | `--max-companies`, `--refresh`, `--seed` (repeatable) |
| `jobfinder discover-roles` | `data/roles.json` | `--company`, `--refresh`, `--continue`, `--use-cache`, `--skip-career-page`, `--enable-yc-jobs` |
| `jobfinder browser-fetch` | roles via browser agent | `--company` |
| `jobfinder serve` | HTTP server | `--host`, `--port`, `--reload` |

## Top-Level Map
```
jobfinder/
  cli.py          # 5 Click subcommands; thin wrappers around core functions
  config.py       # AppConfig + RoleFilters (Pydantic); load_config(), require_api_key(), resolve_api_key()
  api/            # → see jobfinder/api/CLAUDE.md
  resume/
    parser.py     # parse_resumes(dir) — regex extraction from .txt files
  companies/
    discovery.py  # discover_companies(resumes, config, seed_companies, api_key) — LLM → DiscoveredCompany[]
    prompts.py    # System + user prompts for company discovery (resume-based + seed-based)
  roles/          # → see jobfinder/roles/CLAUDE.md (includes roles/sources/ for external job boards)
  storage/        # → see jobfinder/storage/CLAUDE.md
  utils/
    http.py         # head_ok(url), get_json(url, timeout) with retry
    display.py      # Rich console helpers
    throttle.py     # Shared RateLimiter; get_limiter(rpm) — process-level singleton
    log_stream.py   # Centralized logging: Rich console + file + SSE ring buffer (2000 entries)
    gemini_errors.py# Parse Gemini 429 responses (daily vs per-minute limits)
scripts/
  apply_vault_migration.py  # Apply vault SQL migration via psql; falls back to printing SQL + dashboard link
  bump_version.py           # Bump version (major/minor/patch) across pyproject.toml + source files
ui/               # → see ui/CLAUDE.md
tests/            # → see tests/CLAUDE.md
data/             # → see data/CLAUDE.md
docs/
  docs.md         # Human-written learnings & pitfalls — read before major changes
supabase/
  migrations/     # → see supabase/migrations/CLAUDE.md
```

## Config (`config.json`)
All fields optional. CLI flags override file values.
```
model_provider        "anthropic" | "gemini"
anthropic_model       string                  default "claude-sonnet-4-6"
gemini_model          string                  default "gemini-2.5-flash-lite"
max_companies         int                     default 15
refresh               bool                    default false
request_timeout       int                     seconds; default 30
resume_dir            path
data_dir              path
debug                 bool                    default false
skip_career_page      bool                    default false; skip Playwright/browser-agent fallback
enable_yc_jobs        bool                    default false; fetch YC Jobs via RapidAPI (requires RAPIDAPI_KEY)
                                              Also auto-enabled when company run has focus="startups"

role_filters.title          string | null     semantic job title filter
role_filters.posted_after   string | null     natural language date
role_filters.location       string | null     natural language location(s)
role_filters.confidence     "high"|"medium"|"low"   default "high"
role_filters.filter_strategy "llm"|"fuzzy"|"semantic"  default "llm"

relevance_score_criteria  string | null       LLM scores roles 1–10, sorted highest-first
write_preference      "overwrite"|"merge"     merge deduplicates + re-sorts; default "overwrite"
rpm_limit             int                     client-side throttle; 0 = off; default 4

# Browser agent (config.json only — not exposed in UI)
browser_agent_max_time_minutes     int  default 15  hard wall; agent cancelled after N minutes
browser_agent_max_steps            int  default 100 step budget for browser-use Agent.run
browser_agent_rate_limit_max_retries   int  default 5  give up after N consecutive 429s
browser_agent_rate_limit_initial_wait  int  default 5  initial back-off seconds; doubles each hit
```

## Environment Variables
API keys from env: `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `RAPIDAPI_KEY` (server-level, for YC Jobs).
Supabase (managed mode): `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, `SUPABASE_JWT_SECRET`.
Server: `CORS_ORIGINS` (comma-separated; defaults to `http://localhost:5173,http://127.0.0.1:5173`).

## Cross-Cutting Patterns
- **Schemas first**: change `storage/schemas.py` before touching discovery/API/UI code
- **Multi-provider**: add `_call_<provider>()` + branch in each `discovery.py`, plus key check in `config.py:require_api_key()`
- **Graceful degradation**: ATS failures → `flagged` list, not crashes
- **API mirrors CLI**: routes call the same core functions; blocking calls wrapped in `asyncio.to_thread()`
- **Dual storage backend**: `get_storage_backend(user_id, jwt_token)` returns JSON (local) or Supabase (managed). All data access goes through `StorageBackend` protocol
- **Auth + JWT threading**: every API route unpacks `_auth = Depends(get_current_user)` → `(user_id, jwt_token)` or `(None, None)`. JWT threaded to storage backend for RLS enforcement. See `api/CLAUDE.md` for the exact pattern
- **Company registry**: perpetual per-user registry with `searchable` flag; upserted on company discovery, updated after role fetch
- **Checkpoint/resume**: rate-limit errors during filter/score save a checkpoint; `--continue` resumes from it
- **SSE streaming**: browser agent streams partial results via `EventSourceResponse`; events: `jobs_batch`, `filter_result`, `score_result`, `done`, `killed`, `error`
- **External job sources**: `roles/sources/` package for aggregator APIs (YC Jobs via RapidAPI). Runs as Pass 0 before ATS fetch when enabled. Extensible registry pattern for future RapidAPI integrations

## MCP Servers

The following MCP servers are configured in `.mcp.json` and available in every conversation:

| Server | What it connects to | Use for |
|--------|-------------------|---------|
| `supabase` | Supabase Postgres (account-level PAT) | Query tables, inspect schema, run migrations, debug RLS |
| `render` | Render API | Check service status, view deploy logs, inspect env vars |
| `vercel` | Vercel API | Check deployments, view build/runtime logs, inspect project config |

**Default behaviour when the user reports a production error**: reach for these MCP tools first before asking for logs or screenshots. The app runs on the hosted stack (Vercel frontend → Render backend → Supabase DB), so errors are almost always diagnosable via these servers directly.

## Learnings & Pitfalls
Read `docs/docs.md` before starting major changes — it contains hard-won operational knowledge and gotchas written by the project maintainer.

## Testing Convention

After any major code change (new feature, significant refactor):
1. **Run CLI tests** — use the `run-cli-tests` skill (triggers on: "run CLI tests", "run pytest", "run backend tests")
2. **Run UI tests** — use the `run-ui-tests` skill (triggers on: "run UI tests", "run frontend tests", "run vitest")

Both must pass before committing. Quick reference:
```bash
# CLI tests (64 tests covering resume parser, ATS fetchers, storage, config, API routes)
source .venv/bin/activate && pytest tests/ -v --tb=short

# UI tests (12 tests covering ResumeTab rendering and API helpers)
/Users/sakshambhatla/.nvm/versions/node/v20.20.1/bin/pnpm --dir ui test
```

Test files: `tests/` (backend) · `ui/src/tests/` (frontend)
Install test deps: `pip install -e ".[dev]"` · `pnpm --dir ui install`

3. **Run security review** — use the `security-review` skill (triggers on: "run security review", "check for security issues", "security audit")
   - Reviews changed files for secrets, PII, scraping legality, API vulnerabilities, and input validation
   - Appends findings to `security-concerns.md` (gitignored — local only)
   - Run before any commit that touches API routes, scraping logic, or config handling

## Version Bumping
When entering plan mode for any code change, **always ask the user first**:
> "Is this a major feature (breaking changes or significant new functionality)
> or a minor feature/patch (backwards-compatible changes or fixes)?"
Based on the answer:
- Major feature → bump major version (X.0.0) or minor (0.X.0) per semver
- Minor feature → bump patch (0.0.X)
- Include version bump as a step in the plan
