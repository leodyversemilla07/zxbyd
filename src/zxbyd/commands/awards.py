"""Awards commands — check status, import, and list awards."""

from __future__ import annotations

import typer

awards_app = typer.Typer(help="Track contract awards and status.")

# Note: PhilGEPS award details (supplier name, amount) are behind authentication.
# The printable detail pages only show status (Active/Closed/Awarded).
# Use 'zxbyd awards import' to load award data exported from your PhilGEPS dashboard.


@awards_app.command()
def check(
    limit: int = typer.Option(20, "--limit", "-n", help="Max notices to check."),
    force: bool = typer.Option(False, "--force", "-f", help="Re-check even if status known."),
) -> None:
    """Re-fetch status for notices past their closing date.

    Detects status changes (Active -> Closed/Awarded) via printable pages.
    """
    from datetime import datetime

    from rich.table import Table

    from zxbyd.ui import info, console, success
    from zxbyd.data import connection, upsert_notice
    from zxbyd.sources import get_notice_detail

    with connection() as conn:
        if force:
            query = """
                SELECT ref_no, title, agency, closing_date, status
                FROM notices
                WHERE closing_date != ''
                ORDER BY closing_date DESC
                LIMIT ?
            """
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
def import_(
    filepath: str = typer.Argument(help="CSV or JSON file with award data."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without saving."),
) -> None:
    """Import award data from CSV/JSON.

    Expected columns/keys: ref_no, title, agency, supplier, amount, award_date, mode

    Export your PhilGEPS award data from the PhilGEPS dashboard,
    then import it here to enable supplier profiles and repeat-awardee analysis.

    Example CSV:
        ref_no,title,agency,supplier,amount,award_date,mode
        12600000,Supply of PPE,BFP-NCR,ACME CORP,17500000,2026-01-30,Public Bidding
    """
    import csv
    import json as json_mod
    from pathlib import Path

    from rich.table import Table

    from zxbyd.ui import info, console, success, warn
    from zxbyd.data import connection, upsert_award

    path = Path(filepath)
    if not path.exists():
        warn(f"File not found: {filepath}")
        raise typer.Exit(1)

    records = []

    if path.suffix.lower() == ".json":
        data = json_mod.loads(path.read_text())
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict) and "awards" in data:
            records = data["awards"]
        else:
            warn("JSON must be a list of objects or have an 'awards' key")
            raise typer.Exit(1)

    elif path.suffix.lower() == ".csv":
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            records = [row for row in reader]
    else:
        warn(f"Unsupported format: {path.suffix} (use .csv or .json)")
        raise typer.Exit(1)

    if not records:
        warn("No records found in file")
        raise typer.Exit(1)

    # Normalize records
    normalized = []
    for r in records:
        normalized.append({
            "ref_no": str(r.get("ref_no", "")),
            "title": str(r.get("title", "")),
            "agency": str(r.get("agency", "")),
            "supplier": str(r.get("supplier", "")),
            "amount": float(r.get("amount", 0) or 0),
            "award_date": str(r.get("award_date", "")),
            "mode": str(r.get("mode", "")),
        })

    # Preview
    table = Table(title=f"Import Preview ({len(normalized)} records)", show_lines=True)
    table.add_column("Ref #", style="cyan", no_wrap=True)
    table.add_column("Supplier", max_width=30)
    table.add_column("Amount", justify="right", style="green")
    table.add_column("Agency", max_width=25)

    for r in normalized[:10]:
        table.add_row(
            r["ref_no"],
            (r["supplier"] or "—")[:30],
            f"₱{r['amount']:,.0f}" if r["amount"] else "—",
            (r["agency"] or "—")[:25],
        )

    if len(normalized) > 10:
        table.add_row("...", f"({len(normalized) - 10} more)", "", "")

    console.print(table)

    if dry_run:
        info("Dry run — no data saved.")
        return

    # Import
    with connection() as conn:
        imported = 0
        for r in normalized:
            if r["supplier"] and r["ref_no"]:
                upsert_award(conn, r)
                imported += 1
        conn.commit()

    success(f"Imported {imported} award(s)")


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


@awards_app.command("list")
def list_awards(
    agency: str | None = typer.Option(None, "--agency", "-a", help="Filter by agency name."),
    supplier: str | None = typer.Option(None, "--supplier", "-s", help="Filter by supplier name."),
    limit: int = typer.Option(50, "--limit", "-n", help="Max results."),
) -> None:
    """List cached contract awards."""
    from zxbyd.ui import info, show_awards
    from zxbyd.data import connection, search_awards as db_search_awards

    with connection() as conn:
        results = db_search_awards(conn, agency=agency, supplier=supplier, limit=limit)

    if not results:
        info("No award data cached. Use 'zxbyd awards import' to load award data from CSV/JSON.")
        return

    show_awards(results, agency=agency, supplier=supplier)
