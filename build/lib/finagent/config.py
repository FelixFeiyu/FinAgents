"""Configuration loading.

Risk limits and the investable universe live in ``configs/*.json``. Code reads
those files instead of hardcoding values; built-in defaults keep the package
usable when the files are absent (e.g. inside tests running from a tmp dir).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_RISK_PATH = "configs/risk.json"
DEFAULT_UNIVERSE_PATH = "configs/universe_us_largecap.json"

FALLBACK_SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "XOM", "UNH", "COST"]
FALLBACK_SECTORS = {
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology",
    "AMZN": "Consumer", "GOOGL": "Communication", "META": "Communication",
    "JPM": "Financials", "XOM": "Energy", "UNH": "Healthcare", "COST": "Consumer",
    "CASH": "CASH",
}


@dataclass(frozen=True)
class RiskConfig:
    max_single_weight: float = 0.10
    max_sector_weight: float = 0.30
    min_cash: float = 0.05
    max_weekly_turnover: float = 0.20
    max_rebuild_turnover: float = 0.40
    transaction_cost_bps: float = 10.0
    slippage_bps: float = 5.0
    safety_margin_bps: float = 10.0
    max_volatility: float = 0.30

    def __post_init__(self) -> None:
        if not 0 < self.max_single_weight <= 1:
            raise ValueError("max_single_weight must be in (0, 1]")
        if not 0 < self.max_sector_weight <= 1:
            raise ValueError("max_sector_weight must be in (0, 1]")
        if not 0 <= self.min_cash < 1:
            raise ValueError("min_cash must be in [0, 1)")
        if not 0 < self.max_weekly_turnover <= 1:
            raise ValueError("max_weekly_turnover must be in (0, 1]")
        if self.max_weekly_turnover > self.max_rebuild_turnover:
            raise ValueError("max_rebuild_turnover must be >= max_weekly_turnover")
        for name in ("transaction_cost_bps", "slippage_bps", "safety_margin_bps"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0")

    @property
    def total_cost_bps(self) -> float:
        return self.transaction_cost_bps + self.slippage_bps


@dataclass(frozen=True)
class UniverseConfig:
    universe_version: str
    symbols: List[str]
    sectors: Dict[str, str]


def load_risk_config(path: Optional[str] = None) -> RiskConfig:
    file = Path(path or DEFAULT_RISK_PATH)
    if not file.exists():
        return RiskConfig()
    data = json.loads(file.read_text(encoding="utf-8"))
    known = {item.name for item in fields(RiskConfig)}
    return RiskConfig(**{key: value for key, value in data.items() if key in known})


def load_universe(path: Optional[str] = None) -> UniverseConfig:
    file = Path(path or DEFAULT_UNIVERSE_PATH)
    if not file.exists():
        return UniverseConfig("builtin-fallback-v1", list(FALLBACK_SYMBOLS), dict(FALLBACK_SECTORS))
    data = json.loads(file.read_text(encoding="utf-8"))
    symbols = list(data.get("symbols") or FALLBACK_SYMBOLS)
    sectors = dict(data.get("sectors") or FALLBACK_SECTORS)
    sectors.setdefault("CASH", "CASH")
    return UniverseConfig(
        universe_version=str(data.get("universe_version", "unknown")),
        symbols=symbols,
        sectors=sectors,
    )
