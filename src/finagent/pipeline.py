from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .agents import ResearchGraph, review_holding
from .aggregation import ViewAggregator
from .config import RiskConfig, UniverseConfig, load_risk_config, load_universe
from .data import (
    DEFAULT_PRICE_STORE,
    build_evidence,
    load_fundamentals_store,
    load_macro_store,
    load_price_store,
)
from .decision import DecisionGate
from .evidence import EvidenceLedger, make_evidence
from .models import (
    Action,
    AgentView,
    AggregatedView,
    Decision,
    Evidence,
    Portfolio,
    ThesisStatus,
    to_dict,
)
from .portfolio import DeterministicOptimizer, turnover
from .providers import LLMProvider, select_provider
from .risk import RiskGate
from .state import PortfolioStore
from .temporal_firewall import TemporalFirewall

logger = logging.getLogger("finagent.pipeline")


@dataclass
class PipelineResult:
    run_id: str
    evidence: List[Evidence]
    views: List[AgentView]
    aggregated: Dict[str, AggregatedView]
    current: Portfolio
    candidate: Portfolio
    applied: Portfolio
    decision: Decision
    thesis_statuses: Dict[str, ThesisStatus]
    week_number: int


def demo_evidence(as_of: datetime, symbols: Optional[List[str]] = None) -> List[Evidence]:
    symbols = symbols or load_universe().symbols
    values = [0.80, 0.72, 0.65, 0.54, 0.45, 0.36, 0.25, 0.12, -0.05, -0.15]
    return [
        make_evidence(
            source="demo_point_in_time",
            source_url="local://demo",
            observed_at=as_of - timedelta(days=1),
            available_at=as_of - timedelta(hours=1),
            fetched_at=as_of,
            value=value,
            unit="normalized_score",
            symbol=symbol,
            feature="multi_factor_score",
        )
        for symbol, value in zip(symbols, values)
    ]


def resolve_evidence(
    as_of: datetime,
    symbols: List[str],
    price_store_path: str = DEFAULT_PRICE_STORE,
) -> List[Evidence]:
    """Combine every ingested dataset (prices, SEC fundamentals, macro) found
    next to the price store; fall back to the offline demo evidence."""
    store_file = Path(price_store_path)
    processed = store_file.parent
    price_store = load_price_store(price_store_path) if store_file.exists() else None
    fundamentals = load_fundamentals_store(str(processed / "fundamentals.json"))
    macro_store = load_macro_store(str(processed / "macro.json"))
    if not fundamentals:
        fundamentals = None
    if not macro_store:
        macro_store = None
    items = build_evidence(
        as_of, symbols,
        price_store=price_store, fundamentals=fundamentals, macro_store=macro_store,
    )
    if items:
        sources = sorted({item.source for item in items})
        logger.info("evidence from datasets %s (%d items)", sources, len(items))
        return items
    logger.info("no ingested datasets found; using demo evidence")
    return demo_evidence(as_of, symbols)


def _seed_cash_portfolio() -> Portfolio:
    return Portfolio("portfolio-initial-cash", {"CASH": 1.0}, 0.0, 0.0)


def run_pipeline(
    as_of: datetime,
    output_dir: str = "artifacts",
    provider: Optional[LLMProvider] = None,
    evidence: Optional[List[Evidence]] = None,
    risk_config: Optional[RiskConfig] = None,
    universe: Optional[UniverseConfig] = None,
    price_store_path: str = DEFAULT_PRICE_STORE,
    state_path: Optional[str] = None,
    persist_state: bool = True,
) -> PipelineResult:
    run_id = str(uuid.uuid4())
    risk_config = risk_config or load_risk_config()
    universe = universe or load_universe()
    provider = provider or select_provider()
    evidence = evidence or resolve_evidence(as_of, universe.symbols, price_store_path)

    ledger = EvidenceLedger(str(Path(output_dir) / "evidence.sqlite"))
    store = PortfolioStore(state_path or str(Path(output_dir) / "portfolio.sqlite"))

    firewall = TemporalFirewall()
    visible = firewall.filter(evidence, as_of)
    views = ResearchGraph(provider, ledger).run(run_id, as_of, visible)
    aggregated = ViewAggregator(ledger).aggregate(views)

    current = store.load_latest_portfolio()
    first_run = current is None
    if current is None:
        current = _seed_cash_portfolio()

    # Thesis review runs before optimization: an invalidated-thesis rebuild is
    # granted the larger rebuild turnover budget so the book can actually move.
    previous_scores = store.previous_scores()
    current_scores = {
        symbol: aggregated[symbol].score for symbol in universe.symbols if symbol in aggregated
    }
    thesis_statuses: Dict[str, ThesisStatus] = {
        symbol: review_holding(previous_scores.get(symbol, score), score)
        for symbol, score in current_scores.items()
    }
    invalidated = sum(
        status == ThesisStatus.INVALIDATED for status in thesis_statuses.values()
    )

    # Initial construction is allowed full turnover; weekly runs are capped.
    if first_run:
        max_turnover = 1.0
    elif invalidated >= 2:
        max_turnover = risk_config.max_rebuild_turnover
    else:
        max_turnover = risk_config.max_weekly_turnover
    optimizer = DeterministicOptimizer(
        max_weight=risk_config.max_single_weight, min_cash=risk_config.min_cash
    )
    candidate = optimizer.optimize(aggregated, current.weights, max_turnover=max_turnover)

    risk_gate = RiskGate(
        universe.sectors,
        max_weight=risk_config.max_single_weight,
        max_sector_weight=risk_config.max_sector_weight,
        min_cash=risk_config.min_cash,
        max_volatility=risk_config.max_volatility,
    )
    candidate_risk = risk_gate.check(
        candidate,
        turnover(current.weights, candidate.weights),
        max_turnover,
        stale_symbols=[item.symbol or "" for item in visible if item.stale],
        temporal_violations=firewall.violations,
    )
    current_risk = risk_gate.check(current, 0.0, max_turnover)

    gate = DecisionGate(
        transaction_cost_bps=risk_config.total_cost_bps,
        safety_margin_bps=risk_config.safety_margin_bps,
    )
    decision = gate.decide(
        run_id, as_of, current, candidate, candidate_risk, current_risk, thesis_statuses
    )
    if first_run and candidate_risk.status == "APPROVED":
        decision = _as_initial_rebuild(decision)

    applied = candidate if decision.action in (Action.REBALANCE, Action.REBUILD) else current
    week_number = store.week_number() + 1
    if persist_state:
        week_number = store.save_run(as_of, applied, current.weights, decision, current_scores)

    result = PipelineResult(
        run_id, visible, views, aggregated, current, candidate, applied,
        decision, thesis_statuses, week_number,
    )
    write_audit(result, output_dir, universe)
    logger.info(
        "run %s week=%d action=%s turnover=%.4f",
        run_id, week_number, decision.action.value, decision.weekly_turnover,
    )
    return result


def _as_initial_rebuild(decision: Decision) -> Decision:
    return Decision(
        run_id=decision.run_id,
        decision_time=decision.decision_time,
        execute_after=decision.execute_after,
        action=Action.REBUILD,
        current_portfolio_id=decision.current_portfolio_id,
        candidate_portfolio_id=decision.candidate_portfolio_id,
        net_improvement_bps=decision.net_improvement_bps,
        estimated_transaction_cost_bps=decision.estimated_transaction_cost_bps,
        safety_margin_bps=decision.safety_margin_bps,
        weekly_turnover=decision.weekly_turnover,
        risk_gate_status=decision.risk_gate_status,
        reason_codes=["INITIAL_PORTFOLIO_CONSTRUCTION", *decision.reason_codes],
    )


def write_audit(
    result: PipelineResult, output_dir: str, universe: Optional[UniverseConfig] = None
) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    report = {
        "run_id": result.run_id,
        "week_number": result.week_number,
        "universe_version": universe.universe_version if universe else "unknown",
        "decision": to_dict(result.decision),
        "current": to_dict(result.current),
        "candidate": to_dict(result.candidate),
        "applied": to_dict(result.applied),
        "thesis_statuses": {k: v.value for k, v in result.thesis_statuses.items()},
        "aggregated_views": {k: to_dict(v) for k, v in result.aggregated.items()},
        "agent_views": [to_dict(v) for v in result.views],
        "evidence": [to_dict(v) for v in result.evidence],
        "disclaimer": "Research, backtesting, and paper simulation only; not investment advice.",
    }
    output = path / f"run-{result.run_id}.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    return output


def parse_as_of(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
