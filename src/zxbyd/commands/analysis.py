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
        enrich_notices(conn, notices, max_fetch=15)

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
            f"PHP {a['unit_price']:,.0f}",
            f"PHP {a['benchmark']:,.0f}",
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
            f"PHP {r['total']:,.0f}" if r.get("total") else "—",
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
        enrich_notices(conn, notices, max_fetch=15)

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
        abc_str = f"PHP {abc:,.0f}" if abc else "—"
        combined = c.get("total_value", 0)
        table.add_row(
            n.get("ref_no", "—"),
            n.get("title", "—")[:40],
            abc_str,
            str(c["related_count"]),
            f"PHP {combined:,.0f}" if combined else "—",
        )

    console.print(table)
    info(f"{len(candidates)} candidate(s) found")


@analysis_app.command()
def network(
    supplier_name: str = typer.Argument(help="Supplier name to analyze."),
) -> None:
    """Analyze a supplier's network — agencies, competitors."""
    from rich.table import Table
    from zxbyd.ui import info, console
    from zxbyd.data import connection
    from zxbyd.analysis import network_analysis

    info(f"Analyzing network for '{supplier_name}'...")
    with connection() as conn:
        result = network_analysis(conn, supplier_name)

    if not result.get("found"):
        console.print(f"[dim]Supplier '{supplier_name}' not found in cached awards.[/dim]")
        return

    console.print(f"\n[bold]Supplier:[/bold] {result['supplier']}")
    console.print(f"Total awards: {result['total_awards']}")
    console.print(f"Total amount: PHP {result['total_amount']:,.0f}")
    console.print(f"Avg award: PHP {result['avg_amount']:,.0f}")
    console.print(f"Agencies served: {result['agency_count']}")

    if result.get("agencies"):
        table = Table(title="Agencies Served", show_lines=True)
        table.add_column("Agency", max_width=40)
        table.add_column("Awards", justify="center")
        table.add_column("Total", justify="right", style="green")
        for a in result["agencies"]:
            table.add_row(
                a["agency"][:40],
                str(a["count"]),
                f"PHP {a['total']:,.0f}" if a.get("total") else "—",
            )
        console.print(table)

    if result.get("competitors"):
        console.print("\n[bold]Competitors (shared agencies):[/bold]")
        for c in result["competitors"]:
            console.print(f"  {c['supplier']}: {c['shared_agencies']} shared agency/agencies")


@analysis_app.command()
def watch(
    agency: str = typer.Argument(help="Agency name to watch (e.g., 'DepEd', 'DICT')."),
    pages: int = typer.Option(2, "--pages", "-p", help="Pages to scrape (per keyword)."),
    severity: str = typer.Option(
        "medium",
        "--severity",
        help="Minimum severity to flag (low/medium/high).",
    ),
    max_findings: int = typer.Option(
        5,
        "--max-findings",
        help="Cap findings per category.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON for sharing."),
    cache_only: bool = typer.Option(False, "--cache-only", help="Only use local cache."),
) -> None:
    """Comprehensive oversight report for one agency.

    Combines profile stats, price anomalies, mixed procurements,
    and supplier patterns into a single shareable report.

    Designed for journalists, advocates, and oversight workers.
    """
    import json as json_mod
    from datetime import datetime

    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    from zxbyd.ui import info, console, error
    from zxbyd.data import connection, search_notices, upsert_notice
    from zxbyd.analysis import (
        find_price_anomalies,
        is_mixed_procurement,
        extract_units,
        network_analysis,
    )
    from zxbyd import fmt_php

    sev_rank = {"low": 0, "medium": 1, "high": 2}
    if severity not in sev_rank:
        typer.echo(f"Invalid severity '{severity}'. Use low/medium/high.", err=True)
        raise typer.Exit(1)

    with connection() as conn:
        # Step 1: Optionally fetch more notices for this agency
        if not cache_only:
            info(f"Fetching recent data for '{agency}'...")
            try:
                from zxbyd.sources import search as search_source
                # Search by agency-like query to populate cache
                # Note: PhilGEPS doesn't have agency-only search, so we use a broad query
                results = search_source(agency, max_pages=pages)
                for r in results:
                    upsert_notice(conn, r)
                info(f"Cached {len(results)} notice(s).")
            except NotImplementedError:
                pass

        # Step 2: Profile stats
        stats_row = conn.execute("""
            SELECT
                COUNT(*) as notice_count,
                SUM(CASE WHEN abc IS NOT NULL AND abc > 0 THEN 1 ELSE 0 END) as with_abc,
                SUM(COALESCE(abc, 0)) as total_abc,
                AVG(CASE WHEN abc > 0 THEN abc END) as avg_abc,
                MIN(abc) FILTER (WHERE abc > 0) as min_abc,
                MAX(abc) as max_abc,
                COUNT(DISTINCT category) as category_count,
                COUNT(DISTINCT mode) as mode_count
            FROM notices
            WHERE agency LIKE ?
        """, (f"%{agency}%",)).fetchone()
        stats = dict(stats_row) if stats_row else {"notice_count": 0}

        if stats.get("notice_count", 0) == 0:
            info(f"No cached data for agency '{agency}'. Run a search first.")
            raise typer.Exit(1)

        # Step 3: Recent notices (limit for display)
        recent_rows = conn.execute("""
            SELECT ref_no, title, abc, mode, closing_date, status, agency
            FROM notices
            WHERE agency LIKE ?
            ORDER BY cached_at DESC
            LIMIT 15
        """, (f"%{agency}%",)).fetchall()
        recent = [dict(r) for r in recent_rows]

        # Step 4: Mixed procurements
        mixed_rows = []
        for r in recent:
            title = r.get("title", "") or ""
            try:
                if is_mixed_procurement(title):
                    res = extract_units(title, r.get("description", "") or "")
                    mixed_rows.append({
                        "ref_no": r["ref_no"],
                        "title": title,
                        "agency": r.get("agency", ""),
                        "items": res.items,
                        "abc": r.get("abc"),
                    })
            except Exception:
                continue

        # Step 5: Price anomalies for this agency (across categories)
        # Iterate over known categories from cached data
        categories_rows = conn.execute("""
            SELECT DISTINCT category
            FROM notices
            WHERE agency LIKE ? AND category != ''
            LIMIT 10
        """, (f"%{agency}%",)).fetchall()
        categories = [r["category"] for r in categories_rows]

        anomalies = []
        for cat in categories:
            try:
                # find_price_anomalies operates on the query string
                cat_anomalies = find_price_anomalies(conn, cat)
                for a in cat_anomalies:
                    if agency.lower() in (a.get("agency", "") or "").lower():
                        anomalies.append(a)
            except Exception:
                continue

        # Sort by overcharge
        anomalies.sort(key=lambda x: x.get("overcharge_pct", 0), reverse=True)

        # Filter by severity
        filtered_anomalies = []
        for a in anomalies[: max_findings * 2]:
            oc = a.get("overcharge_pct", 0)
            if oc >= 100:
                a_severity = "high"
            elif oc >= 30:
                a_severity = "medium"
            else:
                a_severity = "low"
            if sev_rank[a_severity] >= sev_rank[severity]:
                a["severity"] = a_severity
                filtered_anomalies.append(a)

        # Step 6: Top suppliers from cached awards
        supplier_rows = conn.execute("""
            SELECT supplier, COUNT(*) as count, SUM(amount) as total
            FROM awards
            WHERE agency LIKE ?
            GROUP BY supplier
            ORDER BY total DESC
            LIMIT 5
        """, (f"%{agency}%",)).fetchall()
        suppliers = [dict(s) for s in supplier_rows]

    if as_json:
        output = {
            "agency": agency,
            "generated_at": datetime.now().isoformat(),
            "stats": stats,
            "summary": {
                "notice_count": stats["notice_count"],
                "total_abc": stats.get("total_abc", 0) or 0,
                "price_anomalies": len(filtered_anomalies),
                "mixed_procurements": len(mixed_rows),
                "supplier_count": len(suppliers),
            },
            "price_anomalies": filtered_anomalies[:max_findings],
            "mixed_procurements": mixed_rows[:max_findings],
            "top_suppliers": suppliers,
            "recent_notices": recent[:max_findings],
        }
        typer.echo(json_mod.dumps(output, indent=2, default=str))
        return

    # Rich display
    header = Text()
    header.append(f"OVERSIGHT REPORT\n\n", style="bold white")
    header.append(f"Agency: ", style="bold")
    header.append(f"{agency}\n")
    header.append(f"Notices: ", style="bold")
    header.append(f"{stats['notice_count']} ({stats['with_abc']} with ABC)\n")
    header.append(f"Total ABC: ", style="bold")
    header.append(fmt_php(stats.get('total_abc')))
    console.print(Panel(header, border_style="cyan"))

    # Price anomalies
    if filtered_anomalies:
        table = Table(title=f"Price Anomalies ({len(filtered_anomalies)})", show_lines=True)
        table.add_column("Sev", width=3)
        table.add_column("Ref #", style="cyan", no_wrap=True)
        table.add_column("Category", max_width=15)
        table.add_column("Unit Price", justify="right")
        table.add_column("Benchmark", justify="right")
        table.add_column("Over", justify="right", style="bold red")
        for a in filtered_anomalies[:max_findings]:
            sev_icon = {"high": "[red]H[/red]", "medium": "[yellow]M[/yellow]", "low": "[dim]L[/dim]"}.get(a["severity"], "?")
            table.add_row(
                sev_icon,
                a["ref_no"],
                (a.get("unit_type") or "")[:15],
                fmt_php(a.get("unit_price")),
                fmt_php(a.get("benchmark")),
                f"+{a['overcharge_pct']:.0f}%",
            )
        console.print(table)
    else:
        console.print(f"\n[dim]No price anomalies at '{severity}' severity.[/dim]")

    # Mixed procurements
    if mixed_rows:
        table = Table(title=f"Mixed Procurements ({len(mixed_rows)})", show_lines=True)
        table.add_column("Ref #", style="cyan", no_wrap=True)
        table.add_column("Items", max_width=40)
        table.add_column("ABC", justify="right")
        for m in mixed_rows[:max_findings]:
            items_str = ", ".join(f"{i['type']} ({i['count']})" for i in (m["items"] or []))
            table.add_row(
                m["ref_no"],
                items_str[:40] or "mixed",
                fmt_php(m.get("abc")),
            )
        console.print(table)

    # Recent notices
    if recent:
        table = Table(title="Recent Notices", show_lines=True)
        table.add_column("Ref #", style="cyan", no_wrap=True)
        table.add_column("Title", max_width=35)
        table.add_column("ABC", justify="right")
        table.add_column("Mode", max_width=15)
        table.add_column("Status", max_width=12)
        for r in recent[:max_findings]:
            table.add_row(
                r["ref_no"],
                (r.get("title") or "—")[:35],
                fmt_php(r.get("abc")),
                (r.get("mode") or "—")[:15],
                (r.get("status") or "—")[:12],
            )
        console.print(table)

    # Suppliers
    if suppliers:
        table = Table(title="Top Suppliers (from awards)", show_lines=True)
        table.add_column("Supplier", max_width=40)
        table.add_column("Awards", justify="center")
        table.add_column("Total", justify="right")
        for s in suppliers:
            table.add_row(
                (s["supplier"] or "—")[:40],
                str(s["count"]),
                fmt_php(s.get("total")),
            )
        console.print(table)

    # Disclaimer
    console.print(
        "\n[dim]Note: All signals are based on cached notices and awards. "
        "Verify findings against official PhilGEPS records. "
        "Mixed procurements may include genuine bundle deals. "
        "High unit prices may include installation, warranty, or accessories.[/dim]"
    )
