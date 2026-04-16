"""Report command — generates shareable procurement anomaly reports."""

from __future__ import annotations

from datetime import datetime

import typer


def report(
    query: str = typer.Argument(help="Category to report on (e.g., 'laptop', 'desktop', 'server')."),
    pages: int = typer.Option(2, "--pages", "-p", help="Pages to scrape."),
    threshold: int = typer.Option(20, "--threshold", "-t", help="Overcharge %% to flag."),
    top: int = typer.Option(10, "--top", "-n", help="Max findings to show."),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON."),
    cache_only: bool = typer.Option(False, "--cache-only", help="Only search local cache."),
) -> None:
    """Generate a procurement anomaly report for a category."""
    import json as json_mod

    from zxbyd.ui import info, console
    from zxbyd.data import connection, search_notices, upsert_notice
    from zxbyd.analysis import find_price_anomalies
    from zxbyd.commands.analysis import _enrich_notices

    with connection() as conn:
        # Step 1: Search
        if not cache_only:
            info(f"Searching PhilGEPS for '{query}'...")
            try:
                from zxbyd.sources import search as search_source
                results = search_source(query, max_pages=pages)
                for r in results:
                    upsert_notice(conn, r)
                info(f"Cached {len(results)} notice(s).")
            except NotImplementedError:
                pass

        # Step 2: Enrich with details
        notices = search_notices(conn, query=query)
        _enrich_notices(conn, notices, max_fetch=15)

        # Re-read after enrichment
        notices = search_notices(conn, query=query)
        enriched = [n for n in notices if n.get("abc") and n["abc"] > 0]

        # Step 3: Price anomalies
        anomalies = find_price_anomalies(conn, query)
        anomalies = [a for a in anomalies if a["overcharge_pct"] >= threshold]
        anomalies.sort(key=lambda x: x["overcharge_pct"], reverse=True)

        # Step 4: Compute stats
        total_notices = len(notices)
        total_enriched = len(enriched)
        total_abc = sum(n["abc"] for n in enriched if n.get("abc"))

        # Group by agency
        agency_counts: dict[str, int] = {}
        agency_abc: dict[str, float] = {}
        for n in enriched:
            ag = n.get("agency", "Unknown") or "Unknown"
            agency_counts[ag] = agency_counts.get(ag, 0) + 1
            agency_abc[ag] = agency_abc.get(ag, 0) + (n.get("abc") or 0)

    # Step 5: Output
    if as_json:
        output = {
            "query": query,
            "generated_at": datetime.now().isoformat(),
            "stats": {
                "total_notices": total_notices,
                "enriched_with_abc": total_enriched,
                "total_abc": total_abc,
                "anomalies_found": len(anomalies),
                "threshold_pct": threshold,
            },
            "anomalies": [
                {
                    "ref_no": a["ref_no"],
                    "agency": a["agency"],
                    "title": a["title"],
                    "abc": a["abc"],
                    "unit_count": a["unit_count"],
                    "unit_type": a["unit_type"],
                    "unit_price": a["unit_price"],
                    "benchmark": a["benchmark"],
                    "overcharge_pct": a["overcharge_pct"],
                }
                for a in anomalies[:top]
            ],
            "top_agencies": sorted(agency_abc.items(), key=lambda x: x[1], reverse=True)[:10],
        }
        typer.echo(json_mod.dumps(output, indent=2, default=str))
        return

    # Rich report
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    # Header
    header = Text()
    header.append(f"PROCUREMENT ANOMALY REPORT\n", style="bold white")
    header.append(f"Category: ", style="bold")
    header.append(f"{query}\n")
    header.append(f"Generated: ", style="bold")
    header.append(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    header.append(f"Notices: ", style="bold")
    header.append(f"{total_notices} found, {total_enriched} with ABC data\n")
    header.append(f"Total ABC: ", style="bold")
    header.append(f"₱{total_abc:,.0f}")
    console.print(Panel(header, border_style="cyan"))

    if not anomalies:
        console.print(f"\n[dim]No price anomalies above {threshold}% threshold.[/dim]")
        if total_enriched < 3:
            console.print("[dim]Tip: Try --pages 3 for more coverage.[/dim]")
        return

    # Anomaly table
    table = Table(title=f"Price Anomalies ({len(anomalies)} found)", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Ref #", style="cyan", no_wrap=True)
    table.add_column("Agency", max_width=25)
    table.add_column("Title", max_width=35)
    table.add_column("ABC", justify="right", style="green")
    table.add_column("Units", justify="center")
    table.add_column("Unit Price", justify="right", style="red")
    table.add_column("Benchmark", justify="right")
    table.add_column("Over", justify="right", style="bold red")

    for i, a in enumerate(anomalies[:top], 1):
        table.add_row(
            str(i),
            a["ref_no"],
            (a["agency"] or "—")[:25],
            (a["title"] or "—")[:35],
            f"₱{a['abc']:,.0f}",
            str(a["unit_count"]),
            f"₱{a['unit_price']:,.0f}",
            f"₱{a['benchmark']:,.0f}",
            f"+{a['overcharge_pct']:.0f}%",
        )

    console.print(table)

    # Evidence section
    console.print(f"\n[bold]Evidence:[/bold]")
    for i, a in enumerate(anomalies[:top], 1):
        console.print(
            f"  [{i}] {a['agency']}: "
            f"₱{a['abc']:,.0f} for {a['unit_count']} {a['unit_type']}(s) = "
            f"₱{a['unit_price']:,.0f}/unit "
            f"(benchmark ₱{a['benchmark']:,.0f}, +{a['overcharge_pct']:.0f}%)"
        )
        console.print(
            f"      Ref: https://notices.philgeps.gov.ph/GEPSNONPILOT/Tender/"
            f"PrintableBidNoticeAbstractUI.aspx?refid={a['ref_no']}"
        )

    # Top agencies
    console.print(f"\n[bold]Top Agencies by ABC:[/bold]")
    top_agencies = sorted(agency_abc.items(), key=lambda x: x[1], reverse=True)[:5]
    for ag, abc in top_agencies:
        count = agency_counts.get(ag, 0)
        console.print(f"  {ag}: ₱{abc:,.0f} ({count} notice(s))")

    # Disclaimer
    console.print(
        "\n[dim]Note: Unit prices are computed from ABC / unit count extracted from "
        "notice text. Mixed-item procurements may show inflated prices. "
        "Check individual notices for exact specs and justification.[/dim]"
    )
