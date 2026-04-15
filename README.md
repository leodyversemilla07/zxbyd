# zxbyd

Probe Philippine government procurement.

Minimal tool. Serious purpose.

- Local-first procurement scrutiny
- Explainable risk flags (not verdicts)
- RA 12009 + IRR baseline

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

## Cache

Data stored at `~/.zxbyd/zxbyd.db`. Override with:

```bash
export BIDX_CACHE_DIR=/path/to/dir
```

## License

MIT
