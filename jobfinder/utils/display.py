from __future__ import annotations

from rich.console import Console
from rich.table import Table

console = Console()


def display_companies(companies: list[dict]) -> None:
    table = Table(title="Discovered Companies")
    table.add_column("Name", style="bold cyan")
    table.add_column("ATS", style="green")
    table.add_column("Reason")
    table.add_column("Career Page")
    for c in companies:
        table.add_row(c["name"], c["ats_type"], c["reason"], c["career_page_url"])
    console.print(table)


def display_roles(roles: list[dict]) -> None:
    has_score = any(r.get("relevance_score") is not None for r in roles)
    has_summary = any(r.get("summary") for r in roles)

    table = Table(title="Open Roles")
    if has_score:
        table.add_column("Score", style="bold yellow", justify="right", width=5)
    table.add_column("Company", style="bold cyan")
    table.add_column("Title", style="bold")
    table.add_column("Location")
    if has_summary:
        table.add_column("Summary", style="dim", max_width=40)
    table.add_column("Posted", style="dim")
    table.add_column("URL", style="dim")

    for r in roles:
        posted = r.get("posted_at") or r.get("published_at") or "N/A"
        if posted != "N/A" and len(posted) > 10:
            posted = posted[:10]
        row: list[str] = []
        if has_score:
            score = r.get("relevance_score")
            row.append(str(score) if score is not None else "")
        row += [r["company_name"], r["title"], r["location"]]
        if has_summary:
            row.append(r.get("summary") or "")
        row += [posted, r["url"]]
        table.add_row(*row)
    console.print(table)


def display_flagged(flagged: list[dict]) -> None:
    if not flagged:
        return
    console.print("\n[yellow bold]Companies requiring manual check:[/yellow bold]")
    for f in flagged:
        console.print(
            f"  [yellow]- {f['name']}[/yellow] ({f['ats_type']}): {f['reason']}"
        )
        console.print(f"    [dim]{f['career_page_url']}[/dim]")


def display_warning(message: str) -> None:
    from jobfinder.utils.log_stream import log

    log(f"[yellow]WARNING:[/yellow] {message}", level="warning")


def display_error(message: str) -> None:
    from jobfinder.utils.log_stream import log

    log(f"[red]ERROR:[/red] {message}", level="error")


def display_success(message: str) -> None:
    from jobfinder.utils.log_stream import log

    log(f"[green]SUCCESS:[/green] {message}", level="success")
