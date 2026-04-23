"""Cache management commands — stats, clear, export."""

from __future__ import annotations

import json as json_mod
from pathlib import Path

import typer

cache_app = typer.Typer(help="Manage local cache.")


@cache_app.command()
def stats() -> None:
    """Show cache statistics."""
    from rich.table import Table

    from zxbyd.ui import console, info
    from zxbyd.data import connection, get_db_path

    db_path = get_db_path()

    if not db_path.exists():
        info("No cache found. Run 'zxbyd search notices' first.")
        return

    db_size = db_path.stat().st_size

    with connection() as conn:
        notice_count = conn.execute("SELECT COUNT(*) FROM notices").fetchone()[0]
        with_abc = conn.execute("SELECT COUNT(*) FROM notices WHERE abc IS NOT NULL AND abc > 0").fetchone()[0]
        award_count = conn.execute("SELECT COUNT(*) FROM awards").fetchone()[0]
        agency_count = conn.execute("SELECT COUNT(DISTINCT agency) FROM notices WHERE agency != ''").fetchone()[0]

        # Oldest and newest cached
        oldest = conn.execute("SELECT MIN(cached_at) FROM notices").fetchone()[0] or "—"
        newest = conn.execute("SELECT MAX(cached_at) FROM notices").fetchone()[0] or "—"

    table = Table(title="zxbyd Cache", show_lines=True)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Database", str(db_path))
    table.add_row("Size", f"{db_size / 1024:.1f} KB")
    table.add_row("Notices", str(notice_count))
    table.add_row("  with ABC", str(with_abc))
    table.add_row("Awards", str(award_count))
    table.add_row("Unique Agencies", str(agency_count))
    table.add_row("Oldest Entry", oldest)
    table.add_row("Newest Entry", newest)

    console.print(table)


@cache_app.command()
def clear(
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Clear all cached data."""
    from zxbyd.ui import info, success
    from zxbyd.data import connection, get_db_path

    db_path = get_db_path()

    if not db_path.exists():
        info("No cache to clear.")
        return

    if not confirm:
        typer.confirm("This will delete all cached notices and awards. Continue?", abort=True)

    with connection() as conn:
        conn.execute("DELETE FROM notices")
        conn.execute("DELETE FROM awards")
        conn.commit()

    success("Cache cleared.")


@cache_app.command()
def export(
    filepath: str = typer.Argument(help="Output file path (.json)."),
    table: str = typer.Option("notices", "--table", "-t", help="Table to export (notices/awards/both)."),
) -> None:
    """Export cached data to JSON."""
    from zxbyd.ui import info, success
    from zxbyd.data import connection

    with connection() as conn:
        data = {}

        if table in ("notices", "both"):
            rows = conn.execute("SELECT * FROM notices").fetchall()
            data["notices"] = [dict(r) for r in rows]

        if table in ("awards", "both"):
            rows = conn.execute("SELECT * FROM awards").fetchall()
            data["awards"] = [dict(r) for r in rows]

    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_mod.dumps(data, indent=2, default=str))

    total = sum(len(v) for v in data.values())
    success(f"Exported {total} record(s) to {path}")
