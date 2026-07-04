"""Pytest fixtures for zxbyd tests.

Provides reusable in-memory SQLite databases populated with
realistic PhilGEPS fixture data for offline heuristic testing.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Generator

import pytest

from zxbyd.models.release import Release
from zxbyd.storage.schema import SCHEMA_SQL

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ── Helper: load fixtures ─────────────────────────────────────────

def load_notices_fixture() -> list[dict[str, Any]]:
    """Load the notices fixture JSON file."""
    path = FIXTURES_DIR / "notices.json"
    if not path.exists():
        pytest.skip(f"Fixture file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_awards_fixture() -> list[dict[str, Any]]:
    """Load the awards fixture JSON file."""
    path = FIXTURES_DIR / "awards.json"
    if not path.exists():
        pytest.skip(f"Fixture file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def notices_to_releases() -> list[Release]:
    """Convert all notice fixtures to OCDS Release objects."""
    return [Release.from_philgeps_dict(n) for n in load_notices_fixture()]


# ── Database fixtures ─────────────────────────────────────────────

@pytest.fixture
def in_memory_db() -> Generator[sqlite3.Connection, None, None]:
    """Create a fresh in-memory SQLite database with full schema.

    Yields an sqlite3.Connection with row_factory set to sqlite3.Row.
    The database is clean on every test call.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def populated_db(in_memory_db: sqlite3.Connection) -> sqlite3.Connection:
    """Create an in-memory DB pre-populated with all fixture data.

    Loads both notices and awards fixtures, plus OCDS releases.

    Yields a connection with:
      - notices table: 15 fixture notices
      - awards table: 6 fixture awards
      - releases table: 15 OCDS Release objects
    """
    conn = in_memory_db
    notices = load_notices_fixture()
    awards = load_awards_fixture()

    # Insert notices
    for n in notices:
        conn.execute(
            """INSERT OR IGNORE INTO notices
               (ref_no, title, agency, category, abc, mode,
                area_of_delivery, published_date, closing_date,
                description, status, solicitation_number, cached_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (
                n.get("ref_no", ""),
                n.get("title", ""),
                n.get("agency", ""),
                n.get("category", ""),
                n.get("abc"),
                n.get("mode", ""),
                n.get("area_of_delivery", ""),
                n.get("published_date", ""),
                n.get("closing_date", ""),
                n.get("description", ""),
                n.get("status", ""),
                n.get("solicitation_number", ""),
            ),
        )

    # Insert awards
    for a in awards:
        conn.execute(
            """INSERT OR IGNORE INTO awards
               (ref_no, title, agency, supplier, amount, award_date, mode)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                a.get("ref_no", ""),
                a.get("title", ""),
                a.get("agency", ""),
                a.get("supplier", ""),
                a.get("amount", 0),
                a.get("award_date", ""),
                a.get("mode", ""),
            ),
        )

    # Insert OCDS releases
    from zxbyd.storage import upsert_release
    for n in notices:
        try:
            release = Release.from_philgeps_dict(n)
            upsert_release(conn, release)
        except Exception:
            pass  # skip invalid conversions

    conn.commit()
    return conn


# ── OCDS Release fixtures ─────────────────────────────────────────

@pytest.fixture
def laptop_release() -> Release:
    """Return the laptop fixture (FIXTURE001) as an OCDS Release."""
    return notices_to_releases()[0]


@pytest.fixture
def ocds_releases() -> list[Release]:
    """Return all notices as OCDS Release objects."""
    return notices_to_releases()


# ── Analysis fixture: returns callable helper ─────────────────────

@pytest.fixture
def fixture_notices() -> list[dict[str, Any]]:
    """Load and return the raw notice fixtures."""
    return load_notices_fixture()


@pytest.fixture
def fixture_awards() -> list[dict[str, Any]]:
    """Load and return the raw award fixtures."""
    return load_awards_fixture()
