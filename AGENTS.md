# AGENTS.md

Agent guidance for zxbyd.

## Project overview

- Project: zxbyd
- Purpose: Probe Philippine government procurement with local-first, explainable heuristics
- Stack: Python, Typer CLI, Playwright, selectolax, Rich, SQLite
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

- Entrypoint: `src/zxbyd/main.py` — Typer app with sub-app registration
- Commands: `src/zxbyd/commands/` — search, detail, awards, profiles, analysis, report, cache
- Scraper: `src/zxbyd/sources/` — httpx + selectolax (retry, rate limiting)
- Analysis: `src/zxbyd/analysis/` — heuristics, Finding/ProbeResult dataclasses, BENCHMARKS dict
- Cache: `src/zxbyd/data/` — SQLite with context manager
- Display: `src/zxbyd/ui/` — Rich terminal rendering

## Coding rules

1. Minimalism — small focused changes, depth via flags
2. Explainable — every risk flag traces to evidence
3. Local-first — SQLite cache, no paid dependencies
4. RA 12009 + IRR semantics

## Scraping notes (PhilGEPS)

- ASP.NET WebForms — click Search link before typing
- Stable selectors: `#txtKeyword`, `#btnSearch`
- Budget on detail pages, not list pages
- Retry + fallback to cache on failure
