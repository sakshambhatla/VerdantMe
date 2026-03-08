# JobFinder

A Python CLI that reads your resumes, uses an LLM to discover relevant companies,
and reads open job roles from those companies' career pages via public ATS APIs.

## Setup

**Requirements:** Python 3.10+ (project uses pyenv `3.12.3`)

```bash
# Activate the virtual environment
source .venv/bin/activate

# Install (first time or after pulling changes)
pip install -e .

# Create your personal config from the example (do not commit config.json)
cp config.example.json config.json
```

### API Keys

API keys must be set as environment variables — they are **never** stored in `config.json`.

**Anthropic (Claude):**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```
Get a key at: https://console.anthropic.com

**Google Gemini:**
```bash
export GEMINI_API_KEY=...
```
Get a free key at: https://aistudio.google.com

To avoid re-exporting every session, add to `~/.zshrc`:
```bash
echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.zshrc
# or
echo 'export GEMINI_API_KEY=...' >> ~/.zshrc
```

## Web UI

The easiest way to use JobFinder is through the browser UI:

```bash
# Start the server (Python + pre-built UI)
jobfinder serve

# Then open: http://localhost:8000
```

Three tabs let you upload a resume, discover companies, and discover/filter roles — all without touching the terminal again.

### UI Development

If you want to modify the frontend:

```bash
# Terminal 1 — Python API server
jobfinder serve --reload

# Terminal 2 — Vite dev server (hot reload)
cd ui
node --version  # needs Node 20+; run: nvm use 20
pnpm install    # first time only
pnpm dev        # opens http://localhost:5173 (proxies /api → :8000)
```

Build for production (output goes to `ui/dist/`, served automatically by `jobfinder serve`):

```bash
cd ui && pnpm build
```

## CLI Usage

Run the three commands in order:

```bash
# 1. Parse resumes from resumes/ → writes data/resumes.json
jobfinder resume

# 2. Ask the LLM to suggest companies → writes data/companies.json
jobfinder discover-companies

# 3. Fetch open roles from company career pages → writes data/roles.json
jobfinder discover-roles
```

### All flags

```bash
jobfinder resume
  --resume-dir PATH        Override resume directory (default: ./resumes)

jobfinder discover-companies
  --max-companies INTEGER  Max companies to suggest (default: 15)
  --refresh                Re-run even if companies.json already exists

jobfinder discover-roles
  --company TEXT           Fetch roles for one specific company only
  --refresh                Re-fetch even if roles.json already exists

jobfinder --config PATH    Use a custom config file (default: config.json)
```

### Examples

```bash
# Use a different resume directory
jobfinder resume --resume-dir ~/Documents/resumes

# Get more company suggestions
jobfinder discover-companies --max-companies 25

# Re-run company discovery after updating your resume
jobfinder discover-companies --refresh

# Check a single company
jobfinder discover-roles --company "Stripe"

# Full refresh of roles
jobfinder discover-roles --refresh
```

## Resume Files

Place plain text (`.txt`) resume files in the `resumes/` directory.
Multiple versions are supported — all will be read and combined when
asking the LLM for company suggestions.

## Configuration

Edit `config.json` to change defaults. All fields are optional.

```json
{
  "resume_dir": "./resumes",
  "data_dir": "./data",
  "model_provider": "gemini",
  "anthropic_model": "claude-sonnet-4-6",
  "gemini_model": "gemini-2.5-flash",
  "max_companies": 20,
  "refresh": false,
  "request_timeout": 30,
  "role_filters": {
    "title": "Engineering Manager",
    "posted_after": "Jan 1, 2026",
    "location": "SF, Seattle, NY or Remote",
    "confidence": "high"
  },
  "relevance_score_criteria": "big data, data pipelines, spark, flink, distributed systems",
  "write_preference": "overwrite"
}
```

Set any `role_filters` field to `null` (or omit it) to skip that filter. Omit `role_filters` entirely to show all roles unfiltered.

| Key | Default | Description |
|-----|---------|-------------|
| `resume_dir` | `./resumes` | Directory containing `.txt` resume files |
| `data_dir` | `./data` | Directory where JSON output is written |
| `model_provider` | `anthropic` | LLM provider: `"anthropic"` or `"gemini"` |
| `anthropic_model` | `claude-sonnet-4-6` | Claude model (used when provider is `"anthropic"`) |
| `gemini_model` | `gemini-2.5-flash` | Gemini model (used when provider is `"gemini"`) |
| `max_companies` | `15` | How many companies the LLM should suggest |
| `refresh` | `false` | Re-run discovery even if output files already exist |
| `request_timeout` | `30` | HTTP timeout in seconds for ATS API calls |
| `role_filters.title` | `null` | Job title to match (semantic, e.g. `"Engineering Manager"`) |
| `role_filters.posted_after` | `null` | Only show roles posted after this date (e.g. `"Jan 1, 2026"`) |
| `role_filters.location` | `null` | Location(s) to match (e.g. `"SF, Seattle, NY or Remote"`) |
| `role_filters.confidence` | `"high"` | Match threshold: `"high"`, `"medium"`, or `"low"` |
| `relevance_score_criteria` | `null` | Keywords/description for scoring roles 1–10 (e.g. `"spark, flink, data pipelines"`); roles sorted highest-first in output |
| `write_preference` | `"overwrite"` | `"overwrite"` replaces existing output; `"merge"` combines with existing data, deduplicates, and re-sorts |
| `rpm_limit` | `4` | Max LLM requests per minute (client-side throttle). Set to `0` to disable. Default is `4` — safe for Gemini free tier (5 RPM max). |

CLI flags override config file values (e.g. `--max-companies 25` overrides `max_companies`).

## Output Files

All output is written to `data/`:

| File | Contents |
|------|----------|
| `data/resumes.json` | Parsed resume data (skills, titles, sections) |
| `data/companies.json` | LLM's company suggestions with ATS metadata |
| `data/roles.json` | Fetched roles + companies flagged for manual check |

## ATS Support

Role discovery uses public APIs — no authentication required:

| ATS | Notes |
|-----|-------|
| Greenhouse | Fully supported |
| Lever | Fully supported |
| Ashby | Fully supported |
| Workday | Flagged for manual check |
| LinkedIn | Flagged for manual check |

Companies using unsupported ATS types are surfaced with their career page URL
so you can check them manually.

### Planned ATS support

**Workday** — Many large companies (e.g. Zillow, Salesforce, Nike) use Workday.
The public REST endpoint follows the pattern:
`https://<tenant>.myworkdayjobs.com/wday/cxs/<tenant>/<board>/jobs`
Each company has a unique tenant and board token (e.g. `Zillow_Group_External`) that
can be extracted from their career page URL. A `WorkdayFetcher` should:
1. Parse the tenant and board token from `career_page_url` in `DiscoveredCompany`
2. POST to the Workday jobs endpoint with standard pagination params
3. Map the response fields to `DiscoveredRole` (title, location, posted date, apply URL)

See `jobfinder/roles/ats/greenhouse.py` for a reference implementation to follow.
