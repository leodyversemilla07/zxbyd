"""Awards commands — check status, show awarded contracts."""

from __future__ import annotations

import typer

awards_app = typer.Typer(help="Track contract awards and status.")


@awards_app.command()
def check(
    limit: int = typer.Option(20, "--limit", "-n", help="Max notices to check."),
    force: bool = typer.Option(False, "--force", "-f", help="Re-check even if status known."),
) -> None:
    """Re-fetch status for notices past their closing date.

    PhilGEPS doesn't expose award details (supplier, amount) without JS rendering,
    but we can detect status changes (Active -> Closed/Awarded) via the printable page.
    """
    from datetime import datetime

    from rich.table import Table

    from zxbyd.ui import info, console, success
    from zxbyd.data import connection, upsert_notice
    from zxbyd.sources import get_notice_detail

    today = datetime.now().strftime("%Y-%m-%d")

    with connection() as conn:
        # Find notices past closing date
        if force:
            query = """
                SELECT ref_no, title, agency, closing_date, status
                FROM notices
                WHERE closing_date != ''
                ORDER BY closing_date DESC
                LIMIT ?
            """
            rows = conn.execute(query, (limit,)).fetchall()
        else:
            query = """
                SELECT ref_no, title, agency, closing_date, status
                FROM notices
                WHERE closing_date != ''
                AND (status = '' OR status = 'Active')
                ORDER BY closing_date DESC
                LIMIT ?
            """
            rows = conn.execute(query, (limit,)).fetchall()

        if not rows:
            info("No notices to check. Run 'zxbyd search notices' first.")
            return

        notices = [dict(r) for r in rows]
        info(f"Checking {len(notices)} notice(s) for status updates...")

        updated = 0
        status_changes = []

        for n in notices:
            ref = n["ref_no"]
            old_status = n.get("status", "")

            try:
                detail = get_notice_detail(ref)
                new_status = detail.get("status", "")

                if new_status and new_status != old_status:
                    upsert_notice(conn, detail)
                    status_changes.append({
                        "ref_no": ref,
                        "title": n["title"],
                        "agency": n["agency"],
                        "old_status": old_status or "(unknown)",
                        "new_status": new_status,
                    })
                    updated += 1
                elif new_status:
                    # Update status even if same (refresh timestamp)
                    upsert_notice(conn, {"ref_no": ref, "status": new_status})
            except Exception:
                continue

        conn.commit()

    if status_changes:
        table = Table(title="Status Changes", show_lines=True)
        table.add_column("Ref #", style="cyan", no_wrap=True)
        table.add_column("Title", max_width=40)
        table.add_column("Agency", max_width=25)
        table.add_column("Old", style="dim")
        table.add_column("New", style="bold green")

        for s in status_changes:
            table.add_row(
                s["ref_no"],
                (s["title"] or "—")[:40],
                (s["agency"] or "—")[:25],
                s["old_status"],
                s["new_status"],
            )

        console.print(table)
        success(f"{updated} status change(s) detected")
    else:
        info("No status changes detected.")


@awards_app.command()
def status(
    filter_status: str = typer.Option("", "--filter", "-s", help="Filter by status (Active/Closed/Awarded)."),
    limit: int = typer.Option(50, "--limit", "-n", help="Max results."),
) -> None:
    """Show notices grouped by status."""
    from rich.table import Table

    from zxbyd.ui import info, console
    from zxbyd.data import connection

    with connection() as conn:
        # Status summary
        summary = conn.execute("""
            SELECT CASE WHEN status = '' THEN '(unknown)' ELSE status END as st,
                   COUNT(*) as cnt
            FROM notices
            GROUP BY st
            ORDER BY cnt DESC
        """).fetchall()

        if not summary:
            info("No cached notices. Run 'zxbyd search notices' first.")
            return

        console.print("\n[bold]Status Summary:[/bold]")
        for row in summary:
            console.print(f"  {row['st']}: {row['cnt']}")

        # Detailed list
        if filter_status:
            query = """
                SELECT ref_no, title, agency, abc, status, closing_date
                FROM notices
                WHERE status LIKE ?
                ORDER BY closing_date DESC
                LIMIT ?
            """
            rows = conn.execute(query, (f"%{filter_status}%", limit)).fetchall()
        else:
            query = """
                SELECT ref_no, title, agency, abc, status, closing_date
                FROM notices
                WHERE status != '' AND status != 'Active'
                ORDER BY closing_date DESC
                LIMIT ?
            """
            rows = conn.execute(query, (limit,)).fetchall()

        if not rows:
            info("No matching notices.")
            return

        table = Table(title="Notices by Status", show_lines=True)
        table.add_column("Ref #", style="cyan", no_wrap=True)
        table.add_column("Title", max_width=35)
        table.add_column("Agency", max_width=25)
        table.add_column("ABC", justify="right", style="green")
        table.add_column("Status", style="bold")
        table.add_column("Closing", no_wrap=True)

        for r in rows:
            abc = r["abc"]
            table.add_row(
                r["ref_no"],
                (r["title"] or "—")[:35],
                (r["agency"] or "—")[:25],
                f"₱{abc:,.0f}" if abc else "—",
                r["status"] or "—",
                r["closing_date"] or "—",
            )

        console.print(table)


@awards_app.command()
def list(
    agency: str | None = typer.Option(None, "--agency", "-a", help="Filter by agency name."),
    supplier: str | None = typer.Option(None, "--supplier", "-s", help="Filter by supplier name."),
    limit: int = typer.Option(50, "--limit", "-n", help="Max results."),
) -> None:
    """List cached contract awards (requires award data in DB)."""
    from zxbyd.ui import info, show_awards
    from zxbyd.data import connection, search_awards as db_search_awards

    with connection() as conn:
        results = db_search_awards(conn, agency=agency, supplier=supplier, limit=limit)

    if not results:
        info("No award data cached. PhilGEPS awards require JS rendering — use 'zxbyd detail show' on individual notices.")
        return

    show_awards(results, agency=agency, supplier=supplier)
