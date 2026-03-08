from __future__ import annotations

from jobfinder.config import AppConfig
from jobfinder.roles.ats import get_fetcher
from jobfinder.roles.ats.base import ATSFetchError, UnsupportedATSError
from jobfinder.storage.schemas import DiscoveredCompany, DiscoveredRole, FlaggedCompany
from jobfinder.utils.display import console, display_warning


def discover_roles(
    companies: list[DiscoveredCompany],
    config: AppConfig,
) -> tuple[list[DiscoveredRole], list[FlaggedCompany]]:
    """Fetch roles from all companies. Returns (roles, flagged_companies)."""
    all_roles: list[DiscoveredRole] = []
    flagged: list[FlaggedCompany] = []

    for company in companies:
        fetcher = get_fetcher(company.ats_type)

        with console.status(f"Fetching roles from {company.name}..."):
            try:
                roles = fetcher.fetch(company, config.request_timeout)
                all_roles.extend(roles)
                console.print(
                    f"  [green]{company.name}[/green]: {len(roles)} roles found"
                )
            except UnsupportedATSError:
                flagged.append(
                    FlaggedCompany(
                        name=company.name,
                        ats_type=company.ats_type,
                        career_page_url=company.career_page_url,
                        reason=f"{company.ats_type} does not have a public API for automated fetching",
                    )
                )
                display_warning(
                    f"{company.name}: {company.ats_type} not supported — manual check needed"
                )
            except ATSFetchError as exc:
                flagged.append(
                    FlaggedCompany(
                        name=company.name,
                        ats_type=company.ats_type,
                        career_page_url=company.career_page_url,
                        reason=str(exc),
                    )
                )
                display_warning(f"{company.name}: {exc}")
            except Exception as exc:
                flagged.append(
                    FlaggedCompany(
                        name=company.name,
                        ats_type=company.ats_type,
                        career_page_url=company.career_page_url,
                        reason=f"Unexpected error: {exc}",
                    )
                )
                display_warning(f"{company.name}: Unexpected error — {exc}")

    return all_roles, flagged
