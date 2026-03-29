"""TheirStack Job Search API client.

Fetches job postings for a company using TheirStack's ``/v1/jobs/search``
endpoint.  Returns results as ``DiscoveredRole`` objects ready for the
standard filter/score pipeline.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from jobfinder.config import AppConfig, RoleFilters
from jobfinder.roles.ats.base import ATSFetchError
from jobfinder.roles.theirstack.title_broadener import broaden_title
from jobfinder.storage.schemas import DiscoveredRole

THEIRSTACK_API_URL = "https://api.theirstack.com/v1/jobs/search"


class TheirStackError(ATSFetchError):
    """TheirStack API call failed."""


def _posted_after_to_days(posted_after: str | None) -> int | None:
    """Convert a natural-language date string to ``posted_at_max_age_days``.

    Returns None if the date cannot be parsed or is not set.
    """
    if not posted_after:
        return None
    try:
        from dateutil.parser import parse as _parse_date

        cutoff = _parse_date(posted_after, ignoretz=True)
        delta = datetime.now() - cutoff
        days = max(1, int(delta.days))
        # Cap at 90 days to avoid pulling ancient results
        return min(days, 90)
    except Exception:
        return None


def search_jobs(
    company_name: str,
    *,
    company_domain: str | None = None,
    filters: RoleFilters | None = None,
    config: AppConfig,
    api_key: str,
    max_results: int = 25,
) -> list[DiscoveredRole]:
    """Search TheirStack for job postings at a specific company.

    Args:
        company_name: Company name to search for.
        company_domain: Optional company website domain (e.g., "stripe.com").
        filters: Role filters — title is broadened, posted_after converted to days.
        config: App configuration.
        api_key: TheirStack API key (Bearer token).
        max_results: Maximum jobs to return (controls cost: 1 credit per job).

    Returns:
        List of DiscoveredRole objects with ``ats_type="theirstack"``
        and ``source_path="theirstack"``.

    Raises:
        TheirStackError: On API failure.
    """
    body: dict = {
        "company_name_or": [company_name],
        "limit": max_results,
        "page": 0,
    }

    if company_domain:
        body["company_domain_or"] = [company_domain]

    # Pre-filter by broadened title if available
    if filters and filters.title:
        broadened = broaden_title(filters.title)
        if broadened:
            body["job_title_or"] = [broadened]

    # Convert posted_after to max age in days
    if filters and filters.posted_after:
        days = _posted_after_to_days(filters.posted_after)
        if days:
            body["posted_at_max_age_days"] = days

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        with httpx.Client(timeout=config.request_timeout) as client:
            resp = client.post(THEIRSTACK_API_URL, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        detail = ""
        try:
            detail = exc.response.text[:200]
        except Exception:
            pass
        raise TheirStackError(
            f"TheirStack API returned {status} for {company_name}: {detail}"
        ) from exc
    except httpx.TransportError as exc:
        raise TheirStackError(
            f"TheirStack API unreachable for {company_name}: {exc}"
        ) from exc

    return _parse_response(data, company_name)


def _parse_response(data: dict, company_name: str) -> list[DiscoveredRole]:
    """Map TheirStack JSON response to DiscoveredRole list."""
    jobs = data.get("data", [])
    if not isinstance(jobs, list):
        return []

    roles: list[DiscoveredRole] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for job in jobs:
        if not isinstance(job, dict):
            continue

        title = job.get("job_title") or job.get("normalized_title") or ""
        if not title:
            continue

        location = job.get("short_location") or job.get("long_location") or "Unknown"

        url = job.get("url") or job.get("final_url") or ""
        posted_at = job.get("date_posted") or ""
        job_id = str(job.get("id", "")) if job.get("id") else None

        # Derive remote/hybrid
        is_remote = job.get("remote")
        workplace_type = None
        if is_remote:
            workplace_type = "remote"
        elif job.get("hybrid"):
            workplace_type = "hybrid"

        roles.append(
            DiscoveredRole(
                company_name=job.get("company") or company_name,
                title=title,
                location=location,
                url=url,
                ats_type="theirstack",
                ats_job_id=job_id,
                workplace_type=workplace_type,
                employment_type=(
                    ", ".join(job["employment_statuses"])
                    if isinstance(job.get("employment_statuses"), list)
                    else None
                ),
                is_remote=is_remote if isinstance(is_remote, bool) else None,
                posted_at=posted_at,
                fetched_at=now_iso,
                source_path="theirstack",
            )
        )

    return roles
