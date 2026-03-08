from __future__ import annotations

from datetime import datetime, timezone

from jobfinder.roles.ats.base import ATSFetchError, BaseFetcher
from jobfinder.storage.schemas import DiscoveredCompany, DiscoveredRole
from jobfinder.utils.http import get_json

BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"


class GreenhouseFetcher(BaseFetcher):
    def fetch(
        self, company: DiscoveredCompany, timeout: int
    ) -> list[DiscoveredRole]:
        if not company.ats_board_token:
            raise ATSFetchError(
                f"No Greenhouse board token for {company.name}"
            )

        url = BASE_URL.format(board_token=company.ats_board_token)
        data = get_json(url, timeout=timeout)
        now = datetime.now(timezone.utc).isoformat()

        roles = []
        for job in data.get("jobs", []):
            location = job.get("location", {})
            location_name = (
                location.get("name", "Unknown")
                if isinstance(location, dict)
                else str(location)
            )
            roles.append(
                DiscoveredRole(
                    company_name=company.name,
                    title=job.get("title", "Untitled"),
                    location=location_name,
                    url=job.get("absolute_url", ""),
                    ats_type="greenhouse",
                    ats_job_id=str(job.get("id", "")),
                    posted_at=job.get("first_published"),
                    updated_at=job.get("updated_at"),
                    fetched_at=now,
                )
            )
        return roles
