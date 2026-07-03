"""OCDS-aware SQLite cache layer.

Provides:
- Context manager for DB connections (`connection()`)
- OCDS release upsert/search (`upsert_release`, `search_releases`)
- Backward-compatible helpers (`upsert_notice`, `search_notices`)
- Supplier/agency stats
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

from zxbyd.models.release import Release
from zxbyd.storage.schema import SCHEMA_SQL, run_migrations


def get_cache_dir() -> Path:
    """Get cache directory, respecting BIDX_CACHE_DIR env var."""
    if env := os.environ.get("BIDX_CACHE_DIR"):
        return Path(env)
    return Path.home() / ".zxbyd"


def get_db_path() -> Path:
    """Get SQLite database path."""
    return get_cache_dir() / "zxbyd.db"


def _init_db(conn: sqlite3.Connection) -> None:
    """Initialize database schema and run migrations."""
    conn.executescript(SCHEMA_SQL)
    run_migrations(conn)


@contextmanager
def connection() -> Generator[sqlite3.Connection, None, None]:
    """Get a database connection (context manager).

    Usage:
        with storage.connection() as conn:
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


# ── OCDS Release operations ────────────────────────────────────────

def upsert_release(conn: sqlite3.Connection, release: Release | dict) -> None:
    """Insert or update an OCDS Release in the cache.

    Accepts either a Release model instance or a raw dict.
    """
    if isinstance(release, Release):
        release_dict = release.model_dump(mode="json", by_alias=True)
        ocid = release.ocid
        ref_no = release.id
        agency = release.agency_name
        category = (
            release.tender.main_procurement_category
            if release.tender and release.tender.main_procurement_category
            else ""
        )
        abc = release.abc
        mode = (
            release.tender.procurement_method_details or release.tender.procurement_method or ""
            if release.tender else ""
        )
        status = release.tender.status if release.tender else ""
        published_date = (
            release.tender.tender_period.start_date
            if release.tender and release.tender.tender_period
            else ""
        )
        closing_date = (
            release.tender.tender_period.end_date
            if release.tender and release.tender.tender_period
            else ""
        )
    else:
        # Raw dict path (backward compat / direct)
        release_dict = release
        ref_no = release.get("ref_no", "") or release.get("id", "")
        ocid = release.get("ocid", "") or f"ocds-zxbyd-{ref_no}" if ref_no else ""
        agency = release.get("agency", "")
        category = release.get("category", "")
        abc = release.get("abc")
        mode = release.get("mode", "")
        status = release.get("status", "")
        published_date = release.get("published_date", "")
        closing_date = release.get("closing_date", "")

    conn.execute("""
        INSERT INTO releases (ocid, ref_no, release_json, agency, category, abc,
                              mode, status, published_date, closing_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ocid) DO UPDATE SET
            release_json=excluded.release_json,
            agency=excluded.agency,
            category=excluded.category,
            abc=COALESCE(excluded.abc, releases.abc),
            mode=COALESCE(excluded.mode, releases.mode),
            status=COALESCE(NULLIF(excluded.status, ''), releases.status),
            published_date=excluded.published_date,
            closing_date=excluded.closing_date,
            cached_at=datetime('now')
    """, (
        ocid, ref_no,
        json.dumps(release_dict, default=str, ensure_ascii=False),
        agency, category, abc, mode, status, published_date, closing_date,
    ))


def search_releases(
    conn: sqlite3.Connection,
    query: str = "",
    agency: str | None = None,
    limit: int = 100,
) -> list[Release]:
    """Search cached OCDS releases.

    Returns list of Release model instances.
    """
    sql = "SELECT release_json FROM releases WHERE 1=1"
    params: list[Any] = []

    if query:
        sql += " AND (release_json LIKE ? OR agency LIKE ? OR category LIKE ?)"
        q = f"%{query}%"
        params.extend([q, q, q])

    if agency:
        sql += " AND agency LIKE ?"
        params.append(f"%{agency}%")

    sql += " ORDER BY cached_at DESC"
    if limit:
        sql += f" LIMIT {limit}"

    results = []
    for row in conn.execute(sql, params).fetchall():
        try:
            data = json.loads(row["release_json"])
            results.append(Release.model_validate(data))
        except (json.JSONDecodeError, Exception):
            continue

    return results


# ── Backward-compatible original API ───────────────────────────────

def upsert_notice(conn: sqlite3.Connection, notice: dict[str, Any]) -> None:
    """Insert or update a notice in the cache (original flat schema).

    Also stores an OCDS release alongside for forward compatibility.
    """
    conn.execute("""
        INSERT INTO notices (ref_no, title, agency, category, abc, mode,
                           area_of_delivery, published_date, closing_date,
                           description, documents, status, solicitation_number)
        VALUES (:ref_no, :title, :agency, :category, :abc, :mode,
                :area_of_delivery, :published_date, :closing_date,
                :description, :documents, :status, :solicitation_number)
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
            status=COALESCE(NULLIF(excluded.status, ''), notices.status),
            solicitation_number=COALESCE(NULLIF(excluded.solicitation_number, ''), notices.solicitation_number),
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
        "status": notice.get("status", ""),
        "solicitation_number": notice.get("solicitation_number", ""),
    })

    # Also store as OCDS release
    try:
        release = Release.from_philgeps_dict(notice)
        upsert_release(conn, release)
    except Exception:
        pass  # Non-critical — original cache still works


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
    """Search cached notices (original flat dict format)."""
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


def upsert_award_release(conn: sqlite3.Connection, award: dict[str, Any]) -> None:
    """Store an imported award as an OCDS Award release.

    Expects a dict with keys: ref_no, title, agency, supplier, amount,
    award_date, mode. Creates an OCDS Award inside a Release with
    tag=['award'], and stores it in the releases table.
    """
    from zxbyd.models.release import Release
    from zxbyd.models.award import Award as AwardModel
    from zxbyd.models.party import Organization, OrganizationReference
    from zxbyd.models.common import Value

    ref_no = award.get("ref_no", "")
    ocid = f"ocds-zxbyd-{ref_no}" if ref_no else ""

    supplier_name = award.get("supplier", "")
    supplier_ref = None
    parties: list[Organization] = []

    agency_name = award.get("agency", "")
    if agency_name:
        parties.append(Organization(
            id=f"PH-GEPS-{agency_name.replace(' ', '-')[:30]}",
            name=agency_name,
            roles=["buyer"],
        ))

    if supplier_name:
        supplier_ref = OrganizationReference(
            name=supplier_name,
            id=f"PH-GEPS-{supplier_name.replace(' ', '-')[:30]}",
        )
        parties.append(Organization(
            id=f"PH-GEPS-{supplier_name.replace(' ', '-')[:30]}",
            name=supplier_name,
            roles=["supplier"],
        ))

    amount = award.get("amount")
    award_value = Value(
        amount=float(amount) if amount else 0.0,
        currency="PHP",
    ) if amount else None

    award_model = AwardModel(
        id=ref_no,
        title=award.get("title", ""),
        date=award.get("award_date", ""),
        value=award_value,
        suppliers=[supplier_ref] if supplier_ref else [],
    )

    release = Release(
        ocid=ocid,
        id=f"{ref_no}-award",
        date=award.get("award_date", ""),
        tag=["award"],
        initiation_type="tender",
        parties=parties,
        awards=[award_model],
    )

    upsert_release(conn, release)
