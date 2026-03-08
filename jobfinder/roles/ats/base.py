from __future__ import annotations

from abc import ABC, abstractmethod

from jobfinder.storage.schemas import DiscoveredCompany, DiscoveredRole


class ATSFetchError(Exception):
    """Raised when fetching roles from an ATS fails."""


class UnsupportedATSError(ATSFetchError):
    """Raised when the ATS type does not support automated fetching."""


class BaseFetcher(ABC):
    @abstractmethod
    def fetch(
        self, company: DiscoveredCompany, timeout: int
    ) -> list[DiscoveredRole]:
        """Fetch open roles for a company. Raises ATSFetchError on failure."""
        ...
