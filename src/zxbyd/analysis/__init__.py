"""Anomaly detection — probe orchestrator.

High-level entrypoint: probe() runs all heuristics against cached data
and returns a ProbeResult with reason-coded findings.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from zxbyd.models.enums import Confidence
from zxbyd.analysis.heuristics import (
    find_price_anomalies,
    find_repeat_awardees,
    detect_split_contracts,
    network_analysis,
)


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


def probe(
    conn: sqlite3.Connection,
    query: str,
    min_confidence: str = "low",
    max_findings: int = 10,
) -> ProbeResult:
    """Run probe analysis with summary-first, reason-coded findings.

    Searches notices for the query, then runs multiple heuristics
    to detect anomalies.
    """
    if min_confidence not in {"low", "medium", "high"}:
        raise ValueError("min_confidence must be low, medium, or high")
    if max_findings < 0:
        raise ValueError("max_findings must be non-negative")
    from zxbyd.data import search_notices

    notices = search_notices(conn, query=query)
    findings: list[Finding] = []

    if not notices:
        return ProbeResult(
            query=query,
            summary=f"No cached notices found for '{query}'. Run 'zxbyd search notices \"{query}\"' first.",
            data_quality="constrained",
        )

    notices_with_abc = [n for n in notices if n.get("abc") and n["abc"] > 0]

    data_quality = "adequate" if len(notices_with_abc) >= 3 else (
        "limited" if notices_with_abc else "constrained"
    )

    # Heuristic 1: Price anomalies
    anomalies = find_price_anomalies(conn, query)
    for a in anomalies[:max_findings]:
        findings.append(Finding(
            reason_code="PRICE_ANOMALY",
            title=f"Price above reference for {a['unit_type']}: {a['agency']}",
            description=(
                f"{a['agency']} budgeting PHP {a['unit_price']:,.0f}/unit for {a['unit_type']}s "
                f"vs zxbyd reference PHP {a['benchmark']:,.0f}/unit "
                f"({a['reference_spread_pct']:.0f}% above reference)"
            ),
            confidence=Confidence.LOW,
            evidence=[
                f"Ref {a['ref_no']}: {a['title']}",
                f"ABC: PHP {a['abc']:,.0f} for {a['unit_count']} units",
                f"Unit price: PHP {a['unit_price']:,.0f}",
                f"zxbyd reference: PHP {a['benchmark']:,.0f}",
            ],
            false_positive_note=(
                "The zxbyd reference value is an unverified heuristic, not a sourced market price. "
                "ABC may include installation, licensing, warranty, or other items; check the specifications."
            ),
        ))

    # Sort by confidence
    conf_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: conf_order.get(f.confidence.value, 3))

    # Filter by min confidence
    min_conf = conf_order[min_confidence]
    findings = [f for f in findings if conf_order.get(f.confidence.value, 3) <= min_conf]

    summary = (
        f"Found {len(findings)} risk finding(s) across {len(notices)} notice(s) "
        f"for '{query}'. Data quality: {data_quality}."
    )

    return ProbeResult(
        query=query,
        summary=summary,
        data_quality=data_quality,
        findings=findings[:max_findings],
    )


# Re-export for backward compatibility
from zxbyd.analysis.heuristics import (
    find_price_anomalies,
    find_repeat_awardees,
    detect_split_contracts,
    network_analysis,
    extract_units,
    ExtractionResult,
    is_mixed_procurement,
    find_all_quantity_items,
)

__all__ = [
    "probe", "ProbeResult", "Finding",
    "find_price_anomalies", "find_repeat_awardees",
    "detect_split_contracts", "network_analysis",
    "extract_units", "ExtractionResult",
    "is_mixed_procurement", "find_all_quantity_items",
]
