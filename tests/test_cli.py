"""CLI smoke tests + OCDS model + storage + heuristic tests."""

from typer.testing import CliRunner

from zxbyd.main import app

runner = CliRunner()


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
    """Value defaults to PHP."""
    from zxbyd.models.common import Value
    v = Value(amount=50000)
    assert v.currency == "PHP"
    assert str(v) == "₱50,000.00"


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


def test_cache_stats_shows_releases():
    """cache stats shows OCDS release count."""
    result = runner.invoke(app, ["cache", "stats"])
    assert result.exit_code == 0
    assert "OCDS" in result.output or "No cache" in result.output


def test_detail_show_help():
    """detail show --help contains --ocds flag."""
    result = runner.invoke(app, ["detail", "show", "--help"])
    assert result.exit_code == 0
    assert "--ocds" in result.output


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
