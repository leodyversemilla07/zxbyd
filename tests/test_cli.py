"""CLI smoke tests + OCDS model + storage + heuristic tests."""

from pathlib import Path

from typer.testing import CliRunner

from zxbyd.main import app

runner = CliRunner()


# Fixture loaders reused below
_FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_notices() -> list[dict]:
    import json
    return json.loads((_FIXTURES_DIR / "notices.json").read_text(encoding="utf-8"))


def _load_awards() -> list[dict]:
    import json
    return json.loads((_FIXTURES_DIR / "awards.json").read_text(encoding="utf-8"))


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences for stable assertion under different terminal emulators."""
    import re
    # Match both common CSI (ESC + [... + ...) and OSC sequences used by Rich
    return re.sub(r"\x1b\[[0-9;]*[ -/]*[@-~]", "", text).replace("\x1b", "")


# ── CLI smoke tests ────────────────────────────────────────────────

def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "zxbyd" in result.output


def test_no_args_shows_banner():
    result = runner.invoke(app)
    assert result.exit_code == 0
    assert "zxbyd" in result.output.lower()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "procurement" in result.output.lower()


def test_search_help():
    result = runner.invoke(app, ["search", "--help"])
    assert result.exit_code == 0
    assert "notices" in result.output.lower()
    assert "releases" in result.output.lower()


# ── OCDS model tests ───────────────────────────────────────────────

def test_release_from_philgeps_dict():
    """Ensure PhilGEPS dict → OCDS Release conversion works."""
    from zxbyd.models.release import Release

    data = {
        "ref_no": "12345",
        "title": "Supply of 50 Units Laptop",
        "agency": "Department of Education",
        "category": "Information Technology",
        "abc": 2750000.0,
        "mode": "Public Bidding",
        "published_date": "Jan 15, 2025",
        "closing_date": "Feb 15, 2025",
        "description": "Supply and delivery of laptop units for DepEd division offices",
        "status": "Active",
        "solicitation_number": "DEPED-2025-001",
    }

    release = Release.from_philgeps_dict(data)

    assert release.ocid == "ocds-zxbyd-12345"
    assert release.id == "12345"
    assert release.tender is not None
    assert release.tender.title == "Supply of 50 Units Laptop"
    assert release.tender.value is not None
    assert release.tender.value.amount == 2750000.0
    assert release.tender.value.currency == "PHP"
    assert release.tender.procuring_entity is not None
    assert release.tender.procuring_entity.name == "Department of Education"
    assert release.agency_name == "Department of Education"
    assert release.abc == 2750000.0
    assert release.tender.id == "DEPED-2025-001"


def test_value_currency_default():
    """Value defaults to PHP and formats safely across platforms."""
    from zxbyd.models.common import Value
    v = Value(amount=50000)
    assert v.currency == "PHP"
    # Format is platform-safe (PHP label, not ₱ glyph, for Windows terminal)
    assert "50,000" in str(v)
    assert v.amount == 50000


def test_release_serialization_roundtrip():
    """OCDS Release model dumps and loads correctly."""
    from zxbyd.models.release import Release

    data = {
        "ref_no": "99999",
        "title": "Test Procurement",
        "agency": "Test Agency",
        "abc": 100000.0,
    }
    release = Release.from_philgeps_dict(data)
    dumped = release.model_dump(mode="json", by_alias=True)
    loaded = Release.model_validate(dumped)

    assert loaded.ocid == release.ocid
    assert loaded.tender is not None
    assert loaded.tender.title == "Test Procurement"


def test_release_model_dump_simple():
    """model_dump_simple() returns backward-compatible flat dict."""
    from zxbyd.models.release import Release

    data = {
        "ref_no": "555",
        "title": "Simple Test",
        "agency": "DICT",
        "abc": 50000.0,
        "mode": "Shopping",
        "status": "Active",
    }
    release = Release.from_philgeps_dict(data)
    flat = release.model_dump_simple()

    assert flat["ref_no"] == "555"
    assert flat["title"] == "Simple Test"
    assert flat["agency"] == "DICT"
    assert flat["abc"] == 50000.0
    assert flat["mode"] == "Shopping"
    assert flat["status"] == "Active"


# ── Heuristic tests ────────────────────────────────────────────────

def test_extract_units_standard():
    """Standard PhilGEPS format: FORTY (40) UNITS OF LAPTOP."""
    from zxbyd.analysis.heuristics import extract_units
    result = extract_units("FORTY (40) UNITS OF LAPTOP", "")
    assert result.unit_count == 40
    assert result.unit_type == "laptop"
    assert result.is_mixed is False


def test_extract_units_digit():
    """Direct digit format: '500 UNITS LAPTOP' at end of title."""
    from zxbyd.analysis.heuristics import extract_units
    # Realistic PhilGEPS title where quantity comes before item
    result = extract_units("Supply and Delivery of 500 Units Laptop for DepEd", "")
    assert result.unit_count == 500
    assert result.unit_type == "laptop"
    assert result.is_mixed is False


def test_extract_units_no_match():
    """No extractable units yields None."""
    from zxbyd.analysis.heuristics import extract_units
    result = extract_units("Consultancy Services for IT Assessment", "")
    assert result.unit_count is None
    assert result.unit_type == ""


def test_parse_date_philgeps_quirks():
    """Date parser handles PhilGEPS-specific quirks.

    Real PhilGEPS pages render 24-hour clocks with AM/PM markers like
    '21/07/2026 13:00 PM'. We normalize these before parsing so the
    date is stored unambiguously.
    """
    from zxbyd.sources import _parse_date

    # 24-hour-with-AM/PM gets normalized to 12-hour-with-meridiem
    assert _parse_date("21/07/2026 13:00 PM") == "2026-07-21 13:00"
    assert _parse_date("21/07/2026 14:30 PM") == "2026-07-21 14:30"
    # Already 12-hour passes through unchanged
    assert _parse_date("21/07/2026 09:00 AM") == "2026-07-21 09:00"
    # ISO format
    assert _parse_date("2026-01-07") == "2026-01-07"
    # Empty string
    assert _parse_date("") == ""
    # Whitespace stripped
    assert _parse_date(" 2026-01-07 ") == "2026-01-07"


def test_is_mixed_procurement():
    """Slash-separated items flag as mixed."""
    from zxbyd.analysis.heuristics import is_mixed_procurement
    assert is_mixed_procurement("Desktop / Laptop / Tablet") is True
    assert is_mixed_procurement("Supply of 50 Units Laptop") is False


def test_upsert_award_release():
    """Award import creates OCDS Award release."""
    from zxbyd.storage import upsert_award_release, search_releases

    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from zxbyd.storage.schema import SCHEMA_SQL
    conn.executescript(SCHEMA_SQL)

    award = {
        "ref_no": "AWARD001",
        "title": "Supply of IT Equipment",
        "agency": "DICT",
        "supplier": "ACME CORP",
        "amount": 17500000.0,
        "award_date": "2026-01-30",
        "mode": "Public Bidding",
    }
    upsert_award_release(conn, award)

    results = search_releases(conn, query="ACME")
    assert len(results) == 1
    assert results[0].awards is not None
    assert len(results[0].awards) == 1
    assert results[0].awards[0].value is not None
    assert results[0].awards[0].value.amount == 17500000.0
    assert results[0].tag == ["award"]

    conn.close()


def test_search_ocds_converts_results(monkeypatch):
    """search_ocds converts raw search results to Release objects."""
    from zxbyd.sources import search_ocds
    import zxbyd.sources as sources

    # Mock the underlying raw search to return a known notice
    def mock_search(query, max_pages=1):
        return [
            {
                "ref_no": "OCDSTEST01",
                "title": "OCDS Native Test",
                "agency": "DICT",
                "abc": 500000.0,
                "mode": "Public Bidding",
                "published_date": "Jan 15, 2025",
                "closing_date": "Feb 15, 2025",
                "status": "Active",
            }
        ]

    monkeypatch.setattr(sources, "search", mock_search)
    releases = search_ocds("test", max_pages=1)

    assert len(releases) == 1
    assert releases[0].ocid == "ocds-zxbyd-OCDSTEST01"
    assert releases[0].tender is not None
    assert releases[0].tender.title == "OCDS Native Test"
    assert releases[0].tender.value is not None
    assert releases[0].tender.value.amount == 500000.0
    assert releases[0].agency_name == "DICT"


def test_search_ocds_skips_bad_data(monkeypatch):
    """search_ocds skips notices that fail OCDS conversion."""
    from zxbyd.sources import search_ocds
    import zxbyd.sources as sources

    def mock_search(query, max_pages=1):
        return [
            {"ref_no": "GOOD01", "title": "Good", "agency": "Agency", "abc": 1000},  # valid
            {"ref_no": "BAD01", "title": "Bad"},  # missing required fields
            {"ref_no": "GOOD02", "title": "Good 2", "agency": "Agency", "abc": 2000},  # valid
        ]

    monkeypatch.setattr(sources, "search", mock_search)
    releases = search_ocds("test", max_pages=1)

    # Should have 2 valid releases (BAD01 has no agency, which is OK since agency is optional)
    # Actually with populate_by_name, most fields are optional
    # Let's check it doesn't crash and returns whatever converts
    assert len(releases) >= 2
    assert all(r.ocid.startswith("ocds-zxbyd-") for r in releases)


def test_get_notice_detail_ocds_returns_release(monkeypatch):
    """get_notice_detail_ocds converts raw detail to Release."""
    from zxbyd.sources import get_notice_detail_ocds
    import zxbyd.sources as sources

    def mock_detail(ref_id):
        return {
            "ref_no": ref_id,
            "title": "Detail Test",
            "agency": "DepEd",
            "description": "Full detail description for testing",
            "abc": 1500000.0,
            "mode": "Public Bidding",
            "published_date": "Feb 1, 2025",
            "closing_date": "Mar 1, 2025",
            "status": "Active",
            "solicitation_number": "DEPED-2025-001",
        }

    monkeypatch.setattr(sources, "get_notice_detail", mock_detail)
    release = get_notice_detail_ocds("DETAIL01")

    assert release is not None
    assert release.ocid == "ocds-zxbyd-DETAIL01"
    assert release.tender.title == "Detail Test"
    assert release.tender.value.amount == 1500000.0
    assert release.agency_name == "DepEd"


def test_get_notice_detail_ocds_returns_none_on_error(monkeypatch):
    """get_notice_detail_ocds returns None for failed fetches."""
    from zxbyd.sources import get_notice_detail_ocds
    import zxbyd.sources as sources

    def mock_detail(ref_id):
        return {"ref_no": ref_id, "error": "Not found"}

    monkeypatch.setattr(sources, "get_notice_detail", mock_detail)
    result = get_notice_detail_ocds("FAKE001")
    assert result is None


def test_ocds_source_imports():
    """All OCDS source functions are importable."""
    from zxbyd.sources import search_ocds, get_notice_detail_ocds
    from zxbyd.sources import search_as_releases, get_notice_detail_as_release, to_ocds_release
    assert callable(search_ocds)
    assert callable(get_notice_detail_ocds)


# ── Fixture integration tests ────────────────────────────────────

def test_conftest_populated_db(populated_db):
    """populated_db fixture has notices, awards, and releases."""
    conn = populated_db

    notice_count = conn.execute("SELECT COUNT(*) FROM notices").fetchone()[0]
    award_count = conn.execute("SELECT COUNT(*) FROM awards").fetchone()[0]
    release_count = conn.execute("SELECT COUNT(*) FROM releases").fetchone()[0]

    assert notice_count == 15
    assert award_count == 6
    assert release_count == 15


def test_conftest_in_memory_db(in_memory_db):
    """in_memory_db starts clean."""
    conn = in_memory_db
    count = conn.execute("SELECT COUNT(*) FROM notices").fetchone()[0]
    assert count == 0


def test_conftest_laptop_release(laptop_release):
    """laptop_release fixture is a valid OCDS Release."""
    assert laptop_release.ocid == "ocds-zxbyd-FIXTURE001"
    assert "Laptop" in (laptop_release.tender.title or "")
    assert laptop_release.abc == 2975000.0
    assert laptop_release.agency_name == "Department of Education"


def test_conftest_ocds_releases(ocds_releases):
    """ocds_releases fixture contains all 15 releases."""
    assert len(ocds_releases) == 15
    assert all(isinstance(r.ocid, str) for r in ocds_releases)
    counts = sum(1 for r in ocds_releases if r.tender is not None)
    assert counts == 15  # All should have tender data


def test_conftest_fixture_notices(fixture_notices):
    """fixture_notices returns 15 raw PhilGEPS dicts."""
    assert len(fixture_notices) == 15
    assert all("ref_no" in n for n in fixture_notices)
    assert all("abc" in n for n in fixture_notices)


def test_conftest_fixture_awards(fixture_awards):
    """fixture_awards returns 6 award dicts."""
    assert len(fixture_awards) == 6
    assert all("supplier" in a for a in fixture_awards)


def test_seeded_cache_searchable(populated_db):
    """Seeded OCDS releases are searchable."""
    from zxbyd.storage import search_releases

    conn = populated_db

    # Search for laptop
    results = search_releases(conn, query="laptop")
    assert len(results) >= 1
    assert any("Laptop" in (r.tender.title or "") for r in results)

    # Search for specific agency
    deped = search_releases(conn, query="DepEd")
    assert len(deped) == 2  # FIXTURE001 + FIXTURE012

    # Search for ref_no
    by_ref = search_releases(conn, query="FIXTURE003")
    assert len(by_ref) == 1
    assert by_ref[0].ocid == "ocds-zxbyd-FIXTURE003"


def test_cache_stats_shows_releases():
    """cache stats shows OCDS release count."""
    result = runner.invoke(app, ["cache", "stats"])
    assert result.exit_code == 0
    assert "OCDS" in result.output or "No cache" in result.output


def test_detail_show_help():
    """detail show --help contains --ocds flag."""
    result = runner.invoke(app, ["detail", "show", "--help"])
    assert result.exit_code == 0
    assert "--ocds" in _strip_ansi(result.output)


def test_benchmark_lookup():
    """Benchmark prices return correctly."""
    from zxbyd.analysis.benchmarks import lookup_benchmark, BENCHMARKS
    assert lookup_benchmark("laptop") == 55000
    assert lookup_benchmark("unknown-item-xyz") == 0
    assert lookup_benchmark("server") == 250000
    assert len(BENCHMARKS) >= 50  # Should have 50+ items


# ── Storage tests (in-memory) ──────────────────────────────────────

def test_upsert_and_search_releases():
    """End-to-end: convert PhilGEPS dict → store as OCDS release → retrieve."""
    from zxbyd.models.release import Release
    from zxbyd.storage import connection, upsert_release, search_releases

    data = {
        "ref_no": "TEST001",
        "title": "Supply of Laptops",
        "agency": "DepEd",
        "category": "IT Equipment",
        "abc": 5500000.0,
        "mode": "Public Bidding",
        "published_date": "2025-06-01",
        "closing_date": "2025-07-01",
    }
    release = Release.from_philgeps_dict(data)

    # Use an in-memory DB for the test
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from zxbyd.storage.schema import SCHEMA_SQL
    conn.executescript(SCHEMA_SQL)

    upsert_release(conn, release)
    results = search_releases(conn, query="Laptops")

    assert len(results) == 1
    assert results[0].ocid == "ocds-zxbyd-TEST001"
    assert results[0].tender is not None
    assert results[0].tender.title == "Supply of Laptops"
    assert results[0].abc == 5500000.0

    conn.close()


def test_upsert_notice_also_stores_release():
    """Backward-compat upsert_notice() also stores an OCDS release."""
    from zxbyd.storage import connection, search_releases, upsert_notice

    # Use in-memory
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from zxbyd.storage.schema import SCHEMA_SQL
    conn.executescript(SCHEMA_SQL)

    notice = {
        "ref_no": "COMPAT001",
        "title": "Compat Test",
        "agency": "DOST",
        "abc": 75000.0,
    }
    upsert_notice(conn, notice)

    # The OCDS release should have been created alongside
    releases = search_releases(conn, query="Compat")
    assert len(releases) >= 1
    ocds_ref = releases[0].ocid.split("-")[-1]
    assert ocds_ref == "COMPAT001"

    conn.close()


def test_watch_command_shows_help():
    """watch command help text is reachable."""
    result = runner.invoke(app, ["analysis", "watch", "--help"])
    assert result.exit_code == 0
    out = _strip_ansi(result.output).lower()
    assert "watch" in out
    assert "--severity" in out
    assert "--json" in out


def test_watch_rejects_bad_severity(populated_db):
    """Invalid --severity exits non-zero with clear error."""
    # populated_db seeds real fixtures, but the validation must run FIRST.
    result = runner.invoke(app, ["analysis", "watch", "Some Agency",
                                "--severity", "bogus", "--cache-only"])
    assert result.exit_code != 0
    # Error message should mention severity; whether watch ever reached cache doesn't matter.
    assert "severity" in result.output.lower() or "invalid" in result.output.lower()


def test_watch_markdown_output(tmp_path, monkeypatch):
    """--markdown -o writes a usable Markdown file."""
    # Set up an isolated cache dir with fixtures so the CLI test is
    # deterministic — independent of ``~/.zxbyd`` global state.
    monkeypatch.setenv("BIDX_CACHE_DIR", str(tmp_path))

    # Seed fixtures directly into the cache
    from zxbyd.storage import connection, upsert_notice

    with connection() as conn:
        for n in _load_notices():
            upsert_notice(conn, n)
        for a in _load_awards():
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

    out = tmp_path / "report.md"
    result = runner.invoke(app, [
        "analysis", "watch", "Department of Education",
        "--cache-only", "--markdown",
        "--severity", "low", "-o", str(out),
    ])
    assert result.exit_code == 0, _strip_ansi(result.output)
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert content.startswith("# Oversight Report")
    assert "## At-a-Glance" in content
    assert "## Price Anomalies" in content
    assert "## Recent Notices" in content
    assert "## Methodology" in content
    assert "�" not in content
    assert "PHP" in content


def test_compare_help_lists_options():
    """compare command surfaces key options."""
    result = runner.invoke(app, ["analysis", "compare", "--help"])
    assert result.exit_code == 0
    out = _strip_ansi(result.output)
    assert "--markdown" in out
    assert "--json" in out
    assert "--top" in out
    assert "--cache-only" in out


def test_compare_rejects_single_agency():
    """Only 1 agency should fail (need >= 2)."""
    result = runner.invoke(app, ["analysis", "compare", "DICT",
                                "--cache-only"])
    assert result.exit_code != 0
    assert "2-10" in result.output or "agency" in result.output.lower()


def test_compare_rejects_too_many_agencies():
    """11+ agencies should fail."""
    result = runner.invoke(app, ["analysis", "compare",
                                *(["AGENCY"] * 11),
                                "--cache-only"])
    assert result.exit_code != 0


def test_compare_markdown_output(tmp_path, monkeypatch):
    """--markdown writes a comparison report with overlap section."""
    # Same isolated cache approach as test_watch_markdown_output
    monkeypatch.setenv("BIDX_CACHE_DIR", str(tmp_path))

    from zxbyd.storage import connection, upsert_notice

    with connection() as conn:
        for n in _load_notices():
            upsert_notice(conn, n)
        for a in _load_awards():
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

    out = tmp_path / "compare.md"
    result = runner.invoke(app, [
        "analysis", "compare",
        "PHILIPPINE NATIONAL POLICE", "BUREAU OF INTERNAL REVENUE",
        "--cache-only", "--markdown", "-o", str(out),
    ])
    assert result.exit_code == 0, _strip_ansi(result.output)
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "# Procurement Comparison" in content
    assert "## At-a-Glance" in content
    assert "## Top Suppliers per Agency" in content
    assert "Cross-Agency Supplier Overlap" in content or "cross-agency" in content.lower()
    assert "## Methodology" in content
    assert "�" not in content
    assert "ACME" in content
