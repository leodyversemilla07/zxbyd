"""Search and detail commands."""

from __future__ import annotations

import typer

search_app = typer.Typer(help="Search procurement notices.")


@search_app.command()
def notices(
    query: str = typer.Argument(help="Search keywords (e.g., 'laptop', 'server')."),
    pages: int = typer.Option(1, "--pages", "-p", help="Pages to scrape (20 results/page)."),
    agency: str | None = typer.Option(None, "--agency", "-a", help="Filter by agency name."),
    detail: bool = typer.Option(False, "--detail", "-d", help="Fetch full details for each result."),
    cache_only: bool = typer.Option(False, "--cache-only", help="Only search local cache (no scraping)."),
) -> None:
    """Search procurement notices by keyword."""
    from zxbyd.ui import info
    info(f'Searching PhilGEPS for "{query}"...')
    # TODO: implement search
    typer.echo("Search not yet implemented.")


@search_app.command()
def recent(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of recent notices."),
) -> None:
    """Show recent procurement notices."""
    from zxbyd.ui import info
    info("Fetching recent notices...")
    # TODO: implement
    typer.echo("Not yet implemented.")
