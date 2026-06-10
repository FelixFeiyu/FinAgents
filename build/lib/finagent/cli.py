from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .backtest import demo_backtest, run_backtest
from .config import load_universe
from .data import (
    DEFAULT_PRICE_STORE,
    ingest_fundamentals,
    ingest_macro,
    ingest_prices,
    load_price_store,
)
from .experiments import run_experiments
from .models import to_dict
from .pipeline import parse_as_of, run_pipeline
from .providers import select_provider
from .reporting import write_experiment_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="finagent")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")

    for name in ("research", "decide"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--as-of", default=datetime.now(timezone.utc).date().isoformat())
        cmd.add_argument("--output-dir", default="artifacts")
        cmd.add_argument("--mode", choices=["mock", "live"], default=None,
                         help="LLM provider; defaults to FINAGENT_MODE env (mock)")
        cmd.add_argument("--price-store", default=DEFAULT_PRICE_STORE)

    ingest = sub.add_parser("ingest", help="fetch real datasets into data/processed/")
    ingest.add_argument("--dataset", choices=["prices", "fundamentals", "macro", "all"],
                        default="prices")
    ingest.add_argument("--source", choices=["yahoo", "alpha_vantage", "synthetic"],
                        default="yahoo", help="price source (prices dataset only)")
    ingest.add_argument("--weeks", type=int, default=260)
    ingest.add_argument("--output", default=DEFAULT_PRICE_STORE)

    backtest = sub.add_parser("backtest", help="pipeline-driven weekly backtest")
    backtest.add_argument("--weeks", type=int, default=26)
    backtest.add_argument("--price-store", default=DEFAULT_PRICE_STORE)
    backtest.add_argument("--output-dir", default="artifacts/backtest")
    backtest.add_argument("--mode", choices=["mock", "live"], default=None)

    experiment = sub.add_parser("experiment")
    experiment.add_argument("--output", default="docs/experiment_reports/mock_mvp.md")
    return parser


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        report = {
            "python": sys.version.split()[0],
            "mode": os.environ.get("FINAGENT_MODE", "mock"),
            "deepseek_key_present": bool(os.environ.get("DEEPSEEK_API_KEY")),
            "price_store_present": Path(DEFAULT_PRICE_STORE).exists(),
            "status": "ready",
        }
        print(json.dumps(report, indent=2))
        return 0
    if args.command in {"research", "decide"}:
        result = run_pipeline(
            parse_as_of(args.as_of),
            args.output_dir,
            provider=select_provider(args.mode),
            price_store_path=args.price_store,
            # research is a read-only analysis; only decide advances the state machine
            persist_state=args.command == "decide",
        )
        print(json.dumps(to_dict(result.decision), indent=2))
        return 0
    if args.command == "ingest":
        universe = load_universe()
        summary = {}
        if args.dataset in {"prices", "all"}:
            store = ingest_prices(universe.symbols, args.source, args.output, args.weeks)
            summary["prices"] = {symbol: len(series) for symbol, series in store.items()}
        if args.dataset in {"fundamentals", "all"}:
            fundamentals = ingest_fundamentals(universe.symbols)
            summary["fundamentals"] = {
                symbol: len(records) for symbol, records in fundamentals.items()
            }
        if args.dataset in {"macro", "all"}:
            macro = ingest_macro()
            summary["macro"] = {ticker: len(series) for ticker, series in macro.items()}
        print(json.dumps(summary, indent=2))
        return 0
    if args.command == "backtest":
        if Path(args.price_store).exists():
            report = run_backtest(
                load_price_store(args.price_store),
                weeks=args.weeks,
                output_dir=args.output_dir,
                provider=select_provider(args.mode),
            )
            print(json.dumps(
                {"weeks": report.weeks, "metrics": asdict(report.metrics),
                 "actions": report.actions}, indent=2,
            ))
        else:
            print(json.dumps(
                {"note": "price store missing; ran synthetic demo backtest",
                 "metrics": asdict(demo_backtest(weeks=args.weeks,
                                                 output_dir=args.output_dir))}, indent=2,
            ))
        return 0
    if args.command == "experiment":
        results = run_experiments()
        report = write_experiment_report(results, args.output)
        print(str(report))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
