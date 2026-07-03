"""SQLite cache schema and migrations for OCDS-structured data.

SCHEMA_SQL contains the full initial schema (notices + awards + releases).
run_migrations() handles incremental schema changes for existing databases.
"""

from __future__ import annotations

import sqlite3

SCHEMA_SQL = """
-- Notices table (original flat schema, backward compatible)
CREATE TABLE IF NOT EXISTS notices (
    ref_no TEXT PRIMARY KEY,
    title TEXT,
    agency TEXT,
    category TEXT,
    abc REAL,
    mode TEXT,
    area_of_delivery TEXT,
    published_date TEXT,
    closing_date TEXT,
    description TEXT,
    documents TEXT,
    status TEXT DEFAULT '',
    solicitation_number TEXT DEFAULT '',
    cached_at TEXT DEFAULT (datetime('now'))
);

-- Awards table (original flat schema, backward compatible)
CREATE TABLE IF NOT EXISTS awards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_no TEXT,
    title TEXT,
    agency TEXT,
    supplier TEXT,
    amount REAL,
    award_date TEXT,
    mode TEXT,
    cached_at TEXT DEFAULT (datetime('now'))
);

-- OCDS releases table — stores the full OCDS release as JSON
CREATE TABLE IF NOT EXISTS releases (
    ocid TEXT PRIMARY KEY,
    ref_no TEXT,
    release_json TEXT NOT NULL,
    agency TEXT,
    category TEXT,
    abc REAL,
    mode TEXT,
    status TEXT DEFAULT '',
    published_date TEXT,
    closing_date TEXT,
    cached_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_notices_agency ON notices(agency);
CREATE INDEX IF NOT EXISTS idx_notices_category ON notices(category);
CREATE INDEX IF NOT EXISTS idx_awards_supplier ON awards(supplier);
CREATE INDEX IF NOT EXISTS idx_awards_agency ON awards(agency);
CREATE INDEX IF NOT EXISTS idx_releases_agency ON releases(agency);
CREATE INDEX IF NOT EXISTS idx_releases_category ON releases(category);
CREATE INDEX IF NOT EXISTS idx_releases_ref_no ON releases(ref_no);
"""


def run_migrations(conn: sqlite3.Connection) -> None:
    """Run incremental schema migrations for databases created before OCDS support.

    Safe to call on every connection — operations use IF NOT EXISTS / PRAGMA guards.
    """
    # ── Legacy: add columns added after initial schema ────────────
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(notices)").fetchall()}
    if "status" not in existing_cols:
        conn.execute("ALTER TABLE notices ADD COLUMN status TEXT DEFAULT ''")
    if "solicitation_number" not in existing_cols:
        conn.execute("ALTER TABLE notices ADD COLUMN solicitation_number TEXT DEFAULT ''")

    # ── Legacy: create releases table for databases from before OCDS merge ──
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "releases" not in tables:
        conn.execute("""
            CREATE TABLE releases (
                ocid TEXT PRIMARY KEY,
                ref_no TEXT,
                release_json TEXT NOT NULL,
                agency TEXT,
                category TEXT,
                abc REAL,
                mode TEXT,
                status TEXT DEFAULT '',
                published_date TEXT,
                closing_date TEXT,
                cached_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_releases_agency ON releases(agency)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_releases_category ON releases(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_releases_ref_no ON releases(ref_no)")
