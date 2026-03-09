from __future__ import annotations

from jobfinder.config import AppConfig
from jobfinder.roles.ats import get_fetcher
from jobfinder.roles.ats.base import ATSFetchError, UnsupportedATSError
from jobfinder.roles.ats.career_page import fetch_career_page_roles
from jobfinder.storage.registry import update_registry_searchable
from jobfinder.storage.schemas import DiscoveredCompany, DiscoveredRole, FlaggedCompany
from jobfinder.storage.store import StorageManager
from jobfinder.utils.display import console, display_warning


def discover_roles(
    companies: list[DiscoveredCompany],
    config: AppConfig,
) -> tuple[list[DiscoveredRole], list[FlaggedCompany]]:
    """Fetch roles from all companies. Returns (roles, flagged_companies).

    Two-pass approach:
      1. ATS APIs (Greenhouse/Lever/Ashby) — structured, fast
      2. Career page HTML parsed by LLM — supplements ATS results, deduplicated by URL
    """
    all_roles: list[DiscoveredRole] = []
    flagged: list[FlaggedCompany] = []

    # ── Pass 1: ATS API fetch ────────────────────────────────────────────────
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

    # ── Pass 2: career page supplemental fetch ───────────────────────────────
    store = StorageManager(config.data_dir)
    existing_urls: set[str] = {r.url for r in all_roles if r.url}

    for company in companies:
        if not company.career_page_url:
            continue

        with console.status(f"Checking career page for {company.name}..."):
            searchable: bool
            try:
                cp_roles = fetch_career_page_roles(
                    company.name, company.career_page_url, config
                )
                new_roles = [
                    r for r in cp_roles if not r.url or r.url not in existing_urls
                ]
                if new_roles:
                    all_roles.extend(new_roles)
                    existing_urls.update(r.url for r in new_roles if r.url)
                    console.print(
                        f"  [green]{company.name}[/green]: "
                        f"{len(new_roles)} additional roles via career page"
                    )
                searchable = bool(cp_roles)
            except Exception as exc:
                display_warning(f"{company.name}: career page fetch failed — {exc}")
                searchable = False

            update_registry_searchable(store, company.name, searchable)

    return all_roles, flagged
