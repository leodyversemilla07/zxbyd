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


def _render_watch_markdown(
    agency: str,
    stats: dict,
    anomalies: list[dict],
    mixed: list[dict],
    suppliers: list[dict],
    recent: list[dict],
    severity: str,
) -> str:
    """Render an oversight report as a shareable Markdown document.

    Designed for journalists and oversight workers — fills the gap between
    terminal Rich output (great for ad-hoc inspection) and JSON (great for
    pipelines) but inconvenient for human-readable sharing.
    """
    from datetime import datetime

    from zxbyd import fmt_php

    lines: list[str] = []
    a = lines.append

    a(f"# Oversight Report — {agency}")
    a("")
    a(f"_Generated by zxbyd on {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    a("")

    # Summary
    total_abc = stats.get("total_abc") or 0
    a("## At-a-Glance")
    a("")
    a(f"| Metric | Value |")
    a(f"|---|---|")
    a(f"| Notices cached | {stats.get('notice_count', 0):,} ({stats.get('with_abc', 0):,} with ABC) |")
    a(f"| Total ABC | {fmt_php(total_abc)} |")
    a(f"| Avg ABC | {fmt_php(stats.get('avg_abc') or 0)} |")
    a(f"| ABC range | {fmt_php(stats.get('min_abc') or 0)} — {fmt_php(stats.get('max_abc') or 0)} |")
    a(f"| Categories | {stats.get('category_count', 0):,} |")
    a(f"| Procurement modes | {stats.get('mode_count', 0):,} |")
    a(f"| Severity filter | `{severity}` and above |")
    a("")

    # Price anomalies
    a(f"## Price Anomalies ({len(anomalies)})")
    a("")
    if not anomalies:
        a(f"_No price anomalies at `{severity}` severity._")
        a("")
    else:
        a("| Sev | Ref # | Category | Unit Price | Benchmark | Over |")
        a("|-----|-------|----------|------------|-----------|------|")
        for x in anomalies:
            sev_label = x.get("severity", "?").upper()
            a(
                f"| {sev_label} | `{x.get('ref_no', '—')}` "
                f"| {x.get('unit_type') or '—'} "
                f"| {fmt_php(x.get('unit_price'))} "
                f"| {fmt_php(x.get('benchmark'))} "
                f"| **+{x.get('overcharge_pct', 0):.0f}%** |"
            )
        a("")

    # Mixed procurements
    a(f"## Mixed Procurements ({len(mixed)})")
    a("")
    if not mixed:
        a("_No mixed procurements detected._")
        a("")
    else:
        a("| Ref # | Items | Estimated ABC |")
        a("|-------|-------|---------------|")
        for m in mixed:
            items = ", ".join(f"{i['type']} ({i['count']})" for i in (m.get("items") or [])) or "mixed"
            a(f"| `{m['ref_no']}` | {items} | {fmt_php(m.get('abc'))} |")
        a("")

    # Recent notices
    a(f"## Recent Notices ({len(recent)})")
    a("")
    if not recent:
        a("_No recent notices._")
        a("")
    else:
        a("| Ref # | Title | ABC | Mode | Closing | Status |")
        a("|-------|-------|-----|------|---------|--------|")
        for r in recent:
            title = (r.get("title") or "—").replace("|", "\\|")[:80]
            a(
                f"| `{r.get('ref_no', '—')}` "
                f"| {title} "
                f"| {fmt_php(r.get('abc'))} "
                f"| {r.get('mode') or '—'} "
                f"| {r.get('closing_date') or '—'} "
                f"| {r.get('status') or '—'} |"
            )
        a("")

    # Top suppliers
    a(f"## Top Suppliers ({len(suppliers)})")
    a("")
    if not suppliers:
        a("_No cached awards for this agency yet. Import awards with `zxbyd awards import`._")
        a("")
    else:
        a("| Supplier | Awards | Total |")
        a("|----------|--------|-------|")
        for s in suppliers:
            supplier_name = s.get("supplier") or "—"
            a(
                f"| {supplier_name} "
                f"| {s.get('count', 0)} "
                f"| {fmt_php(s.get('total'))} |"
            )
        a("")

    # Methodology / disclaimer
    a("## Methodology")
    a("")
    a("- **Price anomalies** compare unit prices (ABC ÷ units) against `BENCHMARKS` — conservative PHP market prices for common categories.")
    a("- **Mixed procurements** detect titles combining multiple item types (`/`, `AND`, digit+ noun) per item-count.")
    a("- **Repeat suppliers** are ranked by total award amount for this agency in cached data.")
    a("- Signals are heuristics only. Verify against official PhilGEPS records before publishing.")
    a("")

    return "\n".join(lines)


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
    markdown: bool = typer.Option(
        False,
        "--markdown",
        help="Output as Markdown (shareable, linkable, fits newsroom workflows).",
    ),
    output: str = typer.Option(
        None,
        "-o", "--output",
        help="Write report to this file path (default: stdout).",
    ),
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

    if markdown:
        md_text = _render_watch_markdown(
            agency=agency,
            stats=stats,
            anomalies=filtered_anomalies[:max_findings],
            mixed=mixed_rows[:max_findings],
            suppliers=suppliers,
            recent=recent[:max_findings],
            severity=severity,
        )
        if output:
            from pathlib import Path

            out_path = Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(md_text, encoding="utf-8")
            typer.echo(f"Wrote report to {out_path} ({out_path.stat().st_size:,} bytes)")
        else:
            # Write bytes directly to stdout, bypassing the TTY's cp1252 layer.
            import sys as _sys

            _sys.stdout.buffer.write(md_text.encode("utf-8", errors="replace"))
            _sys.stdout.buffer.write(b"\n")
            _sys.stdout.buffer.flush()
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


def _gather_compare_data(conn, agencies: list[str]) -> list[dict]:
    """Gather matching stats for each agency.

    Returns one dict per agency with: agency, stats (notice count, ABC),
    top_suppliers list, supplier_names set, and just the shared-supplier
    info across all agencies in the comparison.
    """
    out = []
    for agency in agencies:
        row = conn.execute(
            """
            SELECT COUNT(*) as notice_count,
                   SUM(CASE WHEN abc IS NOT NULL AND abc > 0 THEN 1 ELSE 0 END) as with_abc,
                   SUM(COALESCE(abc, 0)) as total_abc,
                   AVG(CASE WHEN abc > 0 THEN abc END) as avg_abc,
                   MIN(abc) FILTER (WHERE abc > 0) as min_abc,
                   MAX(abc) as max_abc,
                   COUNT(DISTINCT category) as category_count,
                   COUNT(DISTINCT mode) as mode_count
            FROM notices
            WHERE agency LIKE ?
            """,
            (f"%{agency}%",),
        ).fetchone()
        stats = dict(row) if row else {"notice_count": 0}
        stats["normalized"] = agency

        supplier_rows = conn.execute(
            """
            SELECT supplier, COUNT(*) as count, SUM(amount) as total
            FROM awards
            WHERE agency LIKE ?
            GROUP BY supplier
            ORDER BY total DESC NULLS LAST
            LIMIT 50
            """,
            (f"%{agency}%",),
        ).fetchall()
        suppliers = [dict(s) for s in supplier_rows]
        supplier_names = {(s.get("supplier") or "").upper() for s in suppliers if s.get("supplier")}

        out.append({
            "agency": agency,
            "stats": stats,
            "top_suppliers": suppliers,
            "supplier_names": supplier_names,
        })

    # Compute shared suppliers across agencies
    if len(out) >= 2:
        all_per_agency = [entry["supplier_names"] for entry in out]
        # Suppliers that appear in 2+ agency sets
        shared = set()
        for i, names_i in enumerate(all_per_agency):
            for j, names_j in enumerate(all_per_agency):
                if i < j:
                    shared |= (names_i & names_j)
        # Annotate each entry
        for entry in out:
            top = entry["top_suppliers"]
            shared_here = [
                {
                    "supplier": s.get("supplier"),
                    "count": s.get("count", 0),
                    "total": s.get("total", 0),
                }
                for s in top
                if (s.get("supplier") or "").upper() in shared
            ]
            entry["shared_suppliers"] = shared_here

    return out


def _render_compare_markdown(
    agencies: list[str],
    data: list[dict],
    top_n: int,
) -> str:
    """Render multi-agency comparison as Markdown."""
    from datetime import datetime

    from zxbyd import fmt_php

    lines: list[str] = []
    a = lines.append

    a(f"# Procurement Comparison — Across Agencies")
    a("")
    a(f"**{len(agencies)} agencies:** " + ", ".join(f"`{ag}`" for ag in agencies))
    a("")
    a(f"_Generated by zxbyd on {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    a("")

    # Side-by-side at-a-glance
    a("## At-a-Glance (Side-by-Side)")
    a("")
    header_cols = ["Metric"] + agencies
    a("| " + " | ".join(header_cols) + " |")
    a("|" + "|".join("---" for _ in header_cols) + "|")

    rows_to_show = [
        ("Notices cached", lambda s: f"{s.get('notice_count', 0):,}"),
        ("With ABC",       lambda s: f"{s.get('with_abc', 0):,}"),
        ("Total ABC",      lambda s: fmt_php(s.get('total_abc') or 0)),
        ("Avg ABC",        lambda s: fmt_php(s.get('avg_abc') or 0)),
        ("Min ABC",        lambda s: fmt_php(s.get('min_abc') or 0)),
        ("Max ABC",        lambda s: fmt_php(s.get('max_abc') or 0)),
        ("Categories",     lambda s: f"{s.get('category_count', 0):,}"),
        ("Procurement modes", lambda s: f"{s.get('mode_count', 0):,}"),
    ]
    for label, project in rows_to_show:
        cells = [label]
        for entry in data:
            cells.append(project(entry["stats"]))
        a("| " + " | ".join(cells) + " |")
    a("")

    # Per-agency top suppliers
    a("## Top Suppliers per Agency")
    a("")
    for entry in data:
        a(f"### {entry['agency']}")
        a("")
        if not entry["top_suppliers"]:
            a("_No cached awards._")
            a("")
            continue
        a("| Supplier | Awards | Total |")
        a("|----------|--------|-------|")
        for s in entry["top_suppliers"][:top_n]:
            name = (s.get("supplier") or "—").replace("|", "\\|")
            total_str = fmt_php(s.get("total"))
            a(f"| {name} | {s.get('count', 0)} | {total_str} |")
        a("")

    # Cross-agency supplier overlap (only meaningful when >= 2 agencies with awards)
    multi = [entry for entry in data if entry.get("shared_suppliers")]
    if multi:
        a("## Cross-Agency Supplier Overlap")
        a("")
        a("Suppliers winning awards at **two or more** of the listed agencies.")
        a("When the same supplier wins across multiple agencies, it can indicate ")
        a("monopolistic procurement — worth investigating.")
        a("")
        for entry in multi:
            ss = entry["shared_suppliers"]
            if not ss:
                continue
            a(f"### {entry['agency']}")
            a("")
            a("| Supplier | Awards here | Total |")
            a("|----------|-------------|-------|")
            for s in ss[:top_n]:
                name = (s.get("supplier") or "—").replace("|", "\\|")
                total_str = fmt_php(s.get("total"))
                a(f"| {name} | {s.get('count', 0)} | {total_str} |")
            a("")

    a("## Methodology")
    a("")
    a("- Each agency is matched by `LIKE '%<agency>%'` on cached notices and awards.")
    a("- ABC values reflect cached records only; some notices have null/missing ABC.")
    a("- Cross-agency overlap flags suppliers who appear at **2 or more** agencies in this comparison set")
    a("  — a single supplier winning the most contracts at many agencies is correlated with procurement collusion patterns.")
    a("- Use `zxbyd analysis watch <agency>` to drill into any single agency's anomalies.")
    a("")

    return "\n".join(lines)


@analysis_app.command()
def compare(
    agencies: list[str] = typer.Argument(
        ..., help="Agency names to compare (2-10). e.g. DepEd DICT DBM"
    ),
    pages: int = typer.Option(2, "--pages", "-p", help="Pages to scrape (per agency)."),
    top_n: int = typer.Option(
        5, "--top", "-n", help="Top suppliers per agency to list."
    ),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON."),
    markdown: bool = typer.Option(
        False, "--markdown", help="Output as Markdown (shareable)."
    ),
    output: str = typer.Option(
        None, "-o", "--output", help="Write report to file path."
    ),
    cache_only: bool = typer.Option(False, "--cache-only", help="Only use local cache."),
) -> None:
    """Compare procurement patterns across multiple agencies.

    Side-by-side view of notice counts, ABC totals, and top suppliers.
    Flags suppliers who appear across multiple agencies — a signal
    worth investigating in Philippine procurement oversight.

    Example:
        zxbyd analysis compare "DICT" "DBM" "DepEd"
        zxbyd analysis compare PNP CHED DOH --markdown
    """
    import json as json_mod

    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    from zxbyd.ui import info, console
    from zxbyd.data import connection, upsert_notice
    from zxbyd import fmt_php

    if not (2 <= len(agencies) <= 10):
        typer.echo(
            f"Please supply 2-10 agencies (got {len(agencies)}).",
            err=True,
        )
        raise typer.Exit(1)

    with connection() as conn:
        # Optionally fetch more data for each agency
        if not cache_only:
            for agency in agencies:
                info(f'Fetching data for "{agency}"...')
                try:
                    from zxbyd.sources import search as search_source
                    results = search_source(agency, max_pages=pages)
                    for r in results:
                        upsert_notice(conn, r)
                except NotImplementedError:
                    pass

        data = _gather_compare_data(conn, agencies)

        # Check at least one agency has data
        with_data = [d for d in data if d["stats"].get("notice_count", 0) > 0]
        if not with_data:
            info(f"No cached data for any of: {agencies}. Run a search first.")
            raise typer.Exit(1)

    if as_json:
        out = {
            "agencies": agencies,
            "generated_at": __import__("datetime").datetime.now().isoformat(),
            "agencies_data": [
                {
                    "agency": entry["agency"],
                    "stats": entry["stats"],
                    "top_suppliers": entry["top_suppliers"][:top_n],
                    "shared_suppliers": entry.get("shared_suppliers", [])[:top_n],
                }
                for entry in data
            ],
        }
        typer.echo(json_mod.dumps(out, indent=2, default=str))
        return

    if markdown:
        md_text = _render_compare_markdown(agencies, data, top_n=top_n)
        if output:
            from pathlib import Path
            out_path = Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(md_text, encoding="utf-8")
            typer.echo(f"Wrote comparison to {out_path} ({out_path.stat().st_size:,} bytes)")
        else:
            import sys as _sys
            _sys.stdout.buffer.write(md_text.encode("utf-8", errors="replace"))
            _sys.stdout.buffer.write(b"\n")
            _sys.stdout.buffer.flush()
        return

    # Rich display
    header = Text()
    header.append("PROCUREMENT COMPARISON\n\n", style="bold white")
    header.append(f"{len(agencies)} agencies: ", style="bold")
    header.append(", ".join(f"{ag}" for ag in agencies) + "\n")
    console.print(Panel(header, border_style="cyan"))

    # At-a-glance table
    table = Table(title="At a Glance", show_lines=True)
    row_data = [("Agency", lambda e: e["agency"]),
                ("Notices", lambda e: str(e["stats"].get("notice_count", 0))),
                ("With ABC", lambda e: str(e["stats"].get("with_abc", 0))),
                ("Total ABC", lambda e: fmt_php(e["stats"].get("total_abc"))),
                ("Suppliers", lambda e: str(len(e.get("top_suppliers", [])))),]
    for label, project in row_data:
        if label == "Agency":
            table.add_column(label, style="cyan", max_width=30)
        elif label == "Total ABC":
            table.add_column(label, justify="right", style="green")
        else:
            table.add_column(label, justify="center")
    for entry in data:
        table.add_row(*[project(entry) for _, project in row_data])
    console.print(table)

    # Cross-agency supplier overlap
    multi = [e for e in data if e.get("shared_suppliers")]
    if multi:
        table = Table(title="Cross-Agency Supplier Overlap", show_lines=True)
        table.add_column("Agency", style="cyan", max_width=30)
        table.add_column("Supplier", max_width=35)
        table.add_column("Awards", justify="center")
        table.add_column("Total", justify="right", style="green")
        for entry in multi:
            for s in entry["shared_suppliers"][:top_n]:
                table.add_row(
                    entry["agency"][:30],
                    (s["supplier"] or "—")[:35],
                    str(s.get("count", 0)),
                    fmt_php(s.get("total")),
                )
        console.print(table)

    # Per-agency top suppliers
    for entry in data:
        if not entry["top_suppliers"]:
            continue
        table = Table(title=f"Top Suppliers — {entry['agency']}", show_lines=True)
        table.add_column("Supplier", max_width=40)
        table.add_column("Awards", justify="center")
        table.add_column("Total", justify="right", style="green")
        for s in entry["top_suppliers"][:top_n]:
            table.add_row(
                (s.get("supplier") or "—")[:40],
                str(s.get("count", 0)),
                fmt_php(s.get("total")),
            )
        console.print(table)

    # Disclaimer
    console.print(
        f"\n[dim]Note: Comparison based on cached notices and awards only. "
        f"Same supplier across multiple agencies can signal monopolistic "
        f"procurement patterns; verify against official PhilGEPS records.[/dim]"
    )
