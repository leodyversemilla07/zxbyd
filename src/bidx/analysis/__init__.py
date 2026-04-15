"""Anomaly detection heuristics."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Finding:
    """A single risk finding from probe analysis."""

    reason_code: str
    title: str
    description: str
    confidence: Confidence
    evidence: list[str] = field(default_factory=list)
    false_positive_note: str = ""


@dataclass
class ProbeResult:
    """Result of a probe analysis."""

    query: str
    summary: str
    data_quality: str  # "adequate" | "limited" | "constrained"
    findings: list[Finding] = field(default_factory=list)


def find_price_anomalies(
    conn: Any,
    category: str = "",
) -> list[dict[str, Any]]:
    """Detect pricing anomalies across agencies.

    Args:
        conn: SQLite connection.
        category: Partial category name to filter.

    Returns:
        List of anomaly dicts.
    """
    # TODO: implement
    # Compare similar items across agencies
    # Flag when price spread exceeds threshold
    return []


def find_repeat_awardees(
    conn: Any,
    min_count: int = 3,
) -> list[dict[str, Any]]:
    """Find suppliers with high award frequency.

    Args:
        conn: SQLite connection.
        min_count: Minimum award count to flag.

    Returns:
        List of awardee stats dicts.
    """
    # TODO: implement
    return []


def detect_split_contracts(
    conn: Any,
    agency: str,
    gap_days: int = 30,
) -> list[dict[str, Any]]:
    """Detect potential contract splitting.

    Args:
        conn: SQLite connection.
        agency: Agency name to analyze.
        gap_days: Max days between related contracts.

    Returns:
        List of split-contract candidate dicts.
    """
    # TODO: implement
    return []


def network_analysis(
    conn: Any,
    supplier_name: str,
) -> dict[str, Any]:
    """Analyze supplier network.

    Args:
        conn: SQLite connection.
        supplier_name: Supplier to analyze.

    Returns:
        Network analysis dict.
    """
    # TODO: implement
    return {}


def probe(
    conn: Any,
    query: str,
    min_confidence: str = "low",
    max_findings: int = 10,
) -> ProbeResult:
    """Run probe analysis with summary-first, reason-coded findings.

    Args:
        conn: SQLite connection.
        query: Search keywords.
        min_confidence: Minimum confidence filter.
        max_findings: Cap on findings.

    Returns:
        ProbeResult with findings and data quality gate.
    """
    # TODO: implement
    return ProbeResult(
        query=query,
        summary="Not yet implemented.",
        data_quality="constrained",
    )
