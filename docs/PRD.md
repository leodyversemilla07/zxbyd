# zxbyd — Product Requirements Document

## 1. Overview

**Product name:** zxbyd

**Tagline:** Probe Philippine government procurement. Minimal tool. Serious purpose.

**What it is:** A local-first CLI tool for searching, inspecting, and flagging suspicious patterns in Philippine government procurement data sourced from PhilGEPS (Philippine Government Electronic Procurement System).

**Why it exists:** Public procurement in the Philippines involves billions of pesos annually. Transparency is legally mandated (RA 12009 + IRR), but practical scrutiny tooling is inaccessible to journalists, researchers, civil society, and concerned citizens. zxbyd fills that gap with an explainable, offline-capable, zero-cost tool.

**Legal baseline:** RA 12009 (New Government Procurement Act) + its Implementing Rules and Regulations.

## 2. Users

| Persona | Need |
|---------|------|
| Investigative journalist | Flag suspicious bids for deeper reporting |
| Civil society watchdog | Monitor procurement patterns across agencies |
| Researcher / analyst | Extract structured procurement data for studies |
| Concerned citizen | Quick check on a specific procurement or supplier |
| COA / oversight auditor | Triage signals before formal audit |

## 3. Core Principles

1. **Local-first.** SQLite cache. No cloud dependency. Works offline after first scrape.
2. **Explainable.** Every risk flag traces to evidence fields. Reason codes, not black boxes.
3. **Flag risk, never imply guilt.** Outputs are signals for investigation, not verdicts.
4. **Minimal by default.** `zxbyd` opens a REPL. Depth via flags, not complexity.
5. **Free and open.** No paid APIs, no accounts, no telemetry. MIT license.

## 4. Tech Stack

| Layer | Tool | Why |
|-------|------|-----|
| Runtime | Python 3.11+ | Type hints, modern stdlib |
| CLI Framework | Typer | Modern, type-hint-based, built on Click |
| Networking | httpx | Async-capable, modern HTTP client |
| Scraping | Playwright | Only option for ASP.NET WebForms (JS postback) |
| HTML Parsing | selectolax | 5-30x faster than BeautifulSoup |
| Terminal UI | Rich | Beautiful terminal output |
| Storage | SQLite (stdlib) | Zero-dep, local-first cache |
| Fuzzy Matching | RapidFuzz | Supplier name normalization |
| Packaging | uv | Fastest Python package manager |

## 5. Data Source

**PhilGEPS Notices Site** (https://notices.philgeps.gov.ph/)

- ASP.NET WebForms application
- Search requires clicking "Search" link to activate postback before keyword input
- Stable selectors: `#txtKeyword`, `#btnSearch`
- Budget data often on detail pages, not list pages

## 6. Architecture

```
zxbyd/
├── src/zxbyd/
│   ├── __init__.py            # Package metadata, __version__
│   ├── main.py                # Typer app entrypoint
│   ├── commands/              # CLI command groups
│   │   ├── search.py          # zxbyd search
│   │   ├── detail.py          # zxbyd detail
│   │   ├── awards.py          # zxbyd awards
│   │   ├── profiles.py        # zxbyd profile (agency/supplier/agencies)
│   │   └── analysis.py        # zxbyd analysis (probe/overprice/repeat/split/network)
│   ├── sources/
│   │   └── philgeps.py        # Playwright scraper
│   ├── analysis/
│   │   └── __init__.py        # Heuristic detectors + data classes
│   ├── data/
│   │   └── __init__.py        # SQLite cache layer
│   └── ui/
│       └── __init__.py        # Rich terminal display
├── tests/
├── docs/
│   └── PRD.md
├── pyproject.toml
└── uv.lock
```

## 7. Commands

### Search & Discovery
| Command | Description | Flags |
|---------|-------------|-------|
| `zxbyd search notices <query>` | Search PhilGEPS notices | `--pages`, `--detail`, `--agency`, `--cache-only` |
| `zxbyd search recent` | Recent notices | `--limit` |
| `zxbyd detail show <ref_id>` | Notice details | `--force` |

### Awards & Profiles
| Command | Description | Flags |
|---------|-------------|-------|
| `zxbyd awards list` | Recent awards | `--agency`, `--supplier`, `--limit`, `--cache-only` |
| `zxbyd profile agency <name>` | Agency profile | — |
| `zxbyd profile supplier <name>` | Supplier profile | — |
| `zxbyd profile agencies` | List all entities | `--limit` |

### Anomaly Detection
| Command | Description | Flags |
|---------|-------------|-------|
| `zxbyd analysis probe <query>` | Summary-first risk findings | `--why`, `--min-confidence`, `--max-findings`, `--json` |
| `zxbyd analysis overprice [cat]` | Pricing anomalies | `--threshold` |
| `zxbyd analysis repeat` | Repeat awardees | `--min-count` |
| `zxbyd analysis split <agency>` | Contract splitting | `--gap-days` |
| `zxbyd analysis network <supplier>` | Supplier network | — |

## 8. Reason Codes

- **R1** — Repeat supplier concentration
- **R2** — Near-ABC award pattern
- **R3** — Potential split contracts in short interval
- **R4** — Procurement mode outlier frequency
- **R5** — Abnormal budget-utilization spread
- **R6** — Single-agency dependence risk (supplier)
- **R7** — Sparse/low-confidence data warning
- **R8** — Beneficial ownership disclosure gap

## 9. Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `BIDX_CACHE_DIR` | SQLite cache directory | `~/.zxbyd/` |

## 10. Non-Goals

- Not a legal adjudication engine
- Not a replacement for COA, GPPB, or Ombudsman investigations
- Not a dashboard or web application
- Not a paid/SaaS product
