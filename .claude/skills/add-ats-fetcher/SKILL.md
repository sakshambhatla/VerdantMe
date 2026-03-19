---
name: add-ats-fetcher
description: >
  Guided workflow for adding support for a new ATS (Applicant Tracking System) to
  JobFinder's role discovery pipeline. Use this skill whenever the user says "add ATS",
  "new ATS fetcher", "support workday", "add ATS support for", or any similar phrase
  about adding a new job board / ATS integration.
---

# Add ATS Fetcher

Add support for a new Applicant Tracking System to the role discovery pipeline.

## Steps

### 1. Research the ATS API

Before writing code, determine:
- Does this ATS have a **public** job board API? (Greenhouse, Lever, Ashby all do)
- What is the API URL pattern? (e.g., `https://api.example.com/jobs/{board_token}`)
- What fields does the response contain? Map to `DiscoveredRole` fields:
  - title, location, url, department, team, commitment, workplace_type, employment_type
  - is_remote, posted_at, updated_at, published_at
- Is there a board token or slug pattern?

If no public API exists, the ATS should remain in `unsupported.py` — the browser agent handles these.

### 2. Update schema

Edit `jobfinder/storage/schemas.py` — add the new ATS type to the `ats_type` field:
```python
ats_type: str  # "greenhouse" | "lever" | "ashby" | "<new_type>" | "workday" | "linkedin" | "unknown"
```

### 3. Create fetcher

Create `jobfinder/roles/ats/<name>.py`:

```python
from __future__ import annotations
from jobfinder.roles.ats.base import BaseFetcher, ATSFetchError
from jobfinder.storage.schemas import DiscoveredRole
from jobfinder.utils.http import get_json

class <Name>Fetcher(BaseFetcher):
    def fetch(self, company, timeout: int = 30) -> list[DiscoveredRole]:
        url = f"https://api.example.com/boards/{company.ats_board_token}/jobs"
        try:
            data = get_json(url, timeout=timeout)
        except Exception as exc:
            raise ATSFetchError(str(exc)) from exc

        return [
            DiscoveredRole(
                company_name=company.name,
                title=job["title"],
                location=job.get("location", ""),
                url=job["url"],
                ats_type="<name>",
                ats_job_id=str(job["id"]),
                # ... map remaining fields
            )
            for job in data.get("jobs", [])
        ]
```

### 4. Register in ATS_REGISTRY

Edit `jobfinder/roles/ats/__init__.py`:
```python
from jobfinder.roles.ats.<name> import <Name>Fetcher
_REGISTRY["<name>"] = <Name>Fetcher()
```

Remove the type from `unsupported.py` if it was listed there.

### 5. Update LLM prompts

Edit `jobfinder/companies/prompts.py` — add the new ATS type to the list so the LLM can detect and emit it during company discovery.

### 6. Add tests

Create `tests/test_ats_<name>.py` following the pattern in `tests/test_ats_fetchers.py`:
- Use `respx` to mock the API endpoint
- Test successful fetch with sample response
- Test error handling (404, timeout, malformed JSON)

### 7. Verify

Run CLI tests to ensure the new fetcher works and existing tests still pass.
