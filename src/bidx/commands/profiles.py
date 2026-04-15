"""Profile commands — agency, supplier, agencies list."""

from __future__ import annotations

import typer

profiles_app = typer.Typer(help="Agency and supplier profiles.")


@profiles_app.command()
def agency(
    name: str = typer.Argument(help="Agency name (e.g., 'DICT')."),
) -> None:
    """Show procurement profile for a government agency."""
    from zxbyd.ui import info
    info(f"Loading profile for {name}...")
    # TODO: implement
    typer.echo("Agency profile not yet implemented.")


@profiles_app.command()
def supplier(
    name: str = typer.Argument(help="Supplier name (e.g., 'ACME CORPORATION')."),
) -> None:
    """Look up a supplier's profile and award history."""
    from zxbyd.ui import info
    info(f"Loading profile for {name}...")
    # TODO: implement
    typer.echo("Supplier profile not yet implemented.")


@profiles_app.command()
def agencies(
    limit: int = typer.Option(50, "--limit", "-n", help="Max results."),
) -> None:
    """List all known procuring entities on PhilGEPS."""
    from zxbyd.ui import info
    info("Fetching agency list from PhilGEPS...")
    # TODO: implement
    typer.echo("Agencies list not yet implemented.")
