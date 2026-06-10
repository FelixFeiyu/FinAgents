"""TDD red suite: behaviors the merged project should have but does not yet.

Each test documents a real gap:
1. `research` must be read-only; only `decide` advances the portfolio state machine.
2. Mock agents must differentiate by role given role-relevant features.
3. `ingest_prices` must reject unknown sources with a clear ValueError.
4. RiskConfig must validate its limits at construction time.
5. A thesis-driven REBUILD must use the rebuild turnover budget from
   configs/risk.json instead of being capped by the weekly turnover limit.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from finagent.cli import main
from finagent.config import RiskConfig, UniverseConfig
from finagent.data import ingest_prices
from finagent.evidence import make_evidence
from finagent.models import Action, Decision, Portfolio, ThesisStatus
from finagent.pipeline import run_pipeline
from finagent.providers import MockLLMProvider
from finagent.state import PortfolioStore

WEEK1 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
WEEK2 = datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def test_research_is_read_only_but_decide_persists(tmp_path: Path):
    """`research` analyses without advancing state; `decide` advances it."""
    main(["research", "--as-of", "2026-06-08", "--output-dir", str(tmp_path)])
    store = PortfolioStore(str(tmp_path / "portfolio.sqlite"))
    assert store.week_number() == 0
    assert store.load_latest_portfolio() is None
    store.close()

    main(["decide", "--as-of", "2026-06-08", "--output-dir", str(tmp_path)])
    store = PortfolioStore(str(tmp_path / "portfolio.sqlite"))
    assert store.week_number() == 1
    assert store.load_latest_portfolio() is not None
    store.close()


def test_mock_agents_differentiate_by_role():
    """Given role-relevant features, agents must not all parrot feature_score."""
    provider = MockLLMProvider()
    payload = {
        "symbol": "AAPL",
        "feature_score": 0.1,
        "features": {
            "momentum_4w": 0.8,
            "momentum_12w": 0.4,
            "macro_risk_appetite": -0.5,
            "growth_revenue_yoy": 0.3,
            "risk_drawdown_52w": 0.6,
        },
    }
    technical = provider.complete_structured("technical", payload)
    macro = provider.complete_structured("macro", payload)
    fundamental = provider.complete_structured("fundamental", payload)
    critic = provider.complete_structured("critic", payload)

    assert technical["score"] == pytest.approx(0.6)
    assert macro["score"] == pytest.approx(-0.5)
    assert fundamental["score"] == pytest.approx(0.3)
    assert critic["score"] == pytest.approx(-0.335)
    assert technical["stance"] == "bullish"
    assert macro["stance"] == "bearish"


def test_ingest_rejects_unknown_source(tmp_path: Path):
    with pytest.raises(ValueError, match="bogus"):
        ingest_prices(["AAPL"], source="bogus", path=str(tmp_path / "prices.json"))


def test_risk_config_validates_limits():
    with pytest.raises(ValueError):
        RiskConfig(max_single_weight=1.5)
    with pytest.raises(ValueError):
        RiskConfig(min_cash=-0.1)
    with pytest.raises(ValueError):
        RiskConfig(max_weekly_turnover=0.5, max_rebuild_turnover=0.3)
    with pytest.raises(ValueError):
        RiskConfig(transaction_cost_bps=-1.0)
    RiskConfig()  # defaults stay valid


def _evidence(as_of, symbol, value):
    return make_evidence(
        source="tdd",
        source_url="local://tdd",
        observed_at=as_of,
        available_at=as_of,
        fetched_at=as_of,
        value=value,
        unit="normalized_score",
        symbol=symbol,
        feature="multi_factor_score",
    )


def test_thesis_rebuild_uses_rebuild_turnover_budget(tmp_path: Path):
    """When >=2 theses are invalidated, the REBUILD candidate may exceed the
    weekly turnover cap up to max_rebuild_turnover; today it is wrongly capped
    at the weekly limit, so the portfolio cannot actually be rebuilt."""
    risk = RiskConfig(
        max_single_weight=0.30,
        max_sector_weight=0.35,
        min_cash=0.05,
        max_weekly_turnover=0.20,
        max_rebuild_turnover=0.60,
    )
    universe = UniverseConfig(
        "tdd-universe",
        ["A", "B", "C", "D"],
        {"A": "S1", "B": "S2", "C": "S3", "D": "S4", "CASH": "CASH"},
    )
    state_path = str(tmp_path / "portfolio.sqlite")

    # Week 1: persisted state holds A/B heavily with strongly positive theses.
    store = PortfolioStore(state_path)
    week1_portfolio = Portfolio(
        "p-week1", {"A": 0.285, "B": 0.25, "C": 0.215, "D": 0.19, "CASH": 0.06}, 40.0, 0.12
    )
    week1_decision = Decision(
        run_id="run-w1", decision_time=WEEK1, execute_after=WEEK1, action=Action.REBUILD,
        current_portfolio_id="seed", candidate_portfolio_id="p-week1",
        net_improvement_bps=40.0, estimated_transaction_cost_bps=14.0,
        safety_margin_bps=10.0, weekly_turnover=0.95, risk_gate_status="APPROVED",
        reason_codes=["INITIAL_PORTFOLIO_CONSTRUCTION"],
    )
    store.save_run(
        WEEK1, week1_portfolio, {"CASH": 1.0}, week1_decision,
        {"A": 0.9, "B": 0.9, "C": 0.4, "D": 0.4},
    )
    store.close()

    # Week 2: A and B collapse, C and D stay strong -> two theses invalidated.
    evidence = [
        _evidence(WEEK2, "A", -1.0),
        _evidence(WEEK2, "B", -1.0),
        _evidence(WEEK2, "C", 1.0),
        _evidence(WEEK2, "D", 1.0),
    ]
    result = run_pipeline(
        WEEK2, str(tmp_path), evidence=evidence,
        risk_config=risk, universe=universe, state_path=state_path,
    )

    assert result.thesis_statuses["A"] == ThesisStatus.INVALIDATED
    assert result.thesis_statuses["B"] == ThesisStatus.INVALIDATED
    assert result.decision.action == Action.REBUILD
    assert "MULTIPLE_CORE_THESES_INVALIDATED" in result.decision.reason_codes
    assert result.decision.risk_gate_status == "APPROVED"
    # The rebuild must actually move the book: beyond the weekly cap,
    # within the rebuild budget.
    assert result.decision.weekly_turnover > risk.max_weekly_turnover + 1e-6
    assert result.decision.weekly_turnover <= risk.max_rebuild_turnover + 1e-6
    # The collapsed names must be flushed from the applied portfolio.
    assert result.applied.weights.get("A", 0.0) < 0.01
    assert result.applied.weights.get("B", 0.0) < 0.01
