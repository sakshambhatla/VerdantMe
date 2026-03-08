from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import click

from jobfinder.config import AppConfig, load_config, require_api_key
from jobfinder.storage.store import StorageManager
from jobfinder.utils.display import (
    console,
    display_companies,
    display_error,
    display_flagged,
    display_roles,
    display_success,
)


@click.group()
@click.option(
    "--config",
    "config_path",
    type=click.Path(),
    default="config.json",
    help="Path to config file",
)
@click.pass_context
def cli(ctx: click.Context, config_path: str) -> None:
    """JobFinder: Discover companies and roles that match your resume."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path


@cli.command()
@click.option(
    "--resume-dir",
    type=click.Path(exists=True),
    default=None,
    help="Directory containing .txt resume files",
)
@click.pass_context
def resume(ctx: click.Context, resume_dir: str | None) -> None:
    """Parse and index resume .txt files."""
    from jobfinder.resume.parser import parse_resumes

    config = load_config(ctx.obj["config_path"], resume_dir=resume_dir)
    store = StorageManager(config.data_dir)

    console.print(f"Scanning for resumes in [bold]{config.resume_dir}[/bold]...")

    try:
        resumes = parse_resumes(config.resume_dir)
    except FileNotFoundError as exc:
        display_error(str(exc))
        raise SystemExit(1)

    data = [r.model_dump() for r in resumes]
    store.write("resumes.json", data)

    display_success(
        f"Parsed {len(resumes)} resume(s). "
        f"Saved to {config.data_dir / 'resumes.json'}"
    )

    for r in resumes:
        console.print(f"\n  [cyan]{r.filename}[/cyan]")
        if r.skills:
            console.print(f"    Skills: {', '.join(r.skills[:10])}")
        if r.job_titles:
            console.print(f"    Titles: {', '.join(r.job_titles)}")
        if r.years_of_experience:
            console.print(f"    Experience: ~{r.years_of_experience} years")


@cli.command("discover-companies")
@click.option(
    "--max-companies",
    type=int,
    default=None,
    help="Maximum number of companies to suggest",
)
@click.option(
    "--refresh",
    is_flag=True,
    default=False,
    help="Re-discover even if companies.json exists",
)
@click.pass_context
def discover_companies(
    ctx: click.Context, max_companies: int | None, refresh: bool
) -> None:
    """Use Claude to discover relevant companies based on your resume."""
    from jobfinder.companies.discovery import discover_companies as _discover

    config = load_config(ctx.obj["config_path"], max_companies=max_companies)
    store = StorageManager(config.data_dir)

    # Check prerequisites
    if not store.exists("resumes.json"):
        display_error(
            "No resumes found. Run 'jobfinder resume' first to parse your resumes."
        )
        raise SystemExit(1)

    effective_refresh = refresh or config.refresh
    if store.exists("companies.json") and not effective_refresh:
        console.print(
            "companies.json already exists. Use --refresh to re-discover."
        )
        existing = store.read("companies.json")
        if existing and "companies" in existing:
            display_companies(existing["companies"])
        return

    require_api_key(config.model_provider)

    resumes = store.read("resumes.json")
    if not resumes:
        display_error("resumes.json is empty. Re-run 'jobfinder resume'.")
        raise SystemExit(1)

    provider_label = config.model_provider.capitalize()
    console.print(
        f"Asking {provider_label} to suggest up to [bold]{config.max_companies}[/bold] companies "
        f"(streaming response below)..."
    )

    try:
        companies = _discover(resumes, config)
    except Exception as exc:
        display_error(f"Company discovery failed: {exc}")
        raise SystemExit(1)

    # Compute a hash of resume content for cache invalidation
    resume_text = "".join(r.get("full_text", "") for r in resumes)
    resume_hash = hashlib.sha256(resume_text.encode()).hexdigest()[:16]

    # Merge with existing companies if configured
    if config.write_preference == "merge" and store.exists("companies.json"):
        existing_data = store.read("companies.json") or {}
        from jobfinder.storage.schemas import DiscoveredCompany
        existing = [
            DiscoveredCompany.model_validate(c)
            for c in existing_data.get("companies", [])
        ]
        seen: dict[str, object] = {c.name.lower(): c for c in existing}
        for c in companies:  # new takes precedence
            seen[c.name.lower()] = c
        companies = list(seen.values())
        console.print(f"  [dim]Merged → {len(companies)} total companies[/dim]")

    output = {
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "source_resume_hash": resume_hash,
        "companies": [c.model_dump() for c in companies],
    }
    store.write("companies.json", output)

    display_success(f"Discovered {len(companies)} companies.")
    display_companies(output["companies"])


@cli.command("discover-roles")
@click.option(
    "--company",
    type=str,
    default=None,
    help="Fetch roles for a specific company only",
)
@click.option(
    "--refresh",
    is_flag=True,
    default=False,
    help="Re-fetch roles even if roles.json exists",
)
@click.option(
    "--continue", "resume",
    is_flag=True,
    default=False,
    help="Resume from a previous run that was interrupted by a rate-limit error",
)
@click.pass_context
def discover_roles_cmd(
    ctx: click.Context, company: str | None, refresh: bool, resume: bool
) -> None:
    """Read open roles from discovered companies' career pages via public ATS APIs."""
    from jobfinder.roles.checkpoint import CHECKPOINT_FILENAME, Checkpoint
    from jobfinder.roles.discovery import discover_roles
    from jobfinder.roles.errors import RateLimitError
    from jobfinder.storage.schemas import DiscoveredCompany, DiscoveredRole

    config = load_config(ctx.obj["config_path"])
    store = StorageManager(config.data_dir)
    cp = Checkpoint(store.data_dir / CHECKPOINT_FILENAME)

    if not store.exists("companies.json"):
        display_error(
            "No companies found. Run 'jobfinder discover-companies' first."
        )
        raise SystemExit(1)

    # If filters or scoring are configured, ensure the API key is available up front
    if config.role_filters or config.relevance_score_criteria:
        require_api_key(config.model_provider)

    effective_refresh = refresh or config.refresh
    if store.exists("roles.json") and not effective_refresh and not resume:
        console.print("roles.json already exists. Use --refresh to re-fetch.")
        existing = store.read("roles.json")
        if existing:
            display_roles(existing.get("roles", []))
            display_flagged(existing.get("flagged_companies", []))
        return

    companies_data = store.read("companies.json")
    raw_companies = companies_data.get("companies", [])

    # ── Determine whether to resume or start fresh ────────────────────────────

    if resume and cp.exists():
        cp.load()
        console.print(f"[yellow]Resuming:[/yellow] {cp.summary()}")
        companies = [DiscoveredCompany.model_validate(c) for c in raw_companies]
        roles = [DiscoveredRole.model_validate(r) for r in cp.raw_roles]
        flagged_dicts = cp.flagged_companies
        resume_filter_batches = cp.filter_batches_done
        resume_filter_kept = [
            DiscoveredRole.model_validate(r) for r in cp.filter_kept_roles
        ]
        resume_score_batches = cp.score_batches_done
    else:
        if resume and not cp.exists():
            console.print("[yellow]No checkpoint found — starting fresh.[/yellow]")

        # Filter to specific company if requested
        if company:
            raw_companies = [
                c for c in raw_companies if company.lower() in c["name"].lower()
            ]
            if not raw_companies:
                display_error(f"No company matching '{company}' found in companies.json.")
                raise SystemExit(1)

        companies = [DiscoveredCompany.model_validate(c) for c in raw_companies]
        console.print(f"Fetching roles from [bold]{len(companies)}[/bold] companies...\n")

        roles, flagged = discover_roles(companies, config)
        flagged_dicts = [f.model_dump() for f in flagged]

        # Save checkpoint after successful ATS fetch
        cp.save_after_fetch(
            raw_roles=roles,
            flagged=flagged,
            filter_config=config.role_filters.model_dump() if config.role_filters else None,
            score_criteria=config.relevance_score_criteria,
            filter_batch_size=100,
            score_batch_size=60,
        )

        resume_filter_batches = 0
        resume_filter_kept = []
        resume_score_batches = 0

    # ── Filter ────────────────────────────────────────────────────────────────

    filtered_roles = roles
    if config.role_filters and roles:
        from jobfinder.roles.filters import filter_roles
        try:
            filtered_roles = filter_roles(
                roles, config.role_filters, config,
                checkpoint=cp,
                resume_batches=resume_filter_batches,
                resume_kept=resume_filter_kept,
            )
        except RateLimitError as exc:
            display_error(
                f"Rate limit hit — {exc}\n"
                f"Run [bold]jobfinder discover-roles --continue[/bold] to resume."
            )
            raise SystemExit(1)
        console.print(
            f"  [dim]{len(roles)} total → "
            f"[bold]{len(filtered_roles)}[/bold] after filtering[/dim]"
        )

    # ── Score ─────────────────────────────────────────────────────────────────

    scored_roles = filtered_roles
    if config.relevance_score_criteria and filtered_roles:
        from jobfinder.roles.scorer import score_roles
        try:
            scored_roles = score_roles(
                filtered_roles, config.relevance_score_criteria, config,
                checkpoint=cp,
                resume_batches=resume_score_batches,
            )
        except RateLimitError as exc:
            display_error(
                f"Rate limit hit — {exc}\n"
                f"Run [bold]jobfinder discover-roles --continue[/bold] to resume."
            )
            raise SystemExit(1)

    # ── Merge with existing roles if configured ───────────────────────────────

    final_roles = scored_roles
    if config.write_preference == "merge" and store.exists("roles.json"):
        existing_data = store.read("roles.json") or {}
        existing_roles = [
            DiscoveredRole.model_validate(r)
            for r in existing_data.get("roles", [])
        ]
        seen: dict[str, DiscoveredRole] = {r.url: r for r in existing_roles}
        for r in scored_roles:
            seen[r.url] = r
        final_roles = sorted(seen.values(), key=lambda r: -(r.relevance_score or 0))
        console.print(f"  [dim]Merged → {len(final_roles)} total roles[/dim]")

    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total_roles": len(roles),
        "roles_after_filter": len(filtered_roles),
        "companies_fetched": len(companies) - len(flagged_dicts),
        "companies_flagged": len(flagged_dicts),
        "flagged_companies": flagged_dicts,
        "roles": [r.model_dump() for r in final_roles],
    }
    store.write("roles.json", output)

    # Clean up checkpoint — complete result is now in roles.json
    cp.delete()

    console.print()
    summary = f"Found {len(roles)} roles from {len(companies) - len(flagged_dicts)} companies"
    if config.role_filters:
        summary += f", {len(filtered_roles)} matched filters"
    if config.relevance_score_criteria:
        summary += ", scored and sorted by relevance"
    display_success(summary + ".")
    if final_roles:
        display_roles(output["roles"])
    display_flagged(flagged_dicts)


@cli.command("serve")
@click.option("--host", default="127.0.0.1", show_default=True, help="Host to bind to")
@click.option("--port", default=8000, show_default=True, type=int, help="Port to listen on")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload (development)")
def serve_cmd(host: str, port: int, reload: bool) -> None:
    """Launch the JobFinder web UI server."""
    import uvicorn

    console.print(
        f"Starting JobFinder UI at [bold cyan]http://{host}:{port}[/bold cyan]"
    )
    uvicorn.run("jobfinder.api.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    cli()
