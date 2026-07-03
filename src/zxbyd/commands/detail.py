"""Detail command — fetch notice details with optional OCDS output."""

from __future__ import annotations

import typer

detail_app = typer.Typer(help="Fetch notice details.")


@detail_app.command()
def show(
    ref_id: str = typer.Argument(help="PhilGEPS reference number (e.g., 12905086)."),
    force: bool = typer.Option(False, "--force", "-f", help="Re-fetch even if cached."),
    ocds: bool = typer.Option(False, "--ocds", help="Show result as OCDS release format."),
    as_json: bool = typer.Option(False, "--json", help="Output raw JSON."),
) -> None:
    """Fetch full details for a procurement notice by reference ID.

    Displays the notice in Rich format by default.
    Use --ocds to see the OCDS-compliant release structure.
    Use --json for machine-readable output.
    """
    import json as json_mod

    from zxbyd.ui import info, show_notice_detail, show_release_detail, error
    from zxbyd.data import connection, upsert_notice
    from zxbyd.storage import search_releases
    from zxbyd.models.release import Release

    # Try cache first
    if not force:
        with connection() as conn:
            # Check OCDS cache
            ocds_results = search_releases(conn, query=ref_id, limit=1)
            if ocds_results:
                release = ocds_results[0]
                # Confirm the ref_no matches
                if ref_id in release.ocid:
                    if as_json:
                        typer.echo(json_mod.dumps(
                            release.model_dump(mode="json", by_alias=True),
                            indent=2, default=str,
                        ))
                        return
                    if ocds:
                        show_release_detail(release)
                        info(f"OCDS release: {release.ocid}")
                        return
                    # Fall through to plain detail (might not have all fields)
                    show_release_detail(release)
                    info(f"Showing cached OCDS release for {ref_id}")
                    return

            # Legacy cache fallback
            row = conn.execute(
                "SELECT * FROM notices WHERE ref_no = ?", (ref_id,)
            ).fetchone()
            if row and row["description"]:
                info(f"Showing cached details for {ref_id}...")
                data = dict(row)
                if as_json:
                    typer.echo(json_mod.dumps(data, indent=2, default=str))
                    return
                if ocds:
                    release = Release.from_philgeps_dict(data)
                    show_release_detail(release)
                    info(f"OCDS release: {release.ocid}")
                    return
                show_notice_detail(data)
                return

    # Fetch from PhilGEPS
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

    if as_json:
        if ocds:
            release = Release.from_philgeps_dict(detail_data)
            typer.echo(json_mod.dumps(
                release.model_dump(mode="json", by_alias=True),
                indent=2, default=str,
            ))
        else:
            typer.echo(json_mod.dumps(detail_data, indent=2, default=str))
        return

    if ocds:
        release = Release.from_philgeps_dict(detail_data)
        show_release_detail(release)
        info(f"OCDS release: {release.ocid}")
        return

    show_notice_detail(detail_data)
