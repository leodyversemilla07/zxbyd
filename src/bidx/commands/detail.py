"""Detail command."""

from __future__ import annotations

import typer

detail_app = typer.Typer(help="Fetch notice details.")


@detail_app.command()
def show(
    ref_id: str = typer.Argument(help="PhilGEPS reference number (e.g., 12905086)."),
    force: bool = typer.Option(False, "--force", "-f", help="Re-fetch even if cached."),
) -> None:
    """Fetch full details for a procurement notice by reference ID."""
    from zxbyd.ui.display import info
    info(f"Fetching details for {ref_id}...")
    # TODO: implement
    typer.echo("Detail not yet implemented.")
