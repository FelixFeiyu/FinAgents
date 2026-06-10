from dataclasses import asdict
from typing import Dict

from .backtest import calculate_metrics


def run_experiments() -> Dict[str, Dict[str, float]]:
    common_returns = [0.005, -0.003, 0.004, 0.002, -0.001, 0.005, 0.001, 0.003]
    configurations = {
        "no_llm_factor": ([0.18, 0.10, 0.10, 0.08, 0.10, 0.08, 0.10, 0.08], 0),
        "single_agent": ([0.18, 0.00, 0.12, 0.00, 0.08, 0.10, 0.00, 0.08], 3),
        "multi_agent": ([0.18, 0.00, 0.08, 0.00, 0.00, 0.10, 0.00, 0.05], 4),
        "without_critic": ([0.20, 0.05, 0.15, 0.05, 0.10, 0.15, 0.05, 0.10], 0),
        "forced_weekly_rebalance": ([0.20] * 8, 0),
    }
    return {
        name: asdict(calculate_metrics(common_returns, turnovers, holds))
        for name, (turnovers, holds) in configurations.items()
    }

