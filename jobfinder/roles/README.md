# jobfinder/roles — Architecture & Orchestration

This document explains the full `discover-roles` pipeline: what happens at each stage,
when the LLM is invoked, and how the cache and checkpoint layers interact.

---

## Overview

`discover-roles` runs a two-pass role fetch followed by optional LLM filtering and
scoring.  Pass 1 queries structured ATS APIs (Greenhouse, Lever, Ashby).  Pass 2
fetches raw career-page HTML and lets the LLM extract job listings.  Both passes write
to a per-company cache so subsequent runs can skip network calls.  After fetching,
roles are filtered (LLM, batch 100) and scored (LLM, batch 60) against user-supplied
criteria, then merged into `roles.json`.

---

## Orchestration Diagram

```
CLI (discover-roles) / API (POST /api/roles/discover)
          │
          ▼
  Company resolution
  ┌─ --company flags → registry lookup (company_registry.json)
  └─ default        → companies.json (last Discover Companies run)
          │
          ▼
  ┌─────────────────────────────────────────────────────────┐
  │  Pass 1 — ATS API fetch (per company)                  │
  │                                                         │
  │  use_cache=True?                                        │
  │    cache hit (≤2 days) → use cached roles, skip fetch  │
  │    cache miss / expired → ATS API call (no LLM)        │
  │                                                         │
  │  always after fresh fetch: cache.put(roles)            │
  │                                                         │
  │  UnsupportedATSError → flagged list                    │
  │  ATSFetchError / other → flagged list, continue        │
  └─────────────────────────────────────────────────────────┘
          │
          ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  Pass 2 — Career page fetch (per company with career_page_url)│
  │                                                              │
  │  use_cache=True?                                            │
  │    cache hit (≤2 days) → use cached roles, skip fetch      │
  │    cache miss / expired → httpx GET career_page_url        │
  │                        → LLM: extract job JSON from HTML   │  ← LLM
  │                                                              │
  │  always after fresh fetch: cache.put(cp_roles)             │
  │  always: registry.searchable updated                        │
  │  dedup with Pass 1 results by URL                           │
  └──────────────────────────────────────────────────────────────┘
          │  (checkpoint saved here — raw roles are safe)
          ▼
  ┌────────────────────────────────────────────────────────┐
  │  Filter  (optional — skip if no role_filters set)      │
  │  LLM batch size: 100 roles / call                      │  ← LLM
  │  Input:  title | location | date (per role)            │
  │  Output: JSON array of matching 0-based indices        │
  │  Confidence levels: high / medium / low                │
  └────────────────────────────────────────────────────────┘
          │
          ▼
  ┌────────────────────────────────────────────────────────┐
  │  Score   (optional — skip if no score criteria set)    │
  │  LLM batch size: 60 roles / call                       │  ← LLM
  │  Input:  title | company | location | dept (per role)  │
  │  Output: JSON object {index: {score, summary}}         │
  │  Sets relevance_score (1–10) + summary (≤15 words)     │
  │  Sorts roles highest-score-first                       │
  └────────────────────────────────────────────────────────┘
          │
          ▼
  Merge with existing roles.json (if write_preference="merge")
  Dedup by URL, new results take precedence, re-sort by score
          │
          ▼
  roles.json  +  checkpoint deleted
```

---

## Stage-by-Stage Reference

| Stage | File | LLM? | Input | Output |
|-------|------|------|-------|--------|
| Company resolution | `cli.py` / `routes/roles.py` | No | `--company` flags or `companies.json` | `list[DiscoveredCompany]` |
| Pass 1 — ATS fetch | `discovery.py` + `ats/*.py` | No | `DiscoveredCompany.ats_board_token` | `list[DiscoveredRole]` |
| Pass 2 — Career page | `discovery.py` + `ats/career_page.py` | Yes | `career_page_url` HTML (≤80 K chars) | `list[DiscoveredRole]` appended to Pass 1 |
| Filter | `filters.py` | Yes | Batches of `title \| location \| date` strings | Filtered `list[DiscoveredRole]` |
| Score | `scorer.py` | Yes | Batches of `title \| company \| location \| dept` strings | Scored + sorted `list[DiscoveredRole]` |
| Write output | `cli.py` / `routes/roles.py` | No | `list[DiscoveredRole]` + flagged | `data/roles.json` |

---

## Cache Layer

**File**: `data/roles_cache.json`
**Schema**:
```json
{
  "version": 1,
  "entries": {
    "stripe|greenhouse": {
      "company_name": "Stripe",
      "ats_type": "greenhouse",
      "cached_at": "2026-03-09T10:00:00+00:00",
      "roles": [ ... ]
    },
    "stripe|career_page": { ... }
  }
}
```

**Cache key**: `company_name.lower() + "|" + ats_type`
**TTL**: 2 days (hardcoded in `cache.py:CACHE_TTL_DAYS`)
**Writes**: unconditional — every fresh fetch writes (or overwrites) its entry
**Reads**: conditional — only when `use_cache=True` is passed to `discover_roles()`
**Expiry**: expired entries stay in the file; `get()` returns `None` for them
**`--refresh` interaction**: `--refresh` sets `use_cache=False` regardless of the flag — fresh fetch always wins

The cache covers **only the raw fetch layer** (Pass 1 + Pass 2).  Filter and score
results are not cached because the criteria can change between runs.

---

## Checkpoint / Resume

After both fetch passes complete, a checkpoint is saved to
`data/roles_fetch_checkpoint.json`.  The checkpoint stores the raw role list plus
partial filter/score progress (batch index + kept roles so far).

If the filter or scorer hits a rate-limit error (`RateLimitError`), the process exits
with an error message.  Running `discover-roles --continue` (CLI) or sending
`resume=true` (API) restores the raw roles from the checkpoint and resumes from the
last completed batch — no ATS re-fetching needed.

The checkpoint is deleted once `roles.json` is successfully written.

---

## Adding a New ATS

1. Create `ats/<name>.py` subclassing `BaseFetcher` (see `ats/base.py`), implement
   `fetch(company, timeout) -> list[DiscoveredRole]`.
2. Register it in `ats/__init__.py` → `ATS_REGISTRY[<name>] = <FetcherClass>()`.
3. Add the new literal to `DiscoveredCompany.ats_type` in `storage/schemas.py`.
4. Update the LLM prompt in `companies/prompts.py` so it can emit the new type.
