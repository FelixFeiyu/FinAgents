from datetime import datetime, timedelta, timezone

from finagent.aggregation import ViewAggregator
from finagent.decision import DecisionGate
from finagent.evidence import EvidenceLedger, make_evidence
from finagent.models import Action, AgentView, Portfolio, RiskResult, ThesisStatus
from finagent.portfolio import DeterministicOptimizer
from finagent.risk import RiskGate
from finagent.temporal_firewall import TemporalFirewall


NOW = datetime(2026, 6, 10, tzinfo=timezone.utc)


def test_temporal_firewall_blocks_future_data():
    past = make_evidence("test", "local://", NOW, NOW - timedelta(hours=1), NOW, 1)
    future = make_evidence("test", "local://", NOW, NOW + timedelta(hours=1), NOW, 2)
    firewall = TemporalFirewall()
    assert firewall.filter([past, future], NOW) == [past]
    assert len(firewall.violations) == 1


def test_view_without_evidence_is_invalid():
    ledger = EvidenceLedger()
    view = AgentView("run", "technical", NOW, "AAPL", "bullish", 0.8, 0.8, 30, "x", [], [], [])
    assert ViewAggregator(ledger).aggregate([view]) == {}


def test_optimizer_is_deterministic_and_respects_limits():
    ledger = EvidenceLedger()
    evidence = make_evidence("test", "local://", NOW, NOW, NOW, 1, symbol="AAPL")
    ledger.add(evidence)
    views = [
        AgentView("run", "technical", NOW, symbol, "bullish", 0.8, 0.8, 30, "x", [], [evidence.evidence_id], [])
        for symbol in ["AAPL", "MSFT", "JPM", "XOM", "UNH", "AMZN", "GOOGL", "META", "NVDA", "COST"]
    ]
    aggregated = ViewAggregator(ledger).aggregate(views)
    current = {symbol: 0.095 for symbol in aggregated}
    current["CASH"] = 0.05
    optimizer = DeterministicOptimizer()
    one = optimizer.optimize(aggregated, current)
    two = optimizer.optimize(aggregated, current)
    assert one.weights == two.weights
    assert max(w for s, w in one.weights.items() if s != "CASH") <= 0.10
    assert one.weights["CASH"] >= 0.05


def test_risk_gate_rejects_extreme_agent_result():
    portfolio = Portfolio("bad", {"AAPL": 0.95, "CASH": 0.05}, 1000, 0.1)
    result = RiskGate({"AAPL": "Technology", "CASH": "CASH"}).check(portfolio, 0.2, 0.2)
    assert result.status == "REJECTED"
    assert "SINGLE_NAME_LIMIT" in result.violations


def test_decision_gate_hold_and_risk_rebalance():
    current = Portfolio("current", {"AAPL": 0.10, "CASH": 0.90}, 20, 0.1)
    candidate = Portfolio("candidate", {"AAPL": 0.10, "CASH": 0.90}, 25, 0.1)
    approved = RiskResult("APPROVED")
    gate = DecisionGate()
    hold = gate.decide("run", NOW, current, candidate, approved, approved, {"AAPL": ThesisStatus.INTACT})
    assert hold.action == Action.HOLD
    breach = gate.decide(
        "run", NOW, current, candidate, approved, RiskResult("REJECTED", ["SINGLE_NAME_LIMIT"]),
        {"AAPL": ThesisStatus.INTACT},
    )
    assert breach.action == Action.REBALANCE


def test_rebuild_requires_multiple_invalidated_theses():
    current = Portfolio("current", {"AAPL": 0.10, "MSFT": 0.10, "CASH": 0.80}, 20, 0.1)
    candidate = Portfolio("candidate", {"JPM": 0.10, "XOM": 0.10, "CASH": 0.80}, 50, 0.1)
    approved = RiskResult("APPROVED")
    decision = DecisionGate().decide(
        "run", NOW, current, candidate, approved, approved,
        {"AAPL": ThesisStatus.INVALIDATED, "MSFT": ThesisStatus.INVALIDATED},
    )
    assert decision.action == Action.REBUILD


def test_current_risk_breach_never_falls_back_to_hold():
    current = Portfolio("current", {"AAPL": 0.95, "CASH": 0.05}, 20, 0.1)
    candidate = Portfolio("candidate", {"MSFT": 0.95, "CASH": 0.05}, 50, 0.1)
    rejected = RiskResult("REJECTED", ["SINGLE_NAME_LIMIT"])
    decision = DecisionGate().decide(
        "run", NOW, current, candidate, rejected, rejected, {"AAPL": ThesisStatus.INTACT}
    )
    assert decision.action == Action.REBALANCE
    assert "RISK_REDUCING_FALLBACK_REQUIRED" in decision.reason_codes
