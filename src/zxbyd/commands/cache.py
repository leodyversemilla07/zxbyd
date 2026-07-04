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
        release_count = conn.execute("SELECT COUNT(*) FROM releases").fetchone()[0]
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
    table.add_row("OCDS Releases", str(release_count))
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
        conn.execute("DELETE FROM releases")
        conn.commit()

    success("Cache cleared.")


@cache_app.command()
def export(
    filepath: str = typer.Argument(help="Output file path (.json)."),
    table: str = typer.Option("notices", "--table", "-t", help="Table to export (notices/awards/releases/both/all)."),
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

        if table in ("releases", "all"):
            rows = conn.execute("SELECT * FROM releases").fetchall()
            data["releases"] = [dict(r) for r in rows]

    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_mod.dumps(data, indent=2, default=str))

    total = sum(len(v) for v in data.values())
    success(f"Exported {total} record(s) to {path}")


@cache_app.command()
def seed(
    filepath: str = typer.Argument(
        "tests/fixtures/notices.json",
        help="Path to JSON fixture file (notices or awards JSON).",
    ),
    as_awards: bool = typer.Option(False, "--awards", "-a", help="Import as awards data."),
) -> None:
    """Seed cache from a JSON fixture file.

    Loads test fixture data from a JSON file into the local cache.
    Useful for offline testing without hitting PhilGEPS.

    Example:
        zxbyd cache seed tests/fixtures/notices.json
        zxbyd cache seed tests/fixtures/awards.json --awards
    """
    from zxbyd.ui import info, success, error
    from zxbyd.data import connection, upsert_notice, upsert_award
    from zxbyd.storage import upsert_award_release
    from zxbyd.models.release import Release

    path = Path(filepath)
    if not path.exists():
        error(f"File not found: {filepath}")
        raise typer.Exit(1)

    raw = json_mod.loads(path.read_text(encoding="utf-8"))
    records = raw if isinstance(raw, list) else []

    if not records:
        error("No records found in fixture file")
        raise typer.Exit(1)

    info(f"Loading {len(records)} record(s) from {path}...")

    with connection() as conn:
        if as_awards:
            imported = 0
            for r in records:
                upsert_award(conn, r)
                upsert_award_release(conn, r)
                imported += 1
            conn.commit()
            success(f"Seeded {imported} award(s)")
        else:
            imported = 0
            release_count = 0
            for r in records:
                upsert_notice(conn, r)
                imported += 1
                # Also store as OCDS release
                try:
                    release = Release.from_philgeps_dict(r)
                    from zxbyd.storage import upsert_release
                    upsert_release(conn, release)
                    release_count += 1
                except Exception:
                    pass
            conn.commit()
            success(f"Seeded {imported} notice(s), {release_count} OCDS release(s)")
