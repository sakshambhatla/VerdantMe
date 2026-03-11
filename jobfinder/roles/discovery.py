from __future__ import annotations

from jobfinder.config import AppConfig
from jobfinder.roles.ats import get_fetcher
from jobfinder.roles.ats.base import ATSFetchError, UnsupportedATSError
from jobfinder.roles.ats.career_page import fetch_career_page_roles
from jobfinder.roles.cache import RolesCache
from jobfinder.storage.registry import update_registry_searchable
from jobfinder.storage.schemas import DiscoveredCompany, DiscoveredRole, FlaggedCompany
from jobfinder.storage.store import StorageManager
from jobfinder.utils.display import console, display_warning


def discover_roles(
    companies: list[DiscoveredCompany],
    config: AppConfig,
    use_cache: bool = False,
) -> tuple[list[DiscoveredRole], list[FlaggedCompany]]:
    """Fetch roles from all companies. Returns (roles, flagged_companies).

    Two-pass approach:
      1. ATS APIs (Greenhouse/Lever/Ashby) — structured, fast
      2. Career page HTML parsed by LLM — supplements ATS results, deduplicated by URL

    When ``use_cache=True``, each company+ATS pair is checked in the local
    roles cache before making any network request.  Cache entries older than
    2 days are treated as misses.  A fresh cache entry is always written after
    every successful network fetch.
    """
    all_roles: list[DiscoveredRole] = []
    flagged: list[FlaggedCompany] = []

    store = StorageManager(config.data_dir)
    cache = RolesCache(store)

    # ── Pass 1: ATS API fetch ────────────────────────────────────────────────
    n_companies = len(companies)
    console.print(
        f"\n[bold]Pass 1 — ATS API[/bold] "
        f"({n_companies} {'company' if n_companies == 1 else 'companies'}): "
        f"fetching structured job feeds..."
    )
    for company in companies:
        # Cache check
        if use_cache:
            cached = cache.get(company.name, company.ats_type)
            if cached is not None:
                all_roles.extend(cached)
                age = cache.age_hours(company.name, company.ats_type) or 0
                console.print(
                    f"  [dim]{company.name}[/dim]: "
                    f"{len(cached)} roles (cached {age:.0f}h ago)"
                )
                continue

        fetcher = get_fetcher(company.ats_type)

        with console.status(f"Fetching roles from {company.name}..."):
            try:
                roles = fetcher.fetch(company, config.request_timeout)
                all_roles.extend(roles)
                cache.put(company.name, company.ats_type, roles)
                console.print(
                    f"  [green]✓ {company.name}[/green]: {len(roles)} roles "
                    f"via [cyan]{company.ats_type.upper()}[/cyan] API"
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
                    f"{company.name}: {company.ats_type} ATS has no public API — "
                    f"flagged (try 'Fetch via Browser Agent')"
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

    # ── Pass 1 summary ───────────────────────────────────────────────────────
    _n_flagged = len(flagged)
    console.print(
        f"  [dim]Pass 1 complete: {len(all_roles)} roles fetched"
        + (f" · {_n_flagged} {'company' if _n_flagged == 1 else 'companies'} "
           f"had no public API (will try career page)" if _n_flagged else "")
        + "[/dim]"
    )

    # ── Pass 2: career page supplemental fetch ───────────────────────────────
    _has_career_pages = any(c.career_page_url for c in companies)
    if _has_career_pages:
        console.print(
            "\n[bold]Pass 2 — Career page supplement[/bold]: "
            "rendering pages with Playwright and extracting roles with LLM..."
        )
    existing_urls: set[str] = {r.url for r in all_roles if r.url}
    flagged_names: set[str] = {f.name.lower() for f in flagged}

    for company in companies:
        if not company.career_page_url:
            if company.name.lower() in flagged_names:
                console.print(
                    f"  [dim]{company.name}: no career page URL configured — "
                    f"skipping (use browser agent to fetch)[/dim]"
                )
            continue

        is_fallback = company.name.lower() in flagged_names
        if is_fallback:
            console.print(
                f"  [yellow]↳ ATS failed — trying career page for {company.name}...[/yellow]"
            )

        # Cache check for career page
        if use_cache:
            cached_cp = cache.get(company.name, "career_page")
            if cached_cp is not None:
                new_roles = [r for r in cached_cp if not r.url or r.url not in existing_urls]
                if new_roles:
                    all_roles.extend(new_roles)
                    existing_urls.update(r.url for r in new_roles if r.url)
                age = cache.age_hours(company.name, "career_page") or 0
                console.print(
                    f"  [dim]{company.name} (career_page)[/dim]: "
                    f"{len(cached_cp)} roles (cached {age:.0f}h ago)"
                )
                if is_fallback and cached_cp:
                    flagged = [f for f in flagged if f.name.lower() != company.name.lower()]
                    flagged_names.discard(company.name.lower())
                update_registry_searchable(store, company.name, bool(cached_cp))
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
                cache.put(company.name, "career_page", cp_roles)
                searchable = bool(cp_roles)
                if is_fallback and cp_roles:
                    flagged = [f for f in flagged if f.name.lower() != company.name.lower()]
                    flagged_names.discard(company.name.lower())
                    console.print(
                        f"  [green]✓ {company.name}[/green]: rescued via career page "
                        f"({len(cp_roles)} roles, {len(new_roles)} new)"
                    )
                elif new_roles:
                    console.print(
                        f"  [green]✓ {company.name}[/green]: "
                        f"{len(new_roles)} additional roles via career page"
                    )
                elif is_fallback and not cp_roles:
                    display_warning(
                        f"{company.name}: career page returned no roles — "
                        f"try 'Fetch via Browser Agent' for agentic extraction"
                    )
                else:
                    # ATS succeeded and career page added nothing new — clarify impact
                    console.print(
                        f"  [dim]{company.name}: career page check found no new roles "
                        f"(ATS feed appears complete)[/dim]"
                    )
            except Exception as exc:
                if is_fallback:
                    display_warning(
                        f"{company.name}: ATS failed and career page also unreachable — {exc}"
                    )
                else:
                    display_warning(f"{company.name}: career page fetch failed — {exc}")
                searchable = False

            update_registry_searchable(store, company.name, searchable)

    # ── Fetch summary ────────────────────────────────────────────────────────
    n_unique_cos = len({r.company_name for r in all_roles})
    n_final_flagged = len(flagged)
    console.print(
        f"\n[bold]Fetch complete[/bold]: {len(all_roles)} roles"
        + (f" across {n_unique_cos} companies" if n_unique_cos != n_companies else "")
        + (f" · [yellow]{n_final_flagged} flagged[/yellow]" if n_final_flagged else "")
    )
    if n_final_flagged:
        flagged_names_str = ", ".join(f.name for f in flagged)
        console.print(
            f"  [dim]Flagged ({flagged_names_str}): no public ATS API and no static "
            f"career page content found.[/dim]"
        )
        console.print(
            f"  [dim]→ Note: 'Fetch via Browser Agent' is a separate explicit action "
            f"(not part of this pipeline) — use it in the UI for flagged companies.[/dim]"
        )

    return all_roles, flagged
