# zxbyd

Probe Philippine government procurement.

Minimal tool. Serious purpose.

- Local-first procurement scrutiny
- Explainable risk flags (not verdicts)
- RA 12009 + IRR baseline
- **OCDS-compliant** data models (Open Contracting Data Standard v1.1.5)

## Install

```bash
uv sync
# For browser/scraper support:
uv sync --all-extras && playwright install chromium
```

## Usage

```bash
# Show version
zxbyd --version

# Search notices
zxbyd search notices "laptop"
zxbyd search notices "server" --pages 3 --detail

# Notice details
zxbyd detail show 12905086

# Awards
zxbyd awards list
zxbyd awards list --agency "DICT"

# Profiles
zxbyd profile agency "DICT"
zxbyd profile supplier "ACME CORPORATION"
zxbyd profile agencies

# Analysis
zxbyd analysis probe "laptop"
zxbyd analysis probe "laptop" --why --min-confidence medium
zxbyd analysis overprice "laptop" --threshold 150
zxbyd analysis repeat --min-count 3
zxbyd analysis split "DICT" --gap-days 30
zxbyd analysis network "ACME CORPORATION"
```

## Architecture

```
src/zxbyd/
├── main.py              # Typer CLI entrypoint
├── models/              # OCDS-compliant Pydantic data models
│   ├── release.py       # Release + ReleasePackage (top-level OCDS)
│   ├── tender.py        # Tender stage
│   ├── award.py         # Award stage
│   ├── contract.py      # Contract stage
│   ├── party.py         # Organization / Party models
│   ├── item.py          # Item (goods/services)
│   ├── common.py        # Value, Period, Address, etc.
│   └── enums.py         # OCDS codelists + Confidence enum
├── commands/            # Typer CLI command groups
├── sources/             # PhilGEPS scraper (httpx + selectolax)
├── analysis/            # Anomaly detection heuristics
│   ├── benchmarks.py    # Market price benchmarks
│   ├── heuristics.py    # Unit extraction, price anomalies, etc.
│   └── __init__.py      # Probe orchestrator + Finding/ProbeResult
├── storage/             # OCDS-aware SQLite cache
│   └── schema.py        # Schema + migrations
├── data/                # Backward-compat re-exports from storage/
└── ui/                  # Rich terminal display
```

## Cache

Data stored at `~/.zxbyd/zxbyd.db` with both original flat schema and OCDS JSON. Override with:

```bash
export BIDX_CACHE_DIR=/path/to/dir
```

## OCDS Compatibility

zxbyd uses **Pydantic v2** models that follow the [Open Contracting Data Standard (OCDS)](https://standard.open-contracting.org/) v1.1.5 schema:

| PhilGEPS field    | OCDS mapping                    |
|-------------------|---------------------------------|
| `ref_no`          | `ocid` → `ocds-zxbyd-{ref_no}` |
| `title`           | `tender.title`                  |
| `agency`          | `parties[].procuringEntity`     |
| `abc`             | `tender.value` (currency=PHP)   |
| `mode`            | `tender.procurementMethod`      |
| `published_date`  | `tender.tenderPeriod.startDate` |
| `closing_date`    | `tender.tenderPeriod.endDate`   |
| `description`     | `tender.description`            |
| `status`          | `tender.status`                 |
| `solicitation_no` | `tender.id`                     |

The OCDS data model enables interoperability with global procurement analysis tools (Kingfisher, OCDS Kit, etc.) and aligns with PS-DBM's commitment to OCDS adoption under RA 12009.

## License

MIT
