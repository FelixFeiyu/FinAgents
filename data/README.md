# Data Layout

Four research agents each consume a dedicated dataset under `data/`. See
`agent_datasets.json` for the authoritative mapping.

| Agent | Processed file | Raw cache | Real source |
|-------|----------------|-----------|-------------|
| **technical** | `processed/prices.json` | `raw/yahoo/` | Yahoo daily closes → `momentum_*` |
| **fundamental** | `processed/fundamentals.json` | `raw/sec/` | SEC EDGAR XBRL → `growth_*`, `quality_*` |
| **macro** | `processed/macro.json` | `raw/yahoo_macro/` | Yahoo `^TNX`, `^VIX` → `macro_*` |
| **critic** | `processed/prices.json` (shared) | `raw/yahoo/` | Same prices → `risk_*` drawdown |

## Ingest

```bash
# All real datasets (network; SEC needs SEC_USER_AGENT in env)
finagent ingest --dataset all --source yahoo

# Offline deterministic bundle for tests / CI
finagent ingest --dataset all --source synthetic

# Individual datasets
finagent ingest --dataset prices --source yahoo
finagent ingest --dataset fundamentals
finagent ingest --dataset macro
```

After ingest, `data/processed/manifest.json` records row counts and feature coverage.

Raw and processed files are gitignored. Only this README and `agent_datasets.json` are
committed. Every normalized evidence record includes `source`, `observed_at`,
`available_at`, `fetched_at`, content hash, and stale status.

## Point-in-time rules

- **Prices / critic / technical**: close on day D is available at D+1 00:00 UTC.
- **Fundamentals**: available at filing date + 1 day (SEC `filed` field).
- **Macro**: same as prices; macro features are replicated onto every symbol in the universe.
