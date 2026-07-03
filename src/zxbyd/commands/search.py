"""Search and detail commands."""

from __future__ import annotations

import csv
import json as json_mod
from pathlib import Path

import typer

from zxbyd.data import connection, upsert_notice


def _export_results(results: list[dict], filepath: str) -> None:
    """Export results to CSV or JSON based on file extension."""
    path = Path(filepath)

    if path.suffix.lower() == ".json":
        path.write_text(json_mod.dumps(results, indent=2, default=str))
    elif path.suffix.lower() == ".csv":
        if not results:
            return
        fieldnames = list(results[0].keys())
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(results)
    else:
        from zxbyd.ui import warn
        warn(f"Unknown format '{path.suffix}' — use .csv or .json")
        return

    from zxbyd.ui import success
    success(f"Exported {len(results)} result(s) to {path}")

search_app = typer.Typer(help="Search procurement notices.")


@search_app.command()
def notices(
    query: str = typer.Argument(help="Search keywords (e.g., 'laptop', 'server')."),
    pages: int = typer.Option(1, "--pages", "-p", help="Pages to scrape (20 results/page)."),
    agency: str | None = typer.Option(None, "--agency", "-a", help="Filter by agency name."),
    detail: bool = typer.Option(False, "--detail", "-d", help="Fetch full details for each result."),
    cache_only: bool = typer.Option(False, "--cache-only", help="Only search local cache (no scraping)."),
    output: str | None = typer.Option(None, "--output", "-o", help="Export to file (.csv or .json)."),
) -> None:
    """Search procurement notices by keyword."""
    from zxbyd.ui import info, show_notices, error

    if cache_only:
        info(f'Searching cache for "{query}"...')
        with connection() as conn:
            from zxbyd.data import search_notices
            results = search_notices(conn, query=query, agency=agency)
        show_notices(results, query)
        if output and results:
            _export_results(results, output)
        return

    info(f'Searching PhilGEPS for "{query}"...')
    try:
        from zxbyd.sources import search as search_source
        results = search_source(query, max_pages=pages)
    except NotImplementedError as e:
        error(str(e))
        raise typer.Exit(1)

    if agency:
        agency_lower = agency.lower()
        results = [r for r in results if agency_lower in r.get("agency", "").lower()]

    if detail:
        info("Fetching details for each result...")
        from zxbyd.sources import get_notice_detail
        detailed_results = []
        for r in results:
            ref = r.get("ref_no", "")
            if ref:
                detail_data = get_notice_detail(ref)
                r.update(detail_data)
            detailed_results.append(r)
        results = detailed_results

    # Cache results
    with connection() as conn:
        for r in results:
            upsert_notice(conn, r)

    show_notices(results, query)

    # Export to file
    if output and results:
        _export_results(results, output)


@search_app.command()
def recent(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of recent notices."),
    agency: str | None = typer.Option(None, "--agency", "-a", help="Filter by agency name."),
) -> None:
    """Show recent procurement notices."""
    from zxbyd.ui import info, show_notices, error

    info("Fetching recent notices...")
    try:
        from zxbyd.sources import search as search_source
        # Search with empty query returns recent notices
        results = search_source("", max_pages=1)
    except NotImplementedError as e:
        error(str(e))
        raise typer.Exit(1)

    if agency:
        agency_lower = agency.lower()
        results = [r for r in results if agency_lower in r.get("agency", "").lower()]

    # Cache results
    with connection() as conn:
        for r in results:
            upsert_notice(conn, r)

    show_notices(results[:limit], "recent")


@search_app.command()
def releases(
    query: str = typer.Argument(help="Search keywords (e.g., 'laptop', 'server')."),
    agency: str | None = typer.Option(None, "--agency", "-a", help="Filter by agency name."),
    limit: int = typer.Option(50, "--limit", "-n", help="Max results."),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Search cached OCDS releases by keyword.

    Unlike 'search notices', this returns data in OCDS format
    with validated structure. Only searches local cache.
    """
    import json as json_mod

    from zxbyd.ui import info, show_releases, error
    from zxbyd.storage import connection, search_releases

    info(f'Searching OCDS releases for "{query}"...')
    with connection() as conn:
        results = search_releases(conn, query=query, agency=agency, limit=limit)

    if not results:
        info(f'No OCDS releases found for "{query}". Run "zxbyd search notices" first to populate cache.')
        return

    if as_json:
        dump = [
            r.model_dump(mode="json", by_alias=True) for r in results
        ]
        typer.echo(json_mod.dumps(dump, indent=2, default=str))
        return

    show_releases(results, query)
