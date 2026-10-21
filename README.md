# zxbyd

[![CI](https://github.com/leodyversemilla07/zxbyd/actions/workflows/ci.yml/badge.svg)](https://github.com/leodyversemilla07/zxbyd/actions/workflows/ci.yml)

Probe Philippine government procurement.

Minimal tool. Serious purpose.

- Local-first procurement scrutiny
- Explainable risk flags (not verdicts)
- RA 12009 + IRR baseline
- OCDS-shaped Pydantic models for structured exports

## Install

```bash
uv sync
# Scraping currently uses httpx; the browser extra is optional for future use.
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
zxbyd analysis watch "DICT" --markdown
zxbyd analysis compare "DICT" "DepEd"
```

## Architecture

```
src/zxbyd/
├── main.py              # Typer CLI entrypoint
├── models/              # OCDS-shaped Pydantic data models
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
│   ├── benchmarks.py    # Unverified reference prices for heuristic review
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
export ZXBYD_CACHE_DIR=/path/to/dir
```

`BIDX_CACHE_DIR` remains supported for existing setups.

## OCDS Compatibility

zxbyd uses Pydantic v2 models shaped around the [Open Contracting Data Standard (OCDS)](https://standard.open-contracting.org/) 1.1 release. The project does not currently validate exports against the official OCDS JSON Schema. PhilGEPS notice pages also do not provide award details for every notice, so an “Awarded” status alone is not exported as an award record.

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

The model provides an interoperability starting point; validate exports against the official schema before treating them as publishable OCDS data.

## Analysis limits

Price references in zxbyd are unverified heuristic values, not sourced market prices. Price findings are low-confidence review leads and may compare unlike specifications or costs included in an ABC. Split-contract findings are based on similar titles published close together and are not legal determinations. zxbyd does not currently flag procurement methods as unlawful based on a single fixed ABC threshold.

## License

MIT
