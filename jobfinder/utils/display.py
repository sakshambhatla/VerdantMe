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
    table = Table(title="Open Roles")
    table.add_column("Company", style="bold cyan")
    table.add_column("Title", style="bold")
    table.add_column("Location")
    table.add_column("Posted", style="dim")
    table.add_column("URL", style="dim")
    for r in roles:
        posted = r.get("posted_at") or r.get("published_at") or "N/A"
        if posted != "N/A" and len(posted) > 10:
            posted = posted[:10]  # Just the date portion
        table.add_row(
            r["company_name"], r["title"], r["location"], posted, r["url"]
        )
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
    console.print(f"[yellow]WARNING:[/yellow] {message}")


def display_error(message: str) -> None:
    console.print(f"[red]ERROR:[/red] {message}")


def display_success(message: str) -> None:
    console.print(f"[green]SUCCESS:[/green] {message}")
