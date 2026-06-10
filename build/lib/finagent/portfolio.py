from __future__ import annotations

import uuid
from typing import Mapping

from .models import AggregatedView, Portfolio


def turnover(current: Mapping[str, float], candidate: Mapping[str, float]) -> float:
    symbols = set(current) | set(candidate)
    return 0.5 * sum(abs(candidate.get(s, 0.0) - current.get(s, 0.0)) for s in symbols)


class DeterministicOptimizer:
    """Constrained score-to-weight optimizer; replaceable by Black-Litterman/CVXPY."""

    def __init__(self, max_weight: float = 0.10, min_cash: float = 0.05) -> None:
        self.max_weight = max_weight
        self.min_cash = min_cash

    def optimize(
        self,
        views: Mapping[str, AggregatedView],
        current_weights: Mapping[str, float],
        max_turnover: float = 0.20,
    ) -> Portfolio:
        investable = 1.0 - self.min_cash
        positive = {s: max(0.0, v.score) for s, v in views.items()}
        total = sum(positive.values())
        if total <= 0:
            target = {s: w for s, w in current_weights.items() if s != "CASH"}
        else:
            target = {s: min(self.max_weight, investable * score / total) for s, score in positive.items()}

        remaining = investable - sum(target.values())
        ranked = sorted(positive, key=lambda s: (-positive[s], s))
        while remaining > 1e-9:
            # Only names with a positive view absorb spare capacity; anything
            # left over stays in cash instead of leaking into rejected names.
            eligible = [
                s for s in ranked
                if positive[s] > 0 and target.get(s, 0.0) < self.max_weight - 1e-9
            ]
            if not eligible:
                break
            allocation = remaining / len(eligible)
            before = remaining
            for symbol in eligible:
                addition = min(allocation, self.max_weight - target.get(symbol, 0.0))
                target[symbol] = target.get(symbol, 0.0) + addition
                remaining -= addition
            if abs(before - remaining) < 1e-12:
                break
        target["CASH"] = 1.0 - sum(target.values())

        raw_turnover = turnover(current_weights, target)
        if raw_turnover > max_turnover and raw_turnover > 0:
            ratio = max_turnover / raw_turnover
            symbols = set(current_weights) | set(target)
            target = {
                s: current_weights.get(s, 0.0)
                + ratio * (target.get(s, 0.0) - current_weights.get(s, 0.0))
                for s in symbols
            }

        expected_return = sum(
            target.get(symbol, 0.0) * view.score * 1000 for symbol, view in views.items()
        )
        concentration = sum(weight * weight for symbol, weight in target.items() if symbol != "CASH")
        return Portfolio(
            portfolio_id=f"portfolio-{uuid.uuid4()}",
            weights={s: round(w, 10) for s, w in sorted(target.items()) if w > 1e-9},
            expected_return_bps=expected_return,
            expected_volatility=concentration**0.5 * 0.30,
        )

