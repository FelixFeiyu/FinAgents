from __future__ import annotations

from typing import Dict, Iterable, Mapping

from .models import Portfolio, RiskResult


class RiskGate:
    def __init__(
        self,
        sectors: Mapping[str, str],
        max_weight: float = 0.10,
        max_sector_weight: float = 0.30,
        min_cash: float = 0.05,
        max_volatility: float = 0.30,
    ) -> None:
        self.sectors = sectors
        self.max_weight = max_weight
        self.max_sector_weight = max_sector_weight
        self.min_cash = min_cash
        self.max_volatility = max_volatility

    def check(
        self,
        portfolio: Portfolio,
        weekly_turnover: float,
        max_turnover: float,
        stale_symbols: Iterable[str] = (),
        temporal_violations: Iterable[str] = (),
    ) -> RiskResult:
        violations = []
        if abs(sum(portfolio.weights.values()) - 1.0) > 1e-6:
            violations.append("WEIGHTS_DO_NOT_SUM_TO_ONE")
        if any(weight < -1e-9 for weight in portfolio.weights.values()):
            violations.append("LONG_ONLY_BREACH")
        if any(
            weight > self.max_weight + 1e-6
            for symbol, weight in portfolio.weights.items()
            if symbol != "CASH"
        ):
            violations.append("SINGLE_NAME_LIMIT")
        if portfolio.weights.get("CASH", 0.0) < self.min_cash - 1e-6:
            violations.append("MINIMUM_CASH")
        sector_weights: Dict[str, float] = {}
        for symbol, weight in portfolio.weights.items():
            sector = self.sectors.get(symbol, "UNKNOWN")
            sector_weights[sector] = sector_weights.get(sector, 0.0) + weight
        if any(w > self.max_sector_weight + 1e-6 for s, w in sector_weights.items() if s != "CASH"):
            violations.append("SECTOR_LIMIT")
        if weekly_turnover > max_turnover + 1e-6:
            violations.append("TURNOVER_LIMIT")
        if portfolio.expected_volatility > self.max_volatility:
            violations.append("VOLATILITY_LIMIT")
        if list(stale_symbols):
            violations.append("STALE_DATA")
        if list(temporal_violations):
            violations.append("TEMPORAL_FIREWALL_VIOLATION")
        return RiskResult(status="APPROVED" if not violations else "REJECTED", violations=violations)

