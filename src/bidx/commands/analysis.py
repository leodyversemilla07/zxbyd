"""Analysis commands — probe, overprice, repeat, split, network."""

from __future__ import annotations

import json as json_mod

import typer

analysis_app = typer.Typer(help="Anomaly detection and probing.")


@analysis_app.command()
def probe(
    query: str = typer.Argument(help="Search keywords to probe."),
    why: bool = typer.Option(False, "--why", help="Show evidence and caveats."),
    min_confidence: str = typer.Option(
        "low",
        "--min-confidence",
        help="Minimum confidence filter (low/medium/high).",
    ),
    max_findings: int = typer.Option(
        10,
        "--max-findings",
        help="Cap number of findings.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON."),
    cache_only: bool = typer.Option(False, "--cache-only", help="Only use local cache."),
) -> None:
    """Probe procurement data with summary-first, reason-coded risk findings."""
    from zxbyd.ui.display import info
    info(f'Probing "{query}"...')
    # TODO: implement
    typer.echo("Probe not yet implemented.")


@analysis_app.command()
def overprice(
    category: str = typer.Argument(default="", help="Category to compare (e.g., 'laptop')."),
    threshold: int = typer.Option(200, "--threshold", "-t", help="Price spread %% to flag."),
) -> None:
    """Detect pricing anomalies across agencies."""
    from zxbyd.ui.display import info
    info(f"Analyzing prices for '{category}'...")
    # TODO: implement
    typer.echo("Overprice detection not yet implemented.")


@analysis_app.command()
def repeat(
    min_count: int = typer.Option(3, "--min-count", "-n", help="Minimum award count to flag."),
) -> None:
    """Find suppliers with high award frequency (potential red flags)."""
    from zxbyd.ui.display import info
    info("Analyzing repeat awardees...")
    # TODO: implement
    typer.echo("Repeat awardee detection not yet implemented.")


@analysis_app.command("split")
def split_contracts(
    agency: str = typer.Argument(help="Agency name to analyze."),
    gap_days: int = typer.Option(30, "--gap-days", help="Max days between related contracts."),
) -> None:
    """Detect potential contract splitting for an agency."""
    from zxbyd.ui.display import info
    info(f"Analyzing {agency} for contract splitting...")
    # TODO: implement
    typer.echo("Split contract detection not yet implemented.")


@analysis_app.command()
def network(
    supplier_name: str = typer.Argument(help="Supplier name to analyze."),
) -> None:
    """Analyze a supplier's network — agencies, competitors."""
    from zxbyd.ui.display import info
    info(f"Analyzing network for {supplier_name}...")
    # TODO: implement
    typer.echo("Network analysis not yet implemented.")
