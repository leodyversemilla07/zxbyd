"""Awards commands."""

from __future__ import annotations

import typer

awards_app = typer.Typer(help="List contract awards.")


@awards_app.command()
def list(
    agency: str | None = typer.Option(None, "--agency", "-a", help="Filter by agency name."),
    supplier: str | None = typer.Option(None, "--supplier", "-s", help="Filter by supplier name."),
    limit: int = typer.Option(50, "--limit", "-n", help="Max results."),
    cache_only: bool = typer.Option(False, "--cache-only", help="Only search local cache."),
) -> None:
    """List recent contract awards."""
    from zxbyd.ui import info
    info("Fetching recent awards from PhilGEPS...")
    # TODO: implement
    typer.echo("Awards not yet implemented.")
