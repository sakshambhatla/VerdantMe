from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from jobfinder.config import AppConfig, get_rapidapi_key, get_theirstack_api_key
from jobfinder.roles.ats import get_fetcher
from jobfinder.roles.ats.base import ATSFetchError, UnsupportedATSError
from jobfinder.roles.ats.career_page import fetch_career_page_roles
from jobfinder.roles.cache import RolesCache
from jobfinder.roles.metrics import RunMetricsCollector
from jobfinder.roles.sources import get_enabled_sources
from jobfinder.roles.sources.cache import ExternalSourceCache
from jobfinder.storage.backend import StorageBackend
from jobfinder.storage.registry import update_registry_searchable
from jobfinder.storage.schemas import DiscoveredCompany, DiscoveredRole, FlaggedCompany
from jobfinder.utils.display import console, display_warning
from jobfinder.utils.log_stream import log

if TYPE_CHECKING:
    ProgressCallback = Callable[[list[DiscoveredRole], list[FlaggedCompany]], None]


def discover_roles(
    companies: list[DiscoveredCompany],
    config: AppConfig,
    *,
    store: StorageBackend,
    use_cache: bool = False,
    on_progress: ProgressCallback | None = None,
    metrics: RunMetricsCollector | None = None,
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

    cache = RolesCache(store)

    # ── Pass 0: External job board sources ─────────────────────────────────
    enabled_sources = get_enabled_sources(config)
    if enabled_sources:
        ext_cache = ExternalSourceCache(store)
        n_sources = len(enabled_sources)
        log(
            f"\n[bold]Pass 0 — External job boards[/bold] "
            f"({n_sources} {'source' if n_sources == 1 else 'sources'}): "
            f"fetching aggregated job feeds..."
        )
        for source_name, source in enabled_sources:
            # Cache check
            if use_cache:
                cached = ext_cache.get(source_name)
                if cached is not None:
                    all_roles.extend(cached)
                    age = ext_cache.age_hours(source_name) or 0
                    log(
                        f"  [dim]{source.name}[/dim]: "
                        f"{len(cached)} roles (cached {age:.0f}h ago)"
                    )
                    if on_progress:
                        on_progress(all_roles, flagged)
                    continue

            rapidapi_key = get_rapidapi_key()
            if not rapidapi_key:
                log(
                    f"  [yellow]{source.name}: RAPIDAPI_KEY not set — skipped[/yellow]",
                    level="warning",
                )
                continue

            with console.status(f"Fetching from {source.name}..."):
                try:
                    roles = source.fetch_all(
                        api_key=rapidapi_key,
                        timeout=config.request_timeout,
                    )
                    all_roles.extend(roles)
                    ext_cache.put(source_name, roles, source.cache_ttl_hours)
                    if metrics:
                        metrics.record_external_source(source_name, len(roles))
                    log(
                        f"  [green]✓ {source.name}[/green]: {len(roles)} roles",
                        level="success",
                    )
                    if on_progress:
                        on_progress(all_roles, flagged)
                except Exception as exc:
                    log(
                        f"  [yellow]⚠ {source.name}: {exc}[/yellow]",
                        level="warning",
                    )
                    if metrics:
                        metrics.errors.append(f"{source.name}: {exc}")

    # ── Pass 1: ATS API fetch ────────────────────────────────────────────────
    n_companies = len(companies)
    if metrics:
        metrics.companies_total = n_companies
    log(
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
                if cached:
                    update_registry_searchable(store, company.name, True)
                log(
                    f"  [dim]{company.name}[/dim]: "
                    f"{len(cached)} roles (cached {age:.0f}h ago)"
                )
                if on_progress:
                    on_progress(all_roles, flagged)
                continue

        fetcher = get_fetcher(company.ats_type)

        with console.status(f"Fetching roles from {company.name}..."):
            try:
                roles = fetcher.fetch(company, config.request_timeout)
                all_roles.extend(roles)
                cache.put(company.name, company.ats_type, roles)
                if metrics:
                    metrics.record_ats_fetch(company.name, company.ats_type, len(roles))
                update_registry_searchable(store, company.name, True)
                log(
                    f"  [green]✓ {company.name}[/green]: {len(roles)} roles "
                    f"via [cyan]{company.ats_type.upper()}[/cyan] API",
                    level="success",
                )
                if on_progress:
                    on_progress(all_roles, flagged)
            except UnsupportedATSError:
                reason = f"{company.ats_type} does not have a public API for automated fetching"
                flagged.append(
                    FlaggedCompany(
                        name=company.name,
                        ats_type=company.ats_type,
                        career_page_url=company.career_page_url,
                        reason=reason,
                    )
                )
                if metrics:
                    metrics.record_ats_failure(company.name, company.ats_type, reason)
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
                if metrics:
                    metrics.record_ats_failure(company.name, company.ats_type, str(exc))
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
                if metrics:
                    metrics.record_ats_failure(company.name, company.ats_type, str(exc))
                display_warning(f"{company.name}: Unexpected error — {exc}")

    # ── Pass 1 summary ───────────────────────────────────────────────────────
    _n_flagged = len(flagged)
    log(
        f"  [dim]Pass 1 complete: {len(all_roles)} roles fetched"
        + (f" · {_n_flagged} {'company' if _n_flagged == 1 else 'companies'} "
           f"had no public API (will try"
           f"{' TheirStack →' if config.enable_theirstack else ''} career page)"
           if _n_flagged else "")
        + "[/dim]"
    )

    # ── Pass 1.5: TheirStack fallback ────────────────────────────────────────
    # Only for flagged companies (ATS failed).  TheirStack costs credits, so
    # we check availability before each call and respect the credit budget.
    if config.enable_theirstack and flagged:
        from jobfinder.roles.theirstack.client import TheirStackError, search_jobs
        from jobfinder.roles.theirstack.credits import CreditTracker

        ts_api_key = get_theirstack_api_key()
        if not ts_api_key:
            log(
                "\n[dim]Pass 1.5 skipped — THEIRSTACK_API_KEY not set[/dim]",
                level="warning",
            )
        else:
            credit_tracker = CreditTracker(store, budget=config.theirstack_credit_budget)
            ts_limit = config.theirstack_max_results
            _n_ts_flagged = len(flagged)

            log(
                f"\n[bold]Pass 1.5 — TheirStack fallback[/bold] "
                f"({_n_ts_flagged} {'company' if _n_ts_flagged == 1 else 'companies'}): "
                f"searching job postings via TheirStack API "
                f"({credit_tracker.remaining} credits remaining)..."
            )

            still_flagged: list[FlaggedCompany] = []
            for fc in flagged:
                if not credit_tracker.can_afford(ts_limit):
                    log(
                        f"  [yellow]⚠ {fc.name}: insufficient credits "
                        f"({credit_tracker.remaining} remaining, need {ts_limit}) — skipped[/yellow]",
                        level="warning",
                    )
                    still_flagged.append(fc)
                    continue

                # Cache check
                if use_cache:
                    cached_ts = cache.get(fc.name, "theirstack")
                    if cached_ts is not None:
                        all_roles.extend(cached_ts)
                        age = cache.age_hours(fc.name, "theirstack") or 0
                        update_registry_searchable(store, fc.name, bool(cached_ts))
                        log(
                            f"  [dim]{fc.name}[/dim]: "
                            f"{len(cached_ts)} roles (cached {age:.0f}h ago)"
                        )
                        if on_progress:
                            on_progress(all_roles, still_flagged)
                        continue  # don't re-add to flagged

                # Find company domain from the original companies list
                company_domain = None
                for c in companies:
                    if c.name.lower() == fc.name.lower() and c.career_page_url:
                        try:
                            from urllib.parse import urlparse
                            parsed = urlparse(c.career_page_url)
                            if parsed.hostname:
                                # Strip www. prefix for cleaner domain matching
                                domain = parsed.hostname
                                if domain.startswith("www."):
                                    domain = domain[4:]
                                company_domain = domain
                        except Exception:
                            pass
                        break

                with console.status(f"Searching TheirStack for {fc.name}..."):
                    try:
                        ts_roles = search_jobs(
                            fc.name,
                            company_domain=company_domain,
                            filters=config.role_filters,
                            config=config,
                            api_key=ts_api_key,
                            max_results=ts_limit,
                        )
                        credits_spent = len(ts_roles)
                        credit_tracker.spend(credits_spent)
                        all_roles.extend(ts_roles)
                        cache.put(fc.name, "theirstack", ts_roles)
                        if metrics:
                            metrics.record_theirstack_fetch(fc.name, len(ts_roles), credits_spent)
                        update_registry_searchable(store, fc.name, bool(ts_roles))
                        log(
                            f"  [green]✓ {fc.name}[/green]: {len(ts_roles)} roles "
                            f"via [cyan]TheirStack[/cyan] ({credits_spent} credits, "
                            f"{credit_tracker.remaining} remaining)",
                            level="success",
                        )
                        if on_progress:
                            on_progress(all_roles, still_flagged)
                        # Don't add to still_flagged — company rescued
                    except TheirStackError as exc:
                        still_flagged.append(fc)
                        if metrics:
                            metrics.errors.append(f"{fc.name} (theirstack): {exc}")
                        display_warning(f"{fc.name}: TheirStack fallback failed — {exc}")
                    except Exception as exc:
                        still_flagged.append(fc)
                        if metrics:
                            metrics.errors.append(f"{fc.name} (theirstack): {exc}")
                        display_warning(f"{fc.name}: TheirStack unexpected error — {exc}")

            flagged = still_flagged

    # ── Pass 2: career page fallback ─────────────────────────────────────────
    # Only run for companies where ATS failed — career page is a fallback, not
    # a supplement. Companies with working ATS feeds (Greenhouse/Lever/Ashby)
    # already have complete data; re-fetching via Playwright wastes time.
    if config.skip_career_page:
        log("\n[dim]Pass 2 skipped (API-only mode — career page fallback disabled)[/dim]")
        return all_roles, flagged

    existing_urls: set[str] = {r.url for r in all_roles if r.url}
    flagged_names: set[str] = {f.name.lower() for f in flagged}

    _flagged_with_pages = [
        c for c in companies
        if c.name.lower() in flagged_names and c.career_page_url
    ]
    if _flagged_with_pages:
        log(
            "\n[bold]Pass 2 — Career page fallback[/bold]: "
            "rendering pages with Playwright and extracting roles with LLM..."
        )

    for company in companies:
        if not company.career_page_url:
            if company.name.lower() in flagged_names:
                log(
                    f"  [dim]{company.name}: no career page URL configured — "
                    f"skipping (use browser agent to fetch)[/dim]"
                )
            continue

        is_fallback = company.name.lower() in flagged_names
        if not is_fallback:
            # ATS succeeded — skip career page entirely
            continue

        log(
            f"  [yellow]↳ ATS failed — trying career page for {company.name}...[/yellow]",
            level="warning",
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
                log(
                    f"  [dim]{company.name} (career_page)[/dim]: "
                    f"{len(cached_cp)} roles (cached {age:.0f}h ago)"
                )
                if is_fallback and cached_cp:
                    flagged = [f for f in flagged if f.name.lower() != company.name.lower()]
                    flagged_names.discard(company.name.lower())
                update_registry_searchable(store, company.name, bool(cached_cp))
                if on_progress:
                    on_progress(all_roles, flagged)
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
                if metrics:
                    metrics.record_career_page(company.name, len(cp_roles))
                if is_fallback and cp_roles:
                    flagged = [f for f in flagged if f.name.lower() != company.name.lower()]
                    flagged_names.discard(company.name.lower())
                    log(
                        f"  [green]✓ {company.name}[/green]: rescued via career page "
                        f"({len(cp_roles)} roles, {len(new_roles)} new)",
                        level="success",
                    )
                    if on_progress:
                        on_progress(all_roles, flagged)
                elif new_roles:
                    log(
                        f"  [green]✓ {company.name}[/green]: "
                        f"{len(new_roles)} additional roles via career page",
                        level="success",
                    )
                    if on_progress:
                        on_progress(all_roles, flagged)
                elif is_fallback and not cp_roles:
                    display_warning(
                        f"{company.name}: career page returned no roles — "
                        f"try 'Fetch via Browser Agent' for agentic extraction"
                    )
            except Exception as exc:
                if metrics:
                    metrics.record_career_page_failure(company.name, str(exc))
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
    log(
        f"\n[bold]Fetch complete[/bold]: {len(all_roles)} roles"
        + (f" across {n_unique_cos} companies" if n_unique_cos != n_companies else "")
        + (f" · [yellow]{n_final_flagged} flagged[/yellow]" if n_final_flagged else "")
    )
    if n_final_flagged:
        flagged_names_str = ", ".join(f.name for f in flagged)
        log(
            f"  [dim]Flagged ({flagged_names_str}): no public ATS API and no static "
            f"career page content found.[/dim]"
        )
        log(
            f"  [dim]→ Note: 'Fetch via Browser Agent' is a separate explicit action "
            f"(not part of this pipeline) — use it in the UI for flagged companies.[/dim]"
        )

    return all_roles, flagged
