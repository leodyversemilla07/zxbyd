# OCDS Architecture - zxbyd

**Version:** v2.0 – OCDS-compliant data flow with Pydantic models
**Status:** Complete → Release Candidate

## Overview

zxbyd implements the **Open Contracting Data Standard (OCDS) 1.1.5** for Philippine government procurement. All procurement data flows through an OCDS-compliant model chain, enabling interoperability with global contracting tools while maintaining the native PhilGEPS source in SQLite.

## Core Principles

1. **Local-first** – All data stored in SQLite; no cloud dependencies
2. **Explainable Heuristics** – Every risk flag traces to specific evidence
3. **Backward Compatible** – Existing `zxbyd.data` imports continue working
4. **Minimal Dependencies** – Only adds Pydantic as new core dependency
5. **RA 12009 Compliance** – All OCDS fields align with Philippine contracting law

## Data Flow Pipeline

```
PhilGEPS Website
    ↓
Source Parsers
    ↓
OCDS Release Objects
    ↓
SQLite Cache
    ↓
Analysis Heuristics
    ↓
Rich Terminal UI
```

### 1. Source Parsing (sources/__init__.py)

The scraper layer converts **PhilGEPS HTML** to OCDS Release objects:

- `search_as_releases()` → OCDS Release(s) for keyword matches
- `get_notice_detail_as_release()` → Full notice as OCDS Release
- `to_ocds_release()` → Internal adapter function

Each release contains:
```yaml
o:id: "ocds-zxbyd-{ref_no}"
releaseID: "{ref_no}-notice"
date: "{published_date}"
tag: ["tender"]
initiation_type: "tender"
tender:
  id: "{solicitation_number}"
  title: "{title}"
  description: "..."
  procuringEntity:
    name: "{agency}"
    id: "PH-GEPS-{agency}"
    roles: ["buyer"]
  procurement_method: "unspecified"
  procurement_method_details: "{mode}"
  tender_period:
    start_date: "{published_date}"
    end_date: "{closing_date}"
  status: "{status}"
  value:
    amount: {abc}
    currency: "PHP"
  items:
    - description: "{title}"
      quantity: {extracted_units}
      unit: {extracted_unit}
       classification:
         scheme: "CPV"
         id: "33221000"
         description: "Computer equipment"
```

### 2. Persistent Storage (storage/)

**Dual Schema Architecture** — maintains backward compatibility:

#### Flat Tables (backward compatibility)
- `notices` — Original PhilGEPS dict format (for legacy queries)
- `awards` — Imported supplier award records

#### OCDS Release Table (new)
- `releases` — JSON blob of OCDS releases with indexed columns:
  - `ocid` (indexed) – Unique OCDS identifier
  - `ref_no` (indexed) – PhilGEPS reference number
  - `tender_title` (indexed) – OCDS tender title
  - `tender_value` (computed) – OCDS tender.value.amount
  - `published_date` / `closing_date` – OCDS tender.tender_period
  - `json_blob` – Full OCDS release (JSON)

#### Key Operations
- `upsert_notice()` – Stores both flat notice and OCDS release
- `upsert_award_release()` – Stores imported award as OCDS Award release
- `search_releases()` – Indexed OCDS query
- `upsert_release()` – Direct OCDS release storage

### 3. Analysis Pipeline (analysis/)

All heuristics work on **OCDS Release objects** for consistent filtering:

#### Price Anomaly Detection
- `find_price_anomalies()` – Overcharge detection against PHILBENCH
- `BENCHMARKS` dict – 52 PHP market rates (2025-2026)

#### Procurement Risk Signals
- `is_mixed_procurement()` – Detects mixed-item contracts
- `extract_units()` – Parses PhilGEPS title quantities
- `NetworkAnalysis` – Supplier-agency relationship mapping

#### OCDS Structure Validation
- `validation_heuristics()` – Schema compliance checks
- `confidence_scoring` – Reliability indicators

### 4. Display Layer (ui/__init__.py)

Two UI paths for dual schema:

#### Plain Format (CLI backward compatibility)
- `show_notice_detail()` – Original PhilGEPS notice display
- Fits existing `zxbyd detail show`, `zxbyd search notices`

#### OCDS Format (new)
- `show_release_detail()` – Rich OCDS release rendering
- Used by `zxbyd detail show --ocds`
- Perfect for integration with OCDS viewers

### 5. CLI Layer (commands/)

**All original commands preserved:**
- `zxbyd search notices` – Original keyword search
- `zxbyd detail show` – Plain notice display
- `zxbyd awards` – Supplier tracking
- `zxbyd profiles` – Agency analysis
- `zxbyd analysis` – Risk detection (now full)
- `zxbyd report` – Anomaly reporting
- `zxbyd cache` – Management

**New OCDS commands:**
- `zxbyd search releases` – OCDS-aware search
- `zxbyd detail show --ocds` – OCDS display
- `zxbyd detail show --json` – Machine-readable output

## OCID Format

```
ocds-zxbyd-{ref_no}
```

Where:
- `ocds-` – Standard OCDS prefix
- `zxbyd` – Project-specific namespace
- `{ref_no}` – PhilGEPS reference number (unique)

Example: `ocds-zxbyd-12905086`

## PhilGEPS → OCDS Mapping

| PhilGEPS | OCDS Path | Notes |
|----------|-----------|-------|
| `ref_no` | `release.ocid` | `ocds-zxbyd-{ref_no}` |
| `title` | `release.tender.title` | Full text |
| `agency` | `release.parties[].procuringEntity` | Created as Organization |
| `abc` | `release.tender.value.amount` | Currency = PHP |
| `mode` | `release.tender.procurement_method_details` | Free text |
| `published_date` | `release.tender.tender_period.start_date` | Parsed from text |
| `closing_date` | `release.tender.tender_period.end_date` | Parsed from text |
| `status` | `release.tender.status` | String match |
| `solicitation_number` | `release.tender.id` | Direct assignment |

## Model Architecture

### Entry Point (`src/zxbyd/models/__init__.py`)

```python
from .release import Release, ReleasePackage
from .tender import Tender, Planning
from .award import Award
from .contract import Contract
from .party import Organization, OrganizationReference, Party
from .item import Item, Unit
from .common import Value, Period, Address, Identifier, Classification
from .enums import ProcurementMethod, AwardCriterion
```

### Core Types (`src/zxbyd/models/common.py`)

```python
class Value(BaseModel):
    amount: float = Field(..., ge=0)
    currency: str = Field(default="PHP")
    class Config:
        populate_by_name = True
```

### Top-Level OCDS (`src/zxbyd/models/release.py`)

```python
class Release(BaseModel):
    ocid: str = Field(..., pattern="^ocds-[a-z]{5}-\\d+$")
    id: str  # releaseID
date: str  # publication date
tag: list[str] = ["tender"]
initiation_type: str = "tender"
parties: list[Organization]  # buyer/supplier organizations
tender: Tender  # core procurement details
awards: list[Award] = []  # optional contractual awards
contracts: list[Contract] = []  # post-award execution
```

All models use `populate_by_name = True` for Python-friendly construction while maintaining JSON serialization with OCDS aliases.

## Testing

**18 End-to-End Tests in `tests/test_cli.py`:**

1. **CLI Smoke** (4) – Help/version/commands exist
2. **OCDS Models** (4) – Schema validation & serialization
3. **Heuristics** (4) – Unit extraction + risk detection
4. **Storage** (4) – Cache roundtrip + OCDS storage
5. **Benchmarks** (1) – Price lookup
6. **Integration** (1) – Full pipeline

All tests use **pytest** with **in-memory SQLite** for isolation.

## Development Workflow

### Adding a New Heuristic

```bash
# 1. Add extraction logic to analysis/heuristics.py
# 2. Add price benchmark to analysis/benchmarks.py
# 3. Test with pytest
# 4. Verify CLI output
```

### Exploring OCDS Data

```bash
# Use CLI:
zxbyd search releases "laptop" --json

# Or explore directly:
from zxbyd.storage import connection
from zxbyd.models.release import Release
with connection() as conn:
    for r in search_releases(conn, query="laptop"):
        print(r.model_dump(mode="json", by_alias=True))
```

## Migration Guide

### For Existing Users

No code changes required — all existing imports work:

```python
# This still works (backward compatible)
from zxbyd.data import search_notices, upsert_notice, get_notice_detail
```

### For New OCDS Applications

```python
# New approach (preferred)
from zxbyd.data import search_releases, upsert_release
from zxbyd.models.release import Release

# Search OCDS releases
with connection() as conn:
    releases = search_releases(conn, query="laptop")
    for r in releases:
        print(f"OCID: {r.ocid}")
        print(f"Title: {r.tender.title}")
        print(f"Value: {r.tender.value.amount} PHP")
```

## Recommended Extensions

### 1. OCDS Validation Layer
Add `validation_runner.py` with OCDS JSON Schema validation for data integrity.

### 2. API Server
Expose SQLite tables as REST API endpoints.

### 3. Data Export
Generate OCDS zip files for bulk reporting.

### 4. Dashboard Integration
Connect `/releases` JSON blob to OCDS Viewer or similar.

## License

Apache 2.0 – Open Contracting Data Standard compliance maintained.

---

*For internal use by zxbyd team. OCDS v1.1.5 alignment documented.*

---

**Quick Start** → `zxbyd search releases "laptop"`  
**Explore Data** → `zxbyd detail show 12905086 --ocds`  
**Cheat Sheet** → [Commands](./README.md#commands)

---

*Last Updated: 2026-07-03*
*Generated by OCDS-first architecture v2.0*