from __future__ import annotations

from jobfinder.roles.ats.base import BaseFetcher, UnsupportedATSError
from jobfinder.storage.schemas import DiscoveredCompany, DiscoveredRole


class UnsupportedFetcher(BaseFetcher):
    def __init__(self, ats_type: str):
        self.ats_type = ats_type

    def fetch(
        self, company: DiscoveredCompany, timeout: int
    ) -> list[DiscoveredRole]:
        raise UnsupportedATSError(
            f"{self.ats_type} does not have a public API. "
            f"Check manually: {company.career_page_url}"
        )
