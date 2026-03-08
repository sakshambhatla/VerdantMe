from __future__ import annotations

from datetime import datetime, timezone

import httpx

from jobfinder.roles.ats.base import ATSFetchError, BaseFetcher
from jobfinder.storage.schemas import DiscoveredCompany, DiscoveredRole
from jobfinder.utils.http import get_json

BASE_URL = "https://api.lever.co/v0/postings/{company}"


class LeverFetcher(BaseFetcher):
    def fetch(
        self, company: DiscoveredCompany, timeout: int
    ) -> list[DiscoveredRole]:
        if not company.ats_board_token:
            raise ATSFetchError(
                f"No Lever board token for {company.name}"
            )

        url = BASE_URL.format(company=company.ats_board_token)
        try:
            data = get_json(url, timeout=timeout, params={"mode": "json"})
        except httpx.HTTPStatusError as exc:
            raise ATSFetchError(
                f"Lever API returned HTTP {exc.response.status_code} for {company.name} "
                f"(token: {company.ats_board_token!r}) — company may not use Lever"
            ) from exc
        except httpx.TransportError as exc:
            raise ATSFetchError(
                f"Lever API unreachable for {company.name}: {exc}"
            ) from exc
        now = datetime.now(timezone.utc).isoformat()

        # Lever returns a flat array of postings
        if not isinstance(data, list):
            return []

        roles = []
        for posting in data:
            categories = posting.get("categories", {})
            roles.append(
                DiscoveredRole(
                    company_name=company.name,
                    title=posting.get("text", "Untitled"),
                    location=categories.get("location", "Unknown"),
                    url=posting.get("hostedUrl", ""),
                    ats_type="lever",
                    ats_job_id=posting.get("id"),
                    department=categories.get("department"),
                    team=categories.get("team"),
                    commitment=categories.get("commitment"),
                    workplace_type=posting.get("workplaceType"),
                    fetched_at=now,
                )
            )
        return roles
