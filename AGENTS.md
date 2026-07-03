# AGENTS.md

Agent guidance for zxbyd.

## Project overview

- Project: zxbyd
- Purpose: Probe Philippine government procurement with local-first, explainable heuristics
- Stack: Python, Typer CLI, Pydantic v2 (OCDS 1.1.5 models), httpx, selectolax, Rich, SQLite
- Data source: PhilGEPS notices site
- Legal baseline: RA 12009 + IRR

## Setup

```bash
uv sync
# Browser support (optional):
uv sync --all-extras && playwright install chromium
```

## Run

```bash
zxbyd --help
zxbyd search notices "laptop"
zxbyd detail show 12905086
zxbyd awards list
zxbyd analysis probe "laptop" --why
```

## Tests

```bash
uv run pytest tests/ -v
```

## Architecture

```
src/zxbyd/
├── main.py              # Typer app with sub-app registration
├── models/              # OCDS Pydantic v2 data models
│   ├── release.py       # Release + ReleasePackage (top-level)
│   ├── tender.py        # Tender stage
│   ├── award.py         # Award stage
│   ├── contract.py      # Contract stage
│   ├── party.py         # Organization / Party models
│   ├── item.py          # Item (goods/services with unit/quantity)
│   ├── common.py        # Value, Period, Address, Identifier
│   └── enums.py         # OCDS codelists + Confidence enum
├── commands/            # Typer CLI command groups
│   ├── search.py        # search notices/recent
│   ├── detail.py        # detail show
│   ├── awards.py        # check, import, status, list
│   ├── profiles.py      # agency, supplier, agencies
│   ├── analysis.py      # probe, overprice, repeat, split, network
│   ├── report.py        # report
│   └── cache.py         # stats, clear, export
├── sources/             # PhilGEPS scraper (httpx + selectolax)
│   └── __init__.py      # search(), get_notice_detail(), to_ocds_release()
├── analysis/            # Anomaly detection heuristics
│   ├── __init__.py      # Probe orchestrator + Finding/ProbeResult
│   ├── benchmarks.py    # BENCHMARKS price dict
│   └── heuristics.py    # Unit extraction, price/repeat/split detection
├── storage/             # OCDS-aware SQLite cache
│   ├── __init__.py      # connection(), upsert_release(), search_releases()
│   └── schema.py        # Schema + migrations
├── data/                # Backward-compatible re-exports from storage/
└── ui/                  # Rich terminal display
    └── __init__.py      # show_notices(), show_detail(), etc.
```

## Coding rules

1. **Minimalism** — small focused changes, depth via flags
2. **Explainable** — every risk flag traces to evidence
3. **Local-first** — SQLite cache, no paid dependencies
4. **RA 12009 + IRR semantics**
5. **OCDS compliance** — new data always maps to OCDS schema

## OCDS Data Model

All procurement data follows the Open Contracting Data Standard v1.1.5:

| PhilGEPS field    | OCDS field                       |
|-------------------|----------------------------------|
| `ref_no`          | `ocid` → `ocds-zxbyd-{ref_no}`  |
| `title`           | `tender.title`                   |
| `agency`          | `parties[].procuringEntity`      |
| `abc`             | `tender.value` (currency=PHP)    |
| `mode`            | `tender.procurementMethodDetails`|
| `published_date`  | `tender.tenderPeriod.startDate`  |
| `closing_date`    | `tender.tenderPeriod.endDate`    |
| `status`          | `tender.status`                  |

Convert a raw PhilGEPS dict to OCDS:
```python
from zxbyd.models.release import Release
release = Release.from_philgeps_dict(raw_notice_dict)
```

Search as OCDS releases:
```python
from zxbyd.storage import connection, search_releases
with connection() as conn:
    releases = search_releases(conn, query="laptop")
```

## Scraping notes (PhilGEPS)

- ASP.NET WebForms — click Search link before typing
- Stable selectors: `#txtKeyword`, `#btnSearch`
- Budget on detail pages, not list pages
- Retry + fallback to cache on failure
