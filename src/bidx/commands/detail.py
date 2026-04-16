"""Detail command."""

from __future__ import annotations

import typer

detail_app = typer.Typer(help="Fetch notice details.")


@detail_app.command()
def show(
    ref_id: str = typer.Argument(help="PhilGEPS reference number (e.g., 12905086)."),
    force: bool = typer.Option(False, "--force", "-f", help="Re-fetch even if cached."),
) -> None:
    """Fetch full details for a procurement notice by reference ID."""
    from zxbyd.ui import info, show_notice_detail, error
    from zxbyd.data import connection, upsert_notice

    # Check cache first
    if not force:
        with connection() as conn:
            row = conn.execute(
                "SELECT * FROM notices WHERE ref_no = ?", (ref_id,)
            ).fetchone()
            if row and row["description"]:
                info(f"Showing cached details for {ref_id}...")
                show_notice_detail(dict(row))
                return

    info(f"Fetching details for {ref_id}...")
    try:
        from zxbyd.sources import get_notice_detail
        detail_data = get_notice_detail(ref_id)
    except NotImplementedError as e:
        error(str(e))
        raise typer.Exit(1)

    if "error" in detail_data:
        error(f"Failed: {detail_data['error']}")
        raise typer.Exit(1)

    # Cache
    with connection() as conn:
        upsert_notice(conn, detail_data)

    show_notice_detail(detail_data)
