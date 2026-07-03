"""Anomaly detection — probe orchestrator.

High-level entrypoint: probe() runs all heuristics against cached data
and returns a ProbeResult with reason-coded findings.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from zxbyd.models.enums import Confidence
from zxbyd.models.release import Release
from zxbyd.analysis.benchmarks import lookup_benchmark
from zxbyd.analysis.heuristics import (
    extract_units,
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
            title=f"Overpriced {a['unit_type']}: {a['agency']}",
            description=(
                f"{a['agency']} budgeting ₱{a['unit_price']:,.0f}/unit for {a['unit_type']}s "
                f"vs market benchmark ₱{a['benchmark']:,.0f}/unit "
                f"({a['overcharge_pct']:.0f}% over)"
            ),
            confidence=Confidence.HIGH if a["overcharge_pct"] > 100 else Confidence.MEDIUM,
            evidence=[
                f"Ref {a['ref_no']}: {a['title']}",
                f"ABC: ₱{a['abc']:,.0f} for {a['unit_count']} units",
                f"Unit price: ₱{a['unit_price']:,.0f}",
                f"Market benchmark: ₱{a['benchmark']:,.0f}",
            ],
            false_positive_note=(
                "Could include installation, licensing, or extended warranty. "
                "Check attached specs for justification."
            ),
        ))

    # Heuristic 2: High ABC relative to item type
    for n in notices_with_abc:
        abc = n["abc"]
        result = extract_units(n["title"], n.get("description", ""))

        if result.is_mixed or not result.unit_count or result.unit_count <= 0:
            continue

        unit_price = abc / result.unit_count
        benchmark = lookup_benchmark(result.unit_type)
        if benchmark > 0 and unit_price > benchmark * 1.3:
            findings.append(Finding(
                reason_code="HIGH_UNIT_PRICE",
                title=f"{result.unit_type.title()} at ₱{unit_price:,.0f}/unit",
                description=f"{n['agency']} budgeting ₱{unit_price:,.0f} per {result.unit_type} (benchmark ₱{benchmark:,.0f})",
                confidence=Confidence.MEDIUM,
                evidence=[
                    f"Ref {n['ref_no']}: {n['title']}",
                    f"ABC: ₱{abc:,.0f} for {result.unit_count} {result.unit_type}(s)",
                    f"Unit price: ₱{unit_price:,.0f} vs benchmark ₱{benchmark:,.0f}",
                ],
            ))

    # Heuristic 3: Negotiated procurement for large amounts
    for n in notices_with_abc:
        mode = n.get("mode", "").lower()
        if "negotiated" in mode and n["abc"] and n["abc"] > 500000:
            findings.append(Finding(
                reason_code="NEGOTIATED_LARGE",
                title=f"Negotiated procurement at ₱{n['abc']:,.0f}",
                description=(
                    f"{n['agency']} using negotiated procurement for ₱{n['abc']:,.0f} "
                    f"contract — competitive bidding required above ₱500K per RA 12009"
                ),
                confidence=Confidence.LOW,
                evidence=[
                    f"Ref {n['ref_no']}: {n['title']}",
                    f"Mode: {n.get('mode', 'N/A')}",
                    f"ABC: ₱{n['abc']:,.0f}",
                ],
                false_positive_note=(
                    "May be allowed under specific IRR provisions (e.g., Sec. 53). "
                    "Check solicitation number for the specific exception used."
                ),
            ))

    # Sort by confidence
    conf_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: conf_order.get(f.confidence.value, 3))

    # Filter by min confidence
    min_conf = conf_order.get(min_confidence, 2)
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
)

__all__ = [
    "probe", "ProbeResult", "Finding",
    "find_price_anomalies", "find_repeat_awardees",
    "detect_split_contracts", "network_analysis",
    "extract_units", "ExtractionResult",
]
