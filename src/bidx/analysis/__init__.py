"""Anomaly detection heuristics."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import sqlite3


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ExtractionResult:
    """Result of unit count extraction from notice text."""

    unit_count: int | None = None
    unit_type: str = ""
    confidence: str = "high"  # high = single clean item, medium = inferred, low = mixed/uncertain
    is_mixed: bool = False  # True when ABC covers multiple distinct item types
    items: list[dict[str, Any]] = field(default_factory=list)  # per-item breakdown when mixed


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


def _parse_php_amount(text: str) -> float | None:
    """Parse a PHP amount from description text."""
    if not text:
        return None
    # Match patterns like PHP60,000,000.00 or ₱60,000,000.00 or PhP 60,000,000.00
    match = re.search(r'(?:PHP|PhP|₱)\s*([\d,]+(?:\.\d+)?)', text, re.IGNORECASE)
    if match:
        return float(match.group(1).replace(',', ''))
    return None


def _word_to_int(word: str) -> int | None:
    """Convert word numbers to integers."""
    words = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
        "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
        "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
        "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000,
    }
    return words.get(word.lower().strip())


# Benchmark prices (PHP) — conservative market rates for PH government procurement
# Updated with broader categories and realistic 2025-2026 pricing
BENCHMARKS: dict[str, float] = {
    # Computers
    "laptop": 55000,
    "notebook": 55000,
    "desktop": 40000,
    "computer": 40000,
    "workstation": 80000,
    "all-in-one": 50000,
    "thin client": 25000,
    # Peripherals
    "printer": 30000,
    "scanner": 25000,
    "plotter": 150000,
    "projector": 35000,
    "monitor": 15000,
    "keyboard": 1500,
    "mouse": 800,
    # Networking
    "server": 250000,
    "switch": 50000,
    "router": 30000,
    "access point": 15000,
    "firewall": 150000,
    "rack": 20000,
    "ups": 25000,
    "patch panel": 5000,
    "cable": 15,  # per meter
    # Storage
    "nas": 80000,
    "hard drive": 5000,
    "ssd": 5000,
    # Mobile
    "tablet": 25000,
    "phone": 15000,
    # Security
    "cctv": 50000,
    "camera": 50000,
    "dvr": 30000,
    # Software
    "license": 10000,
    "software": 10000,
    "subscription": 5000,  # per month
    # Furniture
    "table": 5000,
    "chair": 3000,
    "desk": 5000,
    "cabinet": 8000,
    # Generators / Power
    "generator": 150000,
    "aircon": 35000,
    "airconditioner": 35000,
    "air conditioning": 35000,
    # Vehicles
    "vehicle": 1200000,
    "car": 1200000,
    "motorcycle": 80000,
    # Misc IT
    "biometric": 15000,
    "attendance": 15000,
    "pos": 25000,
    "kiosk": 50000,
    # Fallback for unidentified items
    "item": 50000,
    "unit": 50000,
    "lot": 0,  # lot items are heterogeneous, skip benchmarking
}


def _normalize_unit_type(raw: str) -> str:
    """Normalize extracted unit type to a benchmark key.

    Tries longest match first (e.g., 'air conditioning' before 'air').
    Falls back to substring matching against BENCHMARKS keys.
    """
    if not raw:
        return ""

    lower = raw.lower().strip().rstrip("s")  # strip trailing plural

    # Direct match
    if lower in BENCHMARKS:
        return lower

    # Check all benchmark keys as substrings
    for key in sorted(BENCHMARKS.keys(), key=len, reverse=True):
        if key in lower or lower in key:
            return key

    return lower


def _extract_unit_count(title: str, description: str) -> tuple[int | None, str]:
    """Extract unit count from title/description.

    DEPRECATED: Use _extract_units() which returns ExtractionResult.
    Kept for backward compat — returns (count, unit_type) tuple.
    """
    result = _extract_units(title, description)
    return result.unit_count, result.unit_type


# Regex patterns for quantity+item extraction
_PAT_PAREN = re.compile(
    r'(\w+)\s*\((\d[\d,]*)\)\s*(?:UNITS?|pcs?|sets?|units?)\s*(?:OF\s+)?(?:BRAND[- ]?NEW\s+)?([\w][\w\s-]*?)(?:\s+(?:WITH|FOR|AND|,|\.|$))',
    re.IGNORECASE,
)
_PAT_DIGIT = re.compile(
    r'(\d[\d,]*)\s*(?:UNITS?|pcs?|sets?)\s*[-\s]*(?:OF\s+)?(?:BRAND[- ]?NEW\s+)?([\w][\w\s-]*?)(?:\s+(?:WITH|FOR|AND|,|\.|$))',
    re.IGNORECASE,
)
_PAT_WORD = re.compile(
    r'\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)\b\s+(?:UNITS?\s+)?(?:OF\s+)?([\w][\w\s-]*?)(?:\s+(?:WITH|FOR|AND|,|\.|$))',
    re.IGNORECASE,
)


def _find_all_quantity_items(text: str) -> list[tuple[int, str]]:
    """Find ALL quantity+item_type pairs in text.

    Returns list of (count, normalized_type) for every match.
    This is key for detecting mixed procurements.
    """
    pairs = []

    # Digit with parens: "FORTY (40) UNITS OF LAPTOP"
    for m in _PAT_PAREN.finditer(text):
        count = int(m.group(2).replace(',', ''))
        item = _normalize_unit_type(m.group(3))
        if count > 0 and item and item not in ("lot", "unit"):
            pairs.append((count, item))

    # Direct digit: "500 UNITS LAPTOP"
    for m in _PAT_DIGIT.finditer(text):
        count = int(m.group(1).replace(',', ''))
        item = _normalize_unit_type(m.group(2))
        if count > 0 and item and item not in ("lot", "unit"):
            pairs.append((count, item))

    # Word number: "FORTY units of laptop"
    for m in _PAT_WORD.finditer(text):
        count = _word_to_int(m.group(1))
        item = _normalize_unit_type(m.group(2))
        if count and count > 0 and item and item not in ("lot", "unit"):
            pairs.append((count, item))

    return pairs


def _is_mixed_procurement(title: str) -> bool:
    """Detect if a title describes a mixed/bundled procurement.

    Signals:
      - Slash-separated items: "Desktop / Laptop / Tablet"
      - Multiple quantity+item pairs with different types
      - "AND" between quantity+item groups
    """
    # Check for slash-separated items (common in PhilGEPS)
    if "/" in title:
        parts = [p.strip() for p in title.split("/")]
        item_types = set()
        for part in parts:
            for key in BENCHMARKS:
                if key in part.lower():
                    item_types.add(key)
        if len(item_types) >= 2:
            return True

    # Primary signal: multiple quantity+item pairs with DIFFERENT types
    title_pairs = _find_all_quantity_items(title)
    if len(title_pairs) >= 2:
        types = {p[1] for p in title_pairs}
        if len(types) >= 2:
            return True

    # Strong signal: 2+ different benchmark item types mentioned (even without quantities)
    # e.g., "LAPTOPS AND PRINTERS" or "Laptop Computer... Two (2) Units Printer"
    title_lower = title.lower()
    # Exclude "computer" as standalone if paired with specific types (laptop, desktop)
    # since "laptop computer" and "desktop computer" are single items
    found_types = set()
    for key in BENCHMARKS:
        if key in ("computer", "unit", "item", "lot"):
            continue  # too generic
        if key in title_lower:
            found_types.add(key)

    # Special case: "laptop" and "desktop" count as different types
    # but "laptop" + "computer" doesn't (since "laptop computer" is one item)
    if "laptop" in found_types and "desktop" in found_types:
        return True

    # If 2+ non-computer benchmark types found, it's mixed
    if len(found_types) >= 2:
        return True

    # Secondary signal: "X and Y" where X and Y are both benchmark items
    # But skip common false positives like "Supply and Delivery"
    skip_phrases = {"supply and delivery", "installation and configuration",
                    "testing and commissioning", "bids and awards",
                    "design and build", "supply and install"}
    title_lower = title.lower()
    for phrase in skip_phrases:
        title_lower = title_lower.replace(phrase, " ")

    and_parts = re.split(r'\band\b', title_lower)
    if len(and_parts) >= 2:
        # Check if different item types appear in different segments
        segment_types = []
        for part in and_parts:
            types_in_segment = set()
            for key in BENCHMARKS:
                if key in part:
                    types_in_segment.add(key)
            if types_in_segment:
                segment_types.append(types_in_segment)

        # If 2+ segments each have item types, and they differ
        if len(segment_types) >= 2:
            all_types = set()
            for st in segment_types:
                all_types.update(st)
            # Different segments have different types
            if len(all_types) >= 2:
                return True

    return False


def _extract_units(title: str, description: str) -> ExtractionResult:
    """Extract unit information with mixed-procurement awareness.

    Returns ExtractionResult with confidence level and per-item breakdown.
    """
    combined = f"{title} {description}"

    # Step 1: Find ALL quantity+item pairs
    all_pairs = _find_all_quantity_items(combined)

    if not all_pairs:
        return ExtractionResult()

    # Step 2: Detect mixed procurement
    mixed = _is_mixed_procurement(title)

    # If title is clean but combined text has multiple types, still flag
    if not mixed:
        item_types = {p[1] for p in all_pairs}
        if len(item_types) >= 3:
            # Too many different items in combined text — likely mixed
            mixed = True

    # Step 3: If mixed, try to build per-item breakdown
    if mixed and len(all_pairs) >= 2:
        # Group by item type
        by_type: dict[str, int] = {}
        for count, item_type in all_pairs:
            # Deduplicate: only take the first match per type
            if item_type not in by_type:
                by_type[item_type] = count

        items = [{"type": t, "count": c} for t, c in by_type.items()]

        # Use the most specific (longest-named) item type as primary
        primary = max(by_type.keys(), key=len)

        return ExtractionResult(
            unit_count=by_type[primary],
            unit_type=primary,
            confidence="low",
            is_mixed=True,
            items=items,
        )

    # Step 4: Single item — pick the best match
    # Prefer matches from title over description
    title_pairs = _find_all_quantity_items(title)
    if title_pairs:
        count, item_type = title_pairs[0]
        return ExtractionResult(
            unit_count=count,
            unit_type=item_type,
            confidence="high",
            is_mixed=False,
        )

    # Fall back to first match from combined text
    count, item_type = all_pairs[0]
    return ExtractionResult(
        unit_count=count,
        unit_type=item_type,
        confidence="medium",
        is_mixed=False,
    )


def find_price_anomalies(
    conn: sqlite3.Connection,
    category: str = "",
) -> list[dict[str, Any]]:
    """Detect pricing anomalies across agencies.

    Compares unit prices for similar items across agencies.
    Flags when price spread exceeds threshold.
    """
    # Search cached notices for the category
    query = """
        SELECT * FROM notices
        WHERE (title LIKE ? OR description LIKE ? OR category LIKE ?)
        AND abc IS NOT NULL AND abc > 0
        ORDER BY abc DESC
    """
    q = f"%{category}%"
    rows = conn.execute(query, (q, q, q)).fetchall()

    anomalies = []

    for row in rows:
        notice = dict(row)
        abc = notice["abc"]
        title = notice["title"]
        desc = notice.get("description", "")

        result = _extract_units(title, desc)

        # Skip mixed procurements — unit price would be misleading
        if result.is_mixed or not result.unit_count or result.unit_count <= 0:
            continue

        unit_price = abc / result.unit_count

        # Look up benchmark — skip lot-level procurements
        benchmark = BENCHMARKS.get(result.unit_type, 0)
        if benchmark <= 0:
            continue

        overcharge_pct = ((unit_price - benchmark) / benchmark) * 100

        if overcharge_pct > 20:
            anomalies.append({
                "ref_no": notice["ref_no"],
                "title": title,
                "agency": notice["agency"],
                "abc": abc,
                "unit_count": result.unit_count,
                "unit_type": result.unit_type,
                "unit_price": unit_price,
                "benchmark": benchmark,
                "overcharge_pct": overcharge_pct,
                "confidence": result.confidence,
            })

    return anomalies


def find_repeat_awardees(
    conn: sqlite3.Connection,
    min_count: int = 3,
) -> list[dict[str, Any]]:
    """Find suppliers with high award frequency."""
    rows = conn.execute("""
        SELECT supplier, COUNT(*) as count, SUM(amount) as total,
               GROUP_CONCAT(DISTINCT agency) as agencies
        FROM awards
        GROUP BY supplier
        HAVING count >= ?
        ORDER BY count DESC
    """, (min_count,)).fetchall()

    return [dict(r) for r in rows]


def detect_split_contracts(
    conn: sqlite3.Connection,
    agency: str,
    gap_days: int = 30,
) -> list[dict[str, Any]]:
    """Detect potential contract splitting for an agency."""
    # Look for multiple small-value contracts from same agency in short timeframe
    rows = conn.execute("""
        SELECT ref_no, title, agency, abc, published_date
        FROM notices
        WHERE agency LIKE ?
        AND abc IS NOT NULL
        ORDER BY published_date
    """, (f"%{agency}%",)).fetchall()

    notices = [dict(r) for r in rows]
    candidates = []

    for i, n in enumerate(notices):
        if n["abc"] and n["abc"] < 500000:  # Small value threshold
            # Check for nearby contracts
            related = []
            for j, m in enumerate(notices):
                if i != j and m["abc"] and m["abc"] < 500000:
                    related.append(m)
            if len(related) >= 2:
                candidates.append({
                    "notice": n,
                    "related_count": len(related),
                    "total_value": sum(r["abc"] for r in related if r["abc"]),
                })

    return candidates


def network_analysis(
    conn: sqlite3.Connection,
    supplier_name: str,
) -> dict[str, Any]:
    """Analyze supplier network."""
    stats_row = conn.execute("""
        SELECT supplier, COUNT(*) as total_awards, SUM(amount) as total_amount,
               AVG(amount) as avg_amount, COUNT(DISTINCT agency) as agency_count
        FROM awards WHERE supplier LIKE ?
        GROUP BY supplier
    """, (f"%{supplier_name}%",)).fetchone()

    if not stats_row:
        return {"supplier": supplier_name, "found": False}

    result = dict(stats_row)
    result["found"] = True

    # Get agencies this supplier serves
    agencies = conn.execute("""
        SELECT agency, COUNT(*) as count, SUM(amount) as total
        FROM awards WHERE supplier LIKE ?
        GROUP BY agency ORDER BY count DESC
    """, (f"%{supplier_name}%",)).fetchall()

    result["agencies"] = [dict(a) for a in agencies]

    # Get competitors (suppliers serving same agencies)
    competitors = conn.execute("""
        SELECT DISTINCT a2.supplier, COUNT(DISTINCT a2.agency) as shared_agencies
        FROM awards a1
        JOIN awards a2 ON a1.agency = a2.agency AND a2.supplier != a1.supplier
        WHERE a1.supplier LIKE ?
        GROUP BY a2.supplier
        ORDER BY shared_agencies DESC
        LIMIT 10
    """, (f"%{supplier_name}%",)).fetchall()

    result["competitors"] = [dict(c) for c in competitors]

    return result


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

    # Check if notices have ABC data
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
        result = _extract_units(n["title"], n.get("description", ""))

        # Skip mixed procurements
        if result.is_mixed or not result.unit_count or result.unit_count <= 0:
            continue

        unit_price = abc / result.unit_count
        # Flag if unit price exceeds benchmark by >30%
        benchmark = BENCHMARKS.get(result.unit_type, 0)
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
