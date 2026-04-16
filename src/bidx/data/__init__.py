"""SQLite cache layer."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator


def get_cache_dir() -> Path:
    """Get cache directory, respecting BIDX_CACHE_DIR env var."""
    if env := os.environ.get("BIDX_CACHE_DIR"):
        return Path(env)
    return Path.home() / ".zxbyd"


def get_db_path() -> Path:
    """Get SQLite database path."""
    return get_cache_dir() / "zxbyd.db"


def _init_db(conn: sqlite3.Connection) -> None:
    """Initialize database schema."""
    conn.executescript("""
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
            cached_at TEXT DEFAULT (datetime('now'))
        );

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

        CREATE INDEX IF NOT EXISTS idx_notices_agency ON notices(agency);
        CREATE INDEX IF NOT EXISTS idx_notices_category ON notices(category);
        CREATE INDEX IF NOT EXISTS idx_awards_supplier ON awards(supplier);
        CREATE INDEX IF NOT EXISTS idx_awards_agency ON awards(agency);
    """)


@contextmanager
def connection() -> Generator[sqlite3.Connection, None, None]:
    """Get a database connection (context manager).

    Usage:
        with cache.connection() as conn:
            results = conn.execute("SELECT * FROM notices").fetchall()
    """
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        _init_db(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_notice(conn: sqlite3.Connection, notice: dict[str, Any]) -> None:
    """Insert or update a notice in the cache."""
    conn.execute("""
        INSERT INTO notices (ref_no, title, agency, category, abc, mode,
                           area_of_delivery, published_date, closing_date,
                           description, documents)
        VALUES (:ref_no, :title, :agency, :category, :abc, :mode,
                :area_of_delivery, :published_date, :closing_date,
                :description, :documents)
        ON CONFLICT(ref_no) DO UPDATE SET
            title=excluded.title,
            agency=excluded.agency,
            category=excluded.category,
            abc=COALESCE(excluded.abc, notices.abc),
            mode=COALESCE(excluded.mode, notices.mode),
            area_of_delivery=COALESCE(excluded.area_of_delivery, notices.area_of_delivery),
            published_date=excluded.published_date,
            closing_date=excluded.closing_date,
            description=COALESCE(excluded.description, notices.description),
            documents=COALESCE(excluded.documents, notices.documents),
            cached_at=datetime('now')
    """, {
        "ref_no": notice.get("ref_no", ""),
        "title": notice.get("title", ""),
        "agency": notice.get("agency", ""),
        "category": notice.get("category", ""),
        "abc": notice.get("abc"),
        "mode": notice.get("mode", ""),
        "area_of_delivery": notice.get("area_of_delivery", ""),
        "published_date": notice.get("published_date", ""),
        "closing_date": notice.get("closing_date", ""),
        "description": notice.get("description", ""),
        "documents": notice.get("documents", ""),
    })


def upsert_award(conn: sqlite3.Connection, award: dict[str, Any]) -> None:
    """Insert an award record."""
    conn.execute("""
        INSERT INTO awards (ref_no, title, agency, supplier, amount, award_date, mode)
        VALUES (:ref_no, :title, :agency, :supplier, :amount, :award_date, :mode)
    """, award)


def search_notices(
    conn: sqlite3.Connection,
    query: str = "",
    agency: str | None = None,
) -> list[dict[str, Any]]:
    """Search cached notices."""
    sql = "SELECT * FROM notices WHERE 1=1"
    params: list[Any] = []

    if query:
        sql += " AND (title LIKE ? OR description LIKE ? OR category LIKE ?)"
        q = f"%{query}%"
        params.extend([q, q, q])

    if agency:
        sql += " AND agency LIKE ?"
        params.append(f"%{agency}%")

    sql += " ORDER BY cached_at DESC"
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def search_awards(
    conn: sqlite3.Connection,
    agency: str | None = None,
    supplier: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search cached awards."""
    sql = "SELECT * FROM awards WHERE 1=1"
    params: list[Any] = []

    if agency:
        sql += " AND agency LIKE ?"
        params.append(f"%{agency}%")

    if supplier:
        sql += " AND supplier LIKE ?"
        params.append(f"%{supplier}%")

    sql += f" ORDER BY award_date DESC LIMIT {limit}"
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def get_supplier_stats(conn: sqlite3.Connection, name: str) -> dict[str, Any]:
    """Get aggregate stats for a supplier."""
    row = conn.execute("""
        SELECT supplier,
               COUNT(*) as total_awards,
               SUM(amount) as total_amount,
               AVG(amount) as avg_amount,
               MIN(amount) as min_amount,
               MAX(amount) as max_amount,
               COUNT(DISTINCT agency) as agency_count
        FROM awards
        WHERE supplier LIKE ?
        GROUP BY supplier
    """, (f"%{name}%",)).fetchone()

    return dict(row) if row else {}


def get_agency_stats(conn: sqlite3.Connection, name: str) -> dict[str, Any]:
    """Get aggregate stats for an agency."""
    row = conn.execute("""
        SELECT agency,
               COUNT(*) as total_awards,
               SUM(amount) as total_amount,
               AVG(amount) as avg_amount,
               COUNT(DISTINCT supplier) as supplier_count
        FROM awards
        WHERE agency LIKE ?
        GROUP BY agency
    """, (f"%{name}%",)).fetchone()

    return dict(row) if row else {}
