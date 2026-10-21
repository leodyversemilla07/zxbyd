# zxbyd architecture

## Current implementation

zxbyd is a Python CLI built with Typer. PhilGEPS notices are fetched with
`httpx`, parsed with `selectolax`, converted to local dictionaries, and stored
in SQLite. OCDS-shaped Pydantic models are used for export and selected CLI
flows. This is not currently a full OCDS schema validation or publication
pipeline.

```text
Typer commands
  ├── sources: PhilGEPS HTTP scraping and HTML parsing
  ├── storage: SQLite notice, award, and release-event cache
  ├── analysis: explainable text and price heuristics
  └── ui: Rich terminal output
```

## Storage

The `notices` and `awards` tables retain the flat data used by existing
commands. The `releases` table stores individual release events keyed by
`(ocid, release_id)`, allowing tender and award events for the same process to
coexist. Awards imported more than once are refreshed by reference number and
supplier instead of being counted repeatedly.

The cache lives in `~/.zxbyd/zxbyd.db`. `ZXBYD_CACHE_DIR` selects another
directory; `BIDX_CACHE_DIR` is retained as a legacy alias.

## Analysis limits

Price references are unverified heuristics and should be checked against
equivalent specifications and scope. Findings are low-confidence review leads,
not market-price determinations. Potential split-contract groups use title
similarity and publication-date proximity; they do not establish unlawful
conduct. The tool does not make legal determinations from a fixed ABC
threshold.

PhilGEPS notice statuses are mapped to known OCDS tender status values where
possible. A notice status of “Awarded” does not create an award record because
the public notice page does not necessarily contain supplier and award-value
details.

## Known boundaries

- Award search and agency directory retrieval are not implemented; award data
  can be imported from CSV or JSON.
- Scraper results depend on PhilGEPS page structure and may be incomplete when
  the site changes or requests fail.
- No official OCDS JSON Schema validation is currently run on exports.
