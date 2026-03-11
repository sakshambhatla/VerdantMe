# data/ — Runtime Data Files

All files here are generated at runtime and are git-ignored.
Edit schemas in `jobfinder/storage/schemas.py` before changing data shapes here.

## Files

| File | Written by | Contents |
|------|------------|----------|
| `resumes.json` | `jobfinder resume` | Parsed resume fields (skills, titles, companies, education) |
| `companies.json` | `jobfinder discover-companies` | Last LLM discovery run — ATS metadata for each suggested company |
| `company_registry.json` | `discover-companies` (upsert) + `discover-roles` (`searchable` update) | Perpetual registry — grows each run, never shrinks |
| `company_registry_archive.json` | Manual archive | Previous registry snapshot before fresh reset |
| `roles.json` | `jobfinder discover-roles` | Fetched + filtered + scored roles, plus flagged companies |
| `roles_checkpoint.json` | `discover-roles` (auto) | Resume state saved after a `RateLimitError`; deleted on successful completion |
| `api_profiles.json` | Browser agent (auto) | Discovered career-page API endpoints, keyed by domain (netloc); injected into the agent's task prompt on the next run to skip re-discovery |

## `company_registry.json` schema

```json
{
  "updated_at": "2026-03-09T10:00:00+00:00",
  "companies": [
    {
      "name": "Scale AI",
      "ats_type": "greenhouse",
      "ats_board_token": "scaleai",
      "career_page_url": "https://scale.com/careers/open-roles",
      "searchable": true
    }
  ]
}
```

### Field notes

| Field | Set by | Meaning |
|-------|--------|---------|
| `career_page_url` | `discover-companies` | HTTP-validated during discovery; empty string if unreachable |
| `searchable` | `discover-roles` | `null` = never attempted; `true` = LLM found ≥1 job; `false` = page inaccessible or returned 0 jobs |

### Merge / upsert rules

- Registry entries are matched by `name.lower()` — a new `discover-companies` run wins all fields **except** `searchable` (the existing value is preserved so role-fetch history is not lost)
- `searchable` is only written by `discover-roles` after an actual career page fetch attempt
- `roles.json` deduplicates roles by `url` in merge mode; ATS-sourced roles take precedence over `career_page`-sourced roles
