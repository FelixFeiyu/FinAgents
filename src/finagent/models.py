from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_dict(value: Any) -> Dict[str, Any]:
    result = asdict(value)
    for key, item in list(result.items()):
        if isinstance(item, datetime):
            result[key] = item.isoformat()
        elif isinstance(item, Enum):
            result[key] = item.value
    return result


class Action(str, Enum):
    HOLD = "HOLD"
    REBALANCE = "REBALANCE"
    REBUILD = "REBUILD"


class ThesisStatus(str, Enum):
    INTACT = "intact"
    WEAKENED = "weakened"
    INVALIDATED = "invalidated"


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    source: str
    source_url: str
    observed_at: datetime
    available_at: datetime
    fetched_at: datetime
    content_hash: str
    value: Any
    unit: str = ""
    stale: bool = False
    symbol: Optional[str] = None
    feature: Optional[str] = None


@dataclass(frozen=True)
class AgentView:
    run_id: str
    agent: str
    as_of: datetime
    symbol: str
    stance: str
    score: float
    confidence: float
    horizon_days: int
    thesis: str
    risks: List[str]
    evidence_ids: List[str]
    missing_data: List[str]
    model: str = "mock-deterministic"
    prompt_version: str = "v1"
    thesis_status: Optional[ThesisStatus] = None

    def __post_init__(self) -> None:
        if not -1 <= self.score <= 1:
            raise ValueError("score must be in [-1, 1]")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be in [0, 1]")


@dataclass(frozen=True)
class AggregatedView:
    symbol: str
    score: float
    confidence: float
    evidence_ids: List[str]
    contributors: List[str]
    disagreement: float


@dataclass(frozen=True)
class Portfolio:
    portfolio_id: str
    weights: Dict[str, float]
    expected_return_bps: float
    expected_volatility: float


@dataclass(frozen=True)
class RiskResult:
    status: str
    violations: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class Decision:
    run_id: str
    decision_time: datetime
    execute_after: datetime
    action: Action
    current_portfolio_id: str
    candidate_portfolio_id: str
    net_improvement_bps: float
    estimated_transaction_cost_bps: float
    safety_margin_bps: float
    weekly_turnover: float
    risk_gate_status: str
    reason_codes: List[str]

