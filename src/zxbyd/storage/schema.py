"""SQLite cache schema and migrations for OCDS-structured data.

SCHEMA_SQL contains the full initial schema (notices + awards + releases).
run_migrations() handles incremental schema changes for existing databases.
"""

from __future__ import annotations

import json
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
    release_id TEXT NOT NULL,
    ocid TEXT NOT NULL,
    ref_no TEXT,
    release_json TEXT NOT NULL,
    agency TEXT,
    category TEXT,
    abc REAL,
    mode TEXT,
    status TEXT DEFAULT '',
    published_date TEXT,
    closing_date TEXT,
    cached_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (ocid, release_id)
);

CREATE INDEX IF NOT EXISTS idx_notices_agency ON notices(agency);
CREATE INDEX IF NOT EXISTS idx_notices_category ON notices(category);
CREATE INDEX IF NOT EXISTS idx_awards_supplier ON awards(supplier);
CREATE INDEX IF NOT EXISTS idx_awards_agency ON awards(agency);
CREATE INDEX IF NOT EXISTS idx_releases_agency ON releases(agency);
CREATE INDEX IF NOT EXISTS idx_releases_category ON releases(category);
CREATE INDEX IF NOT EXISTS idx_releases_ref_no ON releases(ref_no);
CREATE INDEX IF NOT EXISTS idx_releases_ocid ON releases(ocid);
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

    # Releases are events within a contracting process. Older cache versions
    # keyed this table by OCID, which caused an award event to overwrite tender.
    release_cols = {row[1]: row[5] for row in conn.execute("PRAGMA table_info(releases)").fetchall()}
    if release_cols and (release_cols.get("release_id") != 2 or release_cols.get("ocid") != 1):
        conn.execute("ALTER TABLE releases RENAME TO releases_legacy")
        conn.execute("""
            CREATE TABLE releases (
                release_id TEXT NOT NULL,
                ocid TEXT NOT NULL,
                ref_no TEXT,
                release_json TEXT NOT NULL,
                agency TEXT,
                category TEXT,
                abc REAL,
                mode TEXT,
                status TEXT DEFAULT '',
                published_date TEXT,
                closing_date TEXT,
                cached_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (ocid, release_id)
            )
        """)
        for row in conn.execute("SELECT * FROM releases_legacy").fetchall():
            data = dict(row)
            try:
                release = json.loads(data["release_json"])
            except (KeyError, TypeError, ValueError):
                release = {}
            release_id = release.get("id") or f"{data.get('ocid', '')}-legacy"
            ref_no = data.get("ocid", "").rsplit("-", 1)[-1] or data.get("ref_no")
            conn.execute("""
                INSERT OR IGNORE INTO releases
                    (release_id, ocid, ref_no, release_json, agency, category, abc,
                     mode, status, published_date, closing_date, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (release_id, data.get("ocid", ""), ref_no, data.get("release_json", "{}"),
                  data.get("agency"), data.get("category"), data.get("abc"), data.get("mode"),
                  data.get("status", ""), data.get("published_date"), data.get("closing_date"),
                  data.get("cached_at")))
        conn.execute("DROP TABLE releases_legacy")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_releases_agency ON releases(agency)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_releases_category ON releases(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_releases_ref_no ON releases(ref_no)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_releases_ocid ON releases(ocid)")

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
                release_id TEXT NOT NULL,
                ocid TEXT NOT NULL,
                ref_no TEXT,
                release_json TEXT NOT NULL,
                agency TEXT,
                category TEXT,
                abc REAL,
                mode TEXT,
                status TEXT DEFAULT '',
                published_date TEXT,
                closing_date TEXT,
                cached_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (ocid, release_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_releases_agency ON releases(agency)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_releases_category ON releases(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_releases_ref_no ON releases(ref_no)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_releases_ocid ON releases(ocid)")
