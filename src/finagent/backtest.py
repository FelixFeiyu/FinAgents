"""Pipeline-driven weekly backtest.

Unlike the previous demo (hardcoded return arrays), this walks a price store
week by week, runs the *real* decision pipeline at each step (evidence ->
agents -> optimizer -> risk gate -> decision gate -> state persistence), and
values the applied portfolio against next week's actual closes. Transaction
costs are charged on realized turnover.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .config import RiskConfig, UniverseConfig, load_risk_config, load_universe
from .data import PriceStore, closes_before, evidence_from_prices, synthetic_price_store
from .providers import LLMProvider, MockLLMProvider


@dataclass(frozen=True)
class BacktestMetrics:
    cumulative_return: float
    annualized_volatility: float
    sharpe: float
    max_drawdown: float
    total_cost: float
    hold_ratio: float


def calculate_metrics(
    weekly_returns: Iterable[float],
    weekly_turnovers: Iterable[float],
    hold_count: int,
    cost_bps: float = 15.0,
) -> BacktestMetrics:
    returns = list(weekly_returns)
    turnovers = list(weekly_turnovers)
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    total_cost = 0.0
    net_returns: List[float] = []
    for index, value in enumerate(returns):
        turnover = turnovers[index] if index < len(turnovers) else 0.0
        cost = turnover * cost_bps / 10000
        total_cost += cost
        net = value - cost
        net_returns.append(net)
        equity *= 1.0 + net
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1.0)
    mean = sum(net_returns) / len(net_returns) if net_returns else 0.0
    variance = (
        sum((item - mean) ** 2 for item in net_returns) / len(net_returns)
        if net_returns else 0.0
    )
    volatility = math.sqrt(variance) * math.sqrt(52)
    sharpe = mean * 52 / volatility if volatility else 0.0
    return BacktestMetrics(
        cumulative_return=equity - 1.0,
        annualized_volatility=volatility,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
        total_cost=total_cost,
        hold_ratio=hold_count / len(returns) if returns else 0.0,
    )


@dataclass
class BacktestReport:
    weeks: int
    metrics: BacktestMetrics
    actions: Dict[str, int]
    equity_curve: List[Dict[str, object]] = field(default_factory=list)


def _price_at(store: PriceStore, symbol: str, day) -> Optional[float]:
    closes = closes_before(store, symbol, day)
    return closes[-1] if closes else None


def _portfolio_return(
    store: PriceStore, weights: Dict[str, float], start, end
) -> float:
    total = 0.0
    for symbol, weight in weights.items():
        if symbol == "CASH":
            continue
        begin = _price_at(store, symbol, start)
        finish = _price_at(store, symbol, end)
        if begin and finish and begin > 0:
            total += weight * (finish / begin - 1.0)
    return total


def run_backtest(
    price_store: PriceStore,
    weeks: int = 26,
    output_dir: str = "artifacts/backtest",
    provider: Optional[LLMProvider] = None,
    risk_config: Optional[RiskConfig] = None,
    universe: Optional[UniverseConfig] = None,
) -> BacktestReport:
    from .pipeline import run_pipeline

    risk_config = risk_config or load_risk_config()
    universe = universe or load_universe()
    provider = provider or MockLLMProvider()

    all_days = sorted({str(day) for series in price_store.values() for day, _ in series})
    if not all_days:
        raise ValueError("price store is empty")
    end_day = datetime.fromisoformat(all_days[-1]).date()
    decision_days = [end_day - timedelta(weeks=weeks - 1 - index) for index in range(weeks)]

    returns: List[float] = []
    turnovers: List[float] = []
    actions: Dict[str, int] = {}
    hold_count = 0
    equity = 1.0
    curve: List[Dict[str, object]] = []

    state_file = Path(output_dir) / "portfolio.sqlite"
    if state_file.exists():
        state_file.unlink()
    state_path = str(state_file)
    for index, day in enumerate(decision_days):
        as_of = datetime.combine(day, dt_time(12, 0), tzinfo=timezone.utc)
        evidence = evidence_from_prices(price_store, universe.symbols, as_of)
        result = run_pipeline(
            as_of,
            output_dir=output_dir,
            provider=provider,
            evidence=evidence,
            risk_config=risk_config,
            universe=universe,
            state_path=state_path,
        )
        if index >= len(decision_days) - 1:
            break
        gross = _portfolio_return(
            price_store, dict(result.applied.weights), day, decision_days[index + 1]
        )
        turnover = result.decision.weekly_turnover
        cost = turnover * risk_config.total_cost_bps / 10000
        returns.append(gross)
        turnovers.append(turnover)
        actions[result.decision.action.value] = actions.get(result.decision.action.value, 0) + 1
        if result.decision.action.value == "HOLD":
            hold_count += 1
        equity *= 1.0 + gross - cost
        curve.append(
            {
                "as_of": day.isoformat(),
                "week_number": result.week_number,
                "action": result.decision.action.value,
                "weekly_return_gross": round(gross, 6),
                "turnover": round(turnover, 6),
                "cost": round(cost, 6),
                "equity": round(equity, 6),
            }
        )

    metrics = calculate_metrics(returns, turnovers, hold_count, risk_config.total_cost_bps)
    report = BacktestReport(
        weeks=len(returns), metrics=metrics, actions=actions, equity_curve=curve
    )
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / "backtest-report.json").write_text(
        json.dumps(
            {
                "weeks": report.weeks,
                "metrics": asdict(report.metrics),
                "actions": report.actions,
                "equity_curve": report.equity_curve,
                "disclaimer": "Simulated research backtest only; not investment advice.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return report


def demo_backtest(weeks: int = 12, output_dir: str = "artifacts/backtest-demo") -> BacktestMetrics:
    """Offline deterministic backtest on synthetic prices (no network, no key)."""
    universe = load_universe()
    store = synthetic_price_store(universe.symbols, weeks=weeks + 30)
    report = run_backtest(store, weeks=weeks, output_dir=output_dir, universe=universe)
    return report.metrics
