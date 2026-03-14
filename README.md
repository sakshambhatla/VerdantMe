# VerdantME

Reads your resumes, uses an LLM to discover relevant companies,
and reads open job roles from those companies' career pages via public ATS APIs.

Available as a web UI and CLI.

---

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/sakshambhatla/VerdantMe.git
cd VerdantMe

# 2. Run setup (creates venv, installs deps, scaffolds config)
bash setup/setup.sh          # macOS / Linux
# .\setup\setup.ps1          # Windows PowerShell

# 3. Add your API key to .env
#    Anthropic: https://console.anthropic.com
#    Gemini (free): https://aistudio.google.com

# 4. Start
source .venv/bin/activate
jobfinder serve
# → open http://localhost:8000
```

> Troubleshooting, Windows instructions, UI dev setup, browser agent: **[setup/README.md](setup/README.md)**

---

## Web UI

The easiest way to use VerdantME is through the browser UI at `http://localhost:8000`.

Three tabs let you upload a resume, discover companies, and discover/filter roles — all without touching the terminal again.

![Workflow Overview](setup/verdantMe-workflow-overview.gif)

---

## CLI Usage

```bash
# 1. Parse resumes → data/resumes.json
jobfinder resume

# 2. Discover companies → data/companies.json
jobfinder discover-companies

# 3. Fetch open roles → data/roles.json
jobfinder discover-roles
```

Key flags:

```
jobfinder resume              --resume-dir PATH
jobfinder discover-companies  --max-companies N  --refresh
jobfinder discover-roles      --company TEXT     --refresh
jobfinder --config PATH
```

---

## Configuration

Edit `config.json` (created by the setup script). All fields are optional.

| Key | Default | Description |
|-----|---------|-------------|
| `model_provider` | `anthropic` | `"anthropic"` or `"gemini"` |
| `anthropic_model` | `claude-sonnet-4-6` | Claude model ID |
| `gemini_model` | `gemini-2.5-flash` | Gemini model ID |
| `max_companies` | `15` | Companies the LLM should suggest |
| `refresh` | `false` | Re-run even if output files exist |
| `request_timeout` | `30` | HTTP timeout (seconds) |
| `role_filters.title` | `null` | Semantic job title filter |
| `role_filters.posted_after` | `null` | Natural language date (e.g. `"Jan 1, 2026"`) |
| `role_filters.location` | `null` | Location(s) (e.g. `"SF, Seattle or Remote"`) |
| `role_filters.confidence` | `"high"` | Match threshold: `"high"`, `"medium"`, `"low"` |
| `relevance_score_criteria` | `null` | Keywords for scoring roles 1–10; sorted highest-first |
| `write_preference` | `"overwrite"` | `"overwrite"` or `"merge"` (deduplicates + re-sorts) |
| `rpm_limit` | `4` | Client-side LLM throttle (requests/min). `0` = off |

CLI flags override config values (e.g. `--max-companies 25`).

---

## Resume Files

Place plain text (`.txt`) resume files in `resumes/`. Multiple files are supported — all are combined when asking the LLM for suggestions.

---

## Output Files

| File | Contents |
|------|----------|
| `data/resumes.json` | Parsed resume data |
| `data/companies.json` | LLM-suggested companies (last run) |
| `data/company_registry.json` | Perpetual registry of all discovered companies |
| `data/roles.json` | Fetched roles + companies flagged for manual check |
| `data/api_profiles.json` | Discovered career-page API endpoints (browser agent cache) |

---

## ATS Support

| ATS | Status |
|-----|--------|
| Greenhouse | Fully supported |
| Lever | Fully supported |
| Ashby | Fully supported |
| Career Page (LLM) | LLM parses static HTML; merged with ATS results |
| Workday | Flagged for manual check |
| LinkedIn | Flagged for manual check |

Companies using unsupported ATS types are surfaced with their career page URL. A **browser-use agent** is available for interactive pages — see [setup/README.md](setup/README.md).

> **⚠️ Browser Agent requires API credits — subscriptions are not sufficient**
>
> The browser-use agent calls your configured LLM provider's API directly and is billed by token usage:
>
> - **Anthropic** — requires a separate API key with a paid credit balance ([console.anthropic.com](https://console.anthropic.com)). A Claude Pro or Max subscription alone does **not** cover API usage.
> - **Gemini** — has a free tier, but heavy browser-agent usage may exceed it. Beyond the free tier, billing is pay-per-token via a Google Cloud billing account ([aistudio.google.com](https://aistudio.google.com)). A Gemini Advanced subscription does **not** cover API usage.
>
> Standard company discovery and role fetching are unaffected and work within the free tier for most usage.
