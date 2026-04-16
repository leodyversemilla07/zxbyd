"""Profile commands — agency, supplier, agencies list."""

from __future__ import annotations

import typer

profiles_app = typer.Typer(help="Agency and supplier profiles.")


@profiles_app.command()
def agency(
    name: str = typer.Argument(help="Agency name (e.g., 'DICT')."),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show procurement profile for a government agency."""
    import json as json_mod

    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    from zxbyd.ui import info, console
    from zxbyd.data import connection

    info(f"Loading profile for '{name}'...")

    with connection() as conn:
        # Aggregate notice stats
        row = conn.execute("""
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
        """, (f"%{name}%",)).fetchone()

        if not row or row["notice_count"] == 0:
            info(f"No cached data for agency '{name}'. Run 'zxbyd search notices' first.")
            raise typer.Exit(1)

        stats = dict(row)

        # Procurement modes breakdown
        modes = conn.execute("""
            SELECT mode, COUNT(*) as count, SUM(COALESCE(abc, 0)) as total_abc
            FROM notices
            WHERE agency LIKE ? AND mode != ''
            GROUP BY mode
            ORDER BY count DESC
        """, (f"%{name}%",)).fetchall()
        modes = [dict(m) for m in modes]

        # Categories breakdown
        categories = conn.execute("""
            SELECT category, COUNT(*) as count
            FROM notices
            WHERE agency LIKE ? AND category != ''
            GROUP BY category
            ORDER BY count DESC
            LIMIT 10
        """, (f"%{name}%",)).fetchall()
        categories = [dict(c) for c in categories]

        # Recent notices
        recent = conn.execute("""
            SELECT ref_no, title, abc, mode, closing_date
            FROM notices
            WHERE agency LIKE ?
            ORDER BY cached_at DESC
            LIMIT 10
        """, (f"%{name}%",)).fetchall()
        recent = [dict(r) for r in recent]

        # Suppliers from awards
        suppliers = conn.execute("""
            SELECT supplier, COUNT(*) as count, SUM(amount) as total
            FROM awards
            WHERE agency LIKE ?
            GROUP BY supplier
            ORDER BY total DESC
            LIMIT 10
        """, (f"%{name}%",)).fetchall()
        suppliers = [dict(s) for s in suppliers]

    if as_json:
        output = {
            "agency": name,
            "stats": stats,
            "procurement_modes": modes,
            "top_categories": categories,
            "recent_notices": recent,
            "top_suppliers": suppliers,
        }
        typer.echo(json_mod.dumps(output, indent=2, default=str))
        return

    # Rich display
    content = Text()
    content.append(f"Notices: ", style="bold")
    content.append(f"{stats['notice_count']} ({stats['with_abc']} with ABC)\n")
    content.append(f"Total ABC: ", style="bold")
    total_abc = stats.get("total_abc", 0) or 0
    content.append(f"₱{total_abc:,.0f}\n")
    content.append(f"Avg ABC: ", style="bold")
    avg_abc = stats.get("avg_abc", 0) or 0
    content.append(f"₱{avg_abc:,.0f}\n")
    content.append(f"ABC Range: ", style="bold")
    min_abc = stats.get("min_abc", 0) or 0
    max_abc = stats.get("max_abc", 0) or 0
    content.append(f"₱{min_abc:,.0f} — ₱{max_abc:,.0f}\n")
    content.append(f"Categories: ", style="bold")
    content.append(f"{stats.get('category_count', 0)}\n")
    content.append(f"Modes Used: ", style="bold")
    content.append(f"{stats.get('mode_count', 0)}")

    console.print(Panel(content, title=f"[cyan]Agency[/cyan] — {name}", border_style="cyan"))

    # Procurement modes table
    if modes:
        table = Table(title="Procurement Modes", show_lines=True)
        table.add_column("Mode", max_width=30)
        table.add_column("Count", justify="center")
        table.add_column("Total ABC", justify="right", style="green")
        for m in modes:
            m_abc = m.get("total_abc", 0) or 0
            table.add_row(
                m["mode"][:30],
                str(m["count"]),
                f"₱{m_abc:,.0f}" if m_abc else "—",
            )
        console.print(table)

    # Categories
    if categories:
        console.print("\n[bold]Top Categories:[/bold]")
        for c in categories:
            console.print(f"  {c['category']}: {c['count']} notice(s)")

    # Recent notices
    if recent:
        table = Table(title="Recent Notices", show_lines=True)
        table.add_column("Ref #", style="cyan", no_wrap=True)
        table.add_column("Title", max_width=40)
        table.add_column("ABC", justify="right", style="green")
        table.add_column("Mode", max_width=15)
        for r in recent:
            abc = r.get("abc")
            table.add_row(
                r["ref_no"],
                (r["title"] or "—")[:40],
                f"₱{abc:,.0f}" if abc else "—",
                (r.get("mode") or "—")[:15],
            )
        console.print(table)

    # Top suppliers
    if suppliers:
        table = Table(title="Top Suppliers (from cached awards)", show_lines=True)
        table.add_column("Supplier", max_width=35)
        table.add_column("Awards", justify="center")
        table.add_column("Total", justify="right", style="green")
        for s in suppliers:
            total = s.get("total", 0) or 0
            table.add_row(
                (s["supplier"] or "—")[:35],
                str(s["count"]),
                f"₱{total:,.0f}" if total else "—",
            )
        console.print(table)


@profiles_app.command()
def supplier(
    name: str = typer.Argument(help="Supplier name (e.g., 'ACME CORPORATION')."),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Look up a supplier's profile and award history."""
    import json as json_mod

    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    from zxbyd.ui import info, console
    from zxbyd.data import connection

    info(f"Loading profile for '{name}'...")

    with connection() as conn:
        # Stats
        row = conn.execute("""
            SELECT supplier,
                   COUNT(*) as total_awards,
                   SUM(amount) as total_amount,
                   AVG(amount) as avg_amount,
                   MIN(amount) as min_amount,
                   MAX(amount) as max_amount,
                   COUNT(DISTINCT agency) as agency_count
            FROM awards
            WHERE supplier LIKE ?
            GROUP BY supplier
        """, (f"%{name}%",)).fetchone()

        if not row:
            info(f"No cached data for supplier '{name}'. Need award data.")
            raise typer.Exit(1)

        stats = dict(row)

        # Agencies served
        agencies = conn.execute("""
            SELECT agency, COUNT(*) as count, SUM(amount) as total
            FROM awards
            WHERE supplier LIKE ?
            GROUP BY agency
            ORDER BY total DESC
        """, (f"%{name}%",)).fetchall()
        agencies = [dict(a) for a in agencies]

        # Recent awards
        recent = conn.execute("""
            SELECT ref_no, title, agency, amount, award_date, mode
            FROM awards
            WHERE supplier LIKE ?
            ORDER BY award_date DESC
            LIMIT 10
        """, (f"%{name}%",)).fetchall()
        recent = [dict(r) for r in recent]

    if as_json:
        output = {
            "supplier": name,
            "stats": stats,
            "agencies_served": agencies,
            "recent_awards": recent,
        }
        typer.echo(json_mod.dumps(output, indent=2, default=str))
        return

    # Rich display
    content = Text()
    content.append(f"Total Awards: ", style="bold")
    content.append(f"{stats['total_awards']}\n")
    content.append(f"Total Amount: ", style="bold")
    total = stats.get("total_amount", 0) or 0
    content.append(f"₱{total:,.0f}\n")
    content.append(f"Avg Award: ", style="bold")
    avg = stats.get("avg_amount", 0) or 0
    content.append(f"₱{avg:,.0f}\n")
    content.append(f"Range: ", style="bold")
    min_a = stats.get("min_amount", 0) or 0
    max_a = stats.get("max_amount", 0) or 0
    content.append(f"₱{min_a:,.0f} — ₱{max_a:,.0f}\n")
    content.append(f"Agencies Served: ", style="bold")
    content.append(f"{stats.get('agency_count', 0)}")

    console.print(Panel(content, title=f"[cyan]Supplier[/cyan] — {name}", border_style="cyan"))

    # Agencies table
    if agencies:
        table = Table(title="Agencies Served", show_lines=True)
        table.add_column("Agency", max_width=35)
        table.add_column("Awards", justify="center")
        table.add_column("Total", justify="right", style="green")
        for a in agencies:
            a_total = a.get("total", 0) or 0
            table.add_row(
                (a["agency"] or "—")[:35],
                str(a["count"]),
                f"₱{a_total:,.0f}" if a_total else "—",
            )
        console.print(table)

    # Recent awards
    if recent:
        table = Table(title="Recent Awards", show_lines=True)
        table.add_column("Ref #", style="cyan", no_wrap=True)
        table.add_column("Title", max_width=30)
        table.add_column("Agency", max_width=25)
        table.add_column("Amount", justify="right", style="green")
        table.add_column("Date", no_wrap=True)
        for r in recent:
            amount = r.get("amount")
            table.add_row(
                r.get("ref_no", "—"),
                (r.get("title") or "—")[:30],
                (r.get("agency") or "—")[:25],
                f"₱{amount:,.0f}" if amount else "—",
                r.get("award_date") or "—",
            )
        console.print(table)


@profiles_app.command()
def agencies(
    query: str = typer.Argument(default="", help="Filter agencies by name substring."),
    limit: int = typer.Option(50, "--limit", "-n", help="Max results."),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List procuring entities known from cached notices."""
    import json as json_mod

    from rich.table import Table

    from zxbyd.ui import info, console
    from zxbyd.data import connection

    with connection() as conn:
        sql = """
            SELECT agency,
                   COUNT(*) as notice_count,
                   SUM(COALESCE(abc, 0)) as total_abc
            FROM notices
            WHERE agency != ''
        """
        params: list = []
        if query:
            sql += " AND agency LIKE ?"
            params.append(f"%{query}%")

        sql += " GROUP BY agency ORDER BY notice_count DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        results = [dict(r) for r in rows]

    if not results:
        info("No agencies found in cache. Run 'zxbyd search notices' first.")
        raise typer.Exit(1)

    if as_json:
        typer.echo(json_mod.dumps(results, indent=2, default=str))
        return

    table = Table(title="Known Agencies", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Agency", max_width=45)
    table.add_column("Notices", justify="center")
    table.add_column("Total ABC", justify="right", style="green")

    for i, r in enumerate(results, 1):
        abc = r.get("total_abc", 0) or 0
        table.add_row(
            str(i),
            r["agency"][:45],
            str(r["notice_count"]),
            f"₱{abc:,.0f}" if abc else "—",
        )

    console.print(table)
    info(f"{len(results)} agencies")
