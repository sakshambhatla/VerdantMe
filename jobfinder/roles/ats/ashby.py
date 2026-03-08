from __future__ import annotations

from datetime import datetime, timezone

import httpx

from jobfinder.roles.ats.base import ATSFetchError, BaseFetcher
from jobfinder.storage.schemas import DiscoveredCompany, DiscoveredRole
from jobfinder.utils.http import get_json

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{board_token}"


class AshbyFetcher(BaseFetcher):
    def fetch(
        self, company: DiscoveredCompany, timeout: int
    ) -> list[DiscoveredRole]:
        if not company.ats_board_token:
            raise ATSFetchError(
                f"No Ashby board token for {company.name}"
            )

        url = BASE_URL.format(board_token=company.ats_board_token)
        try:
            data = get_json(
                url, timeout=timeout, params={"includeCompensation": "true"}
            )
        except httpx.HTTPStatusError as exc:
            raise ATSFetchError(
                f"Ashby API returned HTTP {exc.response.status_code} for {company.name} "
                f"(token: {company.ats_board_token!r}) — company may not use Ashby"
            ) from exc
        except httpx.TransportError as exc:
            raise ATSFetchError(
                f"Ashby API unreachable for {company.name}: {exc}"
            ) from exc
        now = datetime.now(timezone.utc).isoformat()

        roles = []
        for job in data.get("jobs", []):
            roles.append(
                DiscoveredRole(
                    company_name=company.name,
                    title=job.get("title", "Untitled"),
                    location=job.get("location", "Unknown"),
                    url=job.get("jobUrl", ""),
                    ats_type="ashby",
                    department=job.get("department"),
                    team=job.get("team"),
                    is_remote=job.get("isRemote"),
                    workplace_type=job.get("workplaceType"),
                    employment_type=job.get("employmentType"),
                    published_at=job.get("publishedAt"),
                    fetched_at=now,
                )
            )
        return roles
