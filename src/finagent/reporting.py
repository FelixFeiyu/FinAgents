from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict

from .backtest import BacktestMetrics


def write_experiment_report(results: Dict[str, Dict[str, float]], output: str) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# FinAgent Experiment Report",
        "",
        "> Research and simulated backtest only. Not investment advice.",
        "",
        "| Experiment | Cumulative Return | Volatility | Sharpe | Max Drawdown | Cost | HOLD Ratio |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, metrics in results.items():
        lines.append(
            f"| {name} | {metrics['cumulative_return']:.2%} | "
            f"{metrics['annualized_volatility']:.2%} | {metrics['sharpe']:.2f} | "
            f"{metrics['max_drawdown']:.2%} | {metrics['total_cost']:.4%} | "
            f"{metrics['hold_ratio']:.2%} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def metrics_json(metrics: BacktestMetrics) -> str:
    return json.dumps(asdict(metrics), indent=2)

