# FinAgent Portfolio Lab

FinAgent Portfolio Lab is an auditable, weekly multi-agent portfolio research lab based on
[`SPEC_MultiAgent_Portfolio_DeepSeek.md`](SPEC_MultiAgent_Portfolio_DeepSeek.md) (v0.2 As-Built).
See [`docs/TDD_TEST_SUMMARY.md`](docs/TDD_TEST_SUMMARY.md) for the 25-case pytest/TDD summary.

> Research, backtesting, and paper simulation only. This project does not provide investment
> advice or connect to a brokerage.

## Features

- **Real data layer** — four agent-specific datasets under `data/processed/` (see `data/agent_datasets.json`):
  - **technical / critic**: Yahoo daily closes → `prices.json` (`momentum_*`, `risk_*`)
  - **fundamental**: SEC EDGAR XBRL → `fundamentals.json` (`growth_*`, `quality_*`)
  - **macro**: Yahoo ^TNX/^VIX → `macro.json` (`macro_*`)
  - ingest: `finagent ingest --dataset all --source yahoo` (or `synthetic` offline)
- Point-in-time temporal firewall using `available_at`
- Immutable evidence objects and SQLite evidence ledger
- `LLMProvider` selected via `FINAGENT_MODE` (or `--mode`): deterministic mock, or live
  DeepSeek with retries, optional thinking mode, and fence-tolerant JSON parsing
- Fundamental, technical, macro, and critic research graph
- Evidence validation, confidence calibration, and disagreement penalty
- Deterministic constrained optimizer with turnover control
- **Portfolio state machine** — SQLite persists portfolio snapshots, decision history, and
  weekly aggregated scores; `decide` compares the candidate against the *actual* previous
  portfolio, the first run is an `INITIAL_PORTFOLIO_CONSTRUCTION` rebuild, and thesis review
  compares this week's score with last week's
- Hard risk gate and cost-aware `HOLD` / `REBALANCE` / `REBUILD` decision gate, with risk
  limits loaded from `configs/risk.json` and the universe from `configs/universe_us_largecap.json`
- **Pipeline-driven backtest** — `finagent backtest` walks the price store week by week,
  runs the full decision pipeline each week (with state), values the applied portfolio
  against next week's actual closes, charges costs on realized turnover, and writes an
  equity-curve report
- Streamlit dashboard with overview, holdings, decision history, backtest, and agent views tabs
- Auditable JSON run artifact per pipeline run; **25 pytest cases** (see TDD summary)

## Quick Start

The formal target is Python 3.12 and `uv`; the core demo is also compatible with Python 3.9.

```bash
uv sync --no-editable --extra dev   # editable .pth files may be skipped on macOS (hidden flag)
uv run finagent doctor
uv run finagent ingest --dataset all --source yahoo   # prices + SEC + macro
uv run finagent decide --as-of 2026-06-10
uv run finagent backtest --weeks 52          # pipeline-driven weekly backtest
uv run finagent experiment
uv run pytest
```

Offline (no network, no keys): `finagent ingest --source synthetic` generates a deterministic
random-walk price store; without any price store, `decide` falls back to demo evidence.

Live LLM mode: set `DEEPSEEK_API_KEY` and run `finagent decide --mode live`
(or `FINAGENT_MODE=live`).

Dashboard (requires the `full` extra):

```bash
uv run --extra full streamlit run app/dashboard.py
```

Without installation:

```bash
PYTHONPATH=src python3 -m finagent.cli decide --as-of 2026-06-10
PYTHONPATH=src pytest -q
```

Every research run writes `artifacts/run-<run_id>.json`, `artifacts/evidence.sqlite`, and
`artifacts/portfolio.sqlite` (state). Backtests write `artifacts/backtest/backtest-report.json`
plus one audit JSON per simulated week.

## Architecture

```text
Ingest (Yahoo/Alpha Vantage/synthetic) -> Price Store -> Point-in-time Evidence
    -> Temporal Firewall -> Research Graph -> View Aggregator
    -> Deterministic Optimizer -> Hard Risk Gate -> Cost-aware Decision Gate
    -> Portfolio State (SQLite) -> Audit Report / Backtest / Dashboard
```

Agents cannot submit weights, orders, or override the risk gate. Live DeepSeek mode reads only
environment variables shown in `.env.example`; no API key is stored in the repository.

## Known Limits

- The demo universe is frozen but still has survivorship bias.
- The lightweight optimizer is deterministic and constrained, but is not yet full
  Black-Litterman/CVXPY.
- News Agent and FRED/ALFRED macro are not implemented; macro uses Yahoo ^TNX/^VIX.
- The backtest charges linear costs on turnover and ignores intra-week price paths.
