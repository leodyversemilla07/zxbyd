"""SQLite cache layer — re-exports from storage package for backward compatibility.

All new code should import from zxbyd.storage directly.
This module will be deprecated in a future release.
"""

from zxbyd.storage import (
    connection,
    upsert_notice,
    upsert_award,
    search_notices,
    search_awards,
    get_supplier_stats,
    get_agency_stats,
    get_cache_dir,
    get_db_path,
    # New OCDS-aware exports
    upsert_release,
    search_releases,
    upsert_award_release,
)

__all__ = [
    "connection",
    "upsert_notice",
    "upsert_award",
    "search_notices",
    "search_awards",
    "get_supplier_stats",
    "get_agency_stats",
    "get_cache_dir",
    "get_db_path",
    "upsert_release",
    "search_releases",
]
