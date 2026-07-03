"""CLI commands — shared utilities."""

from __future__ import annotations


def enrich_notices(conn, notices: list[dict], max_fetch: int = 10) -> int:
    """Fetch details for notices missing ABC data.

    Returns count of notices enriched.
    Moved here from analysis.py to avoid cross-command imports.
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
                detail["ref_no"] = ref
                upsert_notice(conn, detail)
                enriched += 1
        except Exception:
            continue

    if enriched:
        info(f"Enriched {enriched} notice(s) with ABC data.")
    return enriched
