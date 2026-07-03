"""Heuristic detectors for procurement anomaly analysis.

Extracts unit counts from notice text, detects mixed procurement,
and runs specific anomaly checks (price, repeat awards, split contracts).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from zxbyd.analysis.benchmarks import BENCHMARKS, lookup_benchmark, get_all_benchmark_keys


@dataclass
class ExtractionResult:
    """Result of unit count extraction from notice text."""

    unit_count: int | None = None
    unit_type: str = ""
    confidence: str = "high"  # high = single clean item, medium = inferred, low = mixed/uncertain
    is_mixed: bool = False  # True when ABC covers multiple distinct item types
    items: list[dict[str, Any]] = field(default_factory=list)  # per-item breakdown when mixed


def _parse_php_amount(text: str) -> float | None:
    """Parse a PHP amount from description text."""
    if not text:
        return None
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
    for key in get_all_benchmark_keys():
        if key in lower or lower in key:
            return key

    return lower


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


def find_all_quantity_items(text: str) -> list[tuple[int, str]]:
    """Find ALL quantity+item_type pairs in text.

    Returns list of (count, normalized_type) for every match.
    Key for detecting mixed procurements.
    """
    pairs = []

    for m in _PAT_PAREN.finditer(text):
        count = int(m.group(2).replace(',', ''))
        item = _normalize_unit_type(m.group(3))
        if count > 0 and item and item not in ("lot", "unit"):
            pairs.append((count, item))

    for m in _PAT_DIGIT.finditer(text):
        count = int(m.group(1).replace(',', ''))
        item = _normalize_unit_type(m.group(2))
        if count > 0 and item and item not in ("lot", "unit"):
            pairs.append((count, item))

    for m in _PAT_WORD.finditer(text):
        count = _word_to_int(m.group(1))
        item = _normalize_unit_type(m.group(2))
        if count and count > 0 and item and item not in ("lot", "unit"):
            pairs.append((count, item))

    return pairs


def is_mixed_procurement(title: str) -> bool:
    """Detect if a title describes a mixed/bundled procurement.

    Signals:
      - Slash-separated items: "Desktop / Laptop / Tablet"
      - Multiple quantity+item pairs with different types
      - "AND" between quantity+item groups
    """
    # Check for slash-separated items
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
    title_pairs = find_all_quantity_items(title)
    if len(title_pairs) >= 2:
        types = {p[1] for p in title_pairs}
        if len(types) >= 2:
            return True

    # Strong signal: 2+ different benchmark item types mentioned
    title_lower = title.lower()
    found_types = set()
    for key in BENCHMARKS:
        if key in ("computer", "unit", "item", "lot"):
            continue
        if key in title_lower:
            found_types.add(key)

    if "laptop" in found_types and "desktop" in found_types:
        return True

    if len(found_types) >= 2:
        return True

    # Secondary signal: "X and Y" where both are benchmark items
    skip_phrases = {"supply and delivery", "installation and configuration",
                    "testing and commissioning", "bids and awards",
                    "design and build", "supply and install"}
    title_lower = title.lower()
    for phrase in skip_phrases:
        title_lower = title_lower.replace(phrase, " ")

    and_parts = re.split(r'\band\b', title_lower)
    if len(and_parts) >= 2:
        segment_types = []
        for part in and_parts:
            types_in_segment = set()
            for key in BENCHMARKS:
                if key in part:
                    types_in_segment.add(key)
            if types_in_segment:
                segment_types.append(types_in_segment)
        if len(segment_types) >= 2:
            all_types = set()
            for st in segment_types:
                all_types.update(st)
            if len(all_types) >= 2:
                return True

    return False


def extract_units(title: str, description: str) -> ExtractionResult:
    """Extract unit information with mixed-procurement awareness.

    Returns ExtractionResult with confidence level and per-item breakdown.
    """
    combined = f"{title} {description}"
    all_pairs = find_all_quantity_items(combined)

    if not all_pairs:
        return ExtractionResult()

    mixed = is_mixed_procurement(title)
    if not mixed:
        item_types = {p[1] for p in all_pairs}
        if len(item_types) >= 3:
            mixed = True

    if mixed and len(all_pairs) >= 2:
        by_type: dict[str, int] = {}
        for count, item_type in all_pairs:
            if item_type not in by_type:
                by_type[item_type] = count
        items = [{"type": t, "count": c} for t, c in by_type.items()]
        primary = max(by_type.keys(), key=len)
        return ExtractionResult(
            unit_count=by_type[primary],
            unit_type=primary,
            confidence="low",
            is_mixed=True,
            items=items,
        )

    title_pairs = find_all_quantity_items(title)
    if title_pairs:
        count, item_type = title_pairs[0]
        return ExtractionResult(
            unit_count=count,
            unit_type=item_type,
            confidence="high",
            is_mixed=False,
        )

    count, item_type = all_pairs[0]
    return ExtractionResult(
        unit_count=count,
        unit_type=item_type,
        confidence="medium",
        is_mixed=False,
    )


def _extract_unit_count(title: str, description: str) -> tuple[int | None, str]:
    """DEPRECATED: compatibility wrapper."""
    result = extract_units(title, description)
    return result.unit_count, result.unit_type


def find_price_anomalies(
    conn: sqlite3.Connection,
    category: str = "",
) -> list[dict[str, Any]]:
    """Detect pricing anomalies across agencies.

    Compares unit prices for similar items across agencies.
    Flags when price spread exceeds threshold.
    """
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

        result = extract_units(title, desc)

        if result.is_mixed or not result.unit_count or result.unit_count <= 0:
            continue

        unit_price = abc / result.unit_count
        benchmark = lookup_benchmark(result.unit_type)
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
        if n["abc"] and n["abc"] < 500000:
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

    agencies = conn.execute("""
        SELECT agency, COUNT(*) as count, SUM(amount) as total
        FROM awards WHERE supplier LIKE ?
        GROUP BY agency ORDER BY count DESC
    """, (f"%{supplier_name}%",)).fetchall()
    result["agencies"] = [dict(a) for a in agencies]

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
