"""Analysis commands — probe, overprice, repeat, split, network."""

from __future__ import annotations

import json as json_mod

import typer

analysis_app = typer.Typer(help="Anomaly detection and probing.")


def _enrich_notices(conn, notices: list[dict], max_fetch: int = 10) -> int:
    """Fetch details for notices missing ABC data.

    Returns count of notices enriched.
    """
    from zxbyd.ui import info
    from zxbyd.sources import get_notice_detail
    from zxbyd.data import upsert_notice

    to_fetch = [n for n in notices if not n.get("abc") and n.get("ref_no")]
    to_fetch = to_fetch[:max_fetch]

    if not to_fetch:
        return 0

    info(f"Fetching details for {len(to_fetch)} notice(s)...")
    enriched = 0
    for n in to_fetch:
        ref = n["ref_no"]
        try:
            detail = get_notice_detail(ref)
            if detail.get("abc"):
                detail["ref_no"] = ref  # ensure ref_no is present
                upsert_notice(conn, detail)
                enriched += 1
        except Exception:
            continue

    if enriched:
        info(f"Enriched {enriched} notice(s) with ABC data.")
    return enriched


@analysis_app.command()
def probe(
    query: str = typer.Argument(help="Search keywords to probe."),
    pages: int = typer.Option(1, "--pages", "-p", help="Pages to scrape."),
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
    from zxbyd.ui import info, console, error
    from zxbyd.data import connection, search_notices, upsert_notice
    from zxbyd.analysis import probe as probe_fn

    with connection() as conn:
        # If not cache_only, search first to populate cache
        if not cache_only:
            info(f'Searching PhilGEPS for "{query}"...')
            try:
                from zxbyd.sources import search as search_source
                results = search_source(query, max_pages=pages)
                for r in results:
                    upsert_notice(conn, r)
                info(f"Cached {len(results)} notice(s).")
            except NotImplementedError:
                error("Scraper not implemented. Use --cache-only or run search first.")
                raise typer.Exit(1)

        # Get cached notices and enrich with details
        notices = search_notices(conn, query=query)
        _enrich_notices(conn, notices, max_fetch=10)

        info(f'Probing "{query}"...')
        result = probe_fn(conn, query, min_confidence, max_findings)

    if as_json:
        output = {
            "query": result.query,
            "summary": result.summary,
            "data_quality": result.data_quality,
            "findings": [
                {
                    "reason_code": f.reason_code,
                    "title": f.title,
                    "description": f.description,
                    "confidence": f.confidence.value,
                    "evidence": f.evidence,
                    "false_positive_note": f.false_positive_note,
                }
                for f in result.findings
            ],
        }
        typer.echo(json_mod.dumps(output, indent=2))
        return

    # Rich display
    console.print(f"\n[bold]Probe: {result.query}[/bold]")
    console.print(f"Data quality: {result.data_quality}")
    console.print(f"Summary: {result.summary}\n")

    if not result.findings:
        console.print("[dim]No findings.[/dim]")
        return

    for i, finding in enumerate(result.findings, 1):
        conf_color = {
            "high": "red",
            "medium": "yellow",
            "low": "dim",
        }.get(finding.confidence.value, "white")

        console.print(
            f"[{conf_color}][{finding.confidence.value.upper()}][/{conf_color}] "
            f"[bold]{finding.reason_code}[/bold]: {finding.title}"
        )
        console.print(f"  {finding.description}")

        if why:
            if finding.evidence:
                console.print("  [dim]Evidence:[/dim]")
                for ev in finding.evidence:
                    console.print(f"    - {ev}")
            if finding.false_positive_note:
                console.print(f"  [dim italic]Note: {finding.false_positive_note}[/dim italic]")
        console.print()


@analysis_app.command()
def overprice(
    category: str = typer.Argument(default="", help="Category to compare (e.g., 'laptop')."),
    pages: int = typer.Option(2, "--pages", "-p", help="Pages to scrape."),
    threshold: int = typer.Option(50, "--threshold", "-t", help="Price spread %% to flag."),
    cache_only: bool = typer.Option(False, "--cache-only", help="Only search local cache."),
) -> None:
    """Detect pricing anomalies across agencies."""
    from zxbyd.ui import info, console
    from zxbyd.data import connection, search_notices, upsert_notice
    from zxbyd.analysis import find_price_anomalies

    if not category:
        info("Provide a category to analyze (e.g., 'laptop', 'desktop', 'server').")
        raise typer.Exit(1)

    with connection() as conn:
        if not cache_only:
            info(f"Searching PhilGEPS for '{category}'...")
            try:
                from zxbyd.sources import search as search_source
                results = search_source(category, max_pages=pages)
                for r in results:
                    upsert_notice(conn, r)
                info(f"Cached {len(results)} notice(s).")
            except NotImplementedError:
                pass

        # Enrich with details
        notices = search_notices(conn, query=category)
        _enrich_notices(conn, notices, max_fetch=15)

        info(f"Analyzing prices for '{category}'...")
        anomalies = find_price_anomalies(conn, category)

    if not anomalies:
        console.print("[dim]No price anomalies found.[/dim]")
        return

    # Filter by threshold
    anomalies = [a for a in anomalies if a["overcharge_pct"] >= threshold]

    if not anomalies:
        console.print(f"[dim]No anomalies above {threshold}% threshold.[/dim]")
        return

    from rich.table import Table
    table = Table(title=f"Price Anomalies — '{category}'", show_lines=True)
    table.add_column("Ref #", style="cyan", no_wrap=True)
    table.add_column("Agency", max_width=30)
    table.add_column("Unit Price", justify="right", style="red")
    table.add_column("Benchmark", justify="right", style="green")
    table.add_column("Overcharge", justify="right", style="bold red")
    table.add_column("Units", justify="center")

    for a in sorted(anomalies, key=lambda x: x["overcharge_pct"], reverse=True):
        table.add_row(
            a["ref_no"],
            a["agency"][:30],
            f"₱{a['unit_price']:,.0f}",
            f"₱{a['benchmark']:,.0f}",
            f"+{a['overcharge_pct']:.0f}%",
            str(a["unit_count"]),
        )

    console.print(table)
    info(f"{len(anomalies)} anomaly/anomalies above {threshold}% threshold")


@analysis_app.command()
def repeat(
    min_count: int = typer.Option(3, "--min-count", "-n", help="Minimum award count to flag."),
) -> None:
    """Find suppliers with high award frequency (potential red flags)."""
    from zxbyd.ui import info, console
    from zxbyd.data import connection
    from zxbyd.analysis import find_repeat_awardees

    info("Analyzing repeat awardees...")
    with connection() as conn:
        results = find_repeat_awardees(conn, min_count)

    if not results:
        console.print("[dim]No repeat awardees found (need award data).[/dim]")
        return

    from rich.table import Table
    table = Table(title="Repeat Awardees", show_lines=True)
    table.add_column("Supplier", max_width=40)
    table.add_column("Awards", justify="center")
    table.add_column("Total Amount", justify="right", style="green")
    table.add_column("Agencies", max_width=30)

    for r in results:
        table.add_row(
            r["supplier"][:40],
            str(r["count"]),
            f"₱{r['total']:,.0f}" if r.get("total") else "—",
            (r.get("agencies", "") or "")[:30],
        )

    console.print(table)


@analysis_app.command("split")
def split_contracts(
    agency: str = typer.Argument(help="Agency name to analyze."),
    pages: int = typer.Option(2, "--pages", "-p", help="Pages to scrape."),
    gap_days: int = typer.Option(30, "--gap-days", help="Max days between related contracts."),
    cache_only: bool = typer.Option(False, "--cache-only", help="Only search local cache."),
) -> None:
    """Detect potential contract splitting for an agency."""
    from zxbyd.ui import info, console
    from zxbyd.data import connection, upsert_notice
    from zxbyd.analysis import detect_split_contracts

    with connection() as conn:
        if not cache_only:
            info(f"Searching for '{agency}'...")
            try:
                from zxbyd.sources import search as search_source
                results = search_source(agency, max_pages=pages)
                for r in results:
                    upsert_notice(conn, r)
                info(f"Cached {len(results)} notice(s).")
            except NotImplementedError:
                pass

        # Enrich with details
        from zxbyd.data import search_notices
        notices = search_notices(conn, query=agency)
        _enrich_notices(conn, notices, max_fetch=15)

        info(f"Analyzing {agency} for contract splitting...")
        candidates = detect_split_contracts(conn, agency, gap_days)

    if not candidates:
        console.print(f"[dim]No split-contract candidates found for '{agency}'.[/dim]")
        return

    from rich.table import Table
    table = Table(title=f"Split Contract Candidates — '{agency}'", show_lines=True)
    table.add_column("Ref #", style="cyan", no_wrap=True)
    table.add_column("Title", max_width=40)
    table.add_column("ABC", justify="right", style="green")
    table.add_column("Related", justify="center")
    table.add_column("Combined Value", justify="right", style="red")

    for c in candidates:
        n = c["notice"]
        abc = n.get("abc")
        abc_str = f"₱{abc:,.0f}" if abc else "—"
        combined = c.get("total_value", 0)
        table.add_row(
            n.get("ref_no", "—"),
            n.get("title", "—")[:40],
            abc_str,
            str(c["related_count"]),
            f"₱{combined:,.0f}" if combined else "—",
        )

    console.print(table)
    info(f"{len(candidates)} candidate(s) found")


@analysis_app.command()
def network(
    supplier_name: str = typer.Argument(help="Supplier name to analyze."),
) -> None:
    """Analyze a supplier's network — agencies, competitors."""
    from zxbyd.ui import info
    info(f"Analyzing network for {supplier_name}...")
    typer.echo("Network analysis not yet implemented (requires award data).")
