import json
from datetime import datetime, timezone
from pathlib import Path

from finagent.backtest import run_backtest
from finagent.config import RiskConfig, load_risk_config, load_universe
from finagent.data import evidence_from_prices, synthetic_price_store
from finagent.models import Action, Decision, Portfolio
from finagent.pipeline import demo_evidence, run_pipeline
from finagent.state import PortfolioStore

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
SYMBOLS = ["AAPL", "MSFT", "JPM", "XOM", "UNH", "AMZN", "GOOGL", "META", "NVDA", "COST"]


def test_risk_config_loads_from_file(tmp_path: Path):
    file = tmp_path / "risk.json"
    file.write_text(json.dumps({"max_single_weight": 0.15, "transaction_cost_bps": 20}))
    config = load_risk_config(str(file))
    assert config.max_single_weight == 0.15
    assert config.total_cost_bps == 25  # 20 + default slippage 5
    assert load_risk_config(str(tmp_path / "missing.json")) == RiskConfig()


def test_universe_config_includes_sectors():
    universe = load_universe()
    assert universe.symbols
    assert all(symbol in universe.sectors for symbol in universe.symbols)
    assert universe.sectors.get("CASH") == "CASH"


def test_price_evidence_is_point_in_time():
    store = synthetic_price_store(SYMBOLS, weeks=40)
    items = evidence_from_prices(store, SYMBOLS, NOW)
    assert items
    assert all(item.available_at <= NOW for item in items)
    assert all(-1.0 <= float(item.value) <= 1.0 for item in items)
    features = {item.feature for item in items}
    assert {"momentum_12w", "momentum_4w", "low_volatility"} <= features


def test_portfolio_store_roundtrip(tmp_path: Path):
    store = PortfolioStore(str(tmp_path / "portfolio.sqlite"))
    assert store.load_latest_portfolio() is None
    assert store.week_number() == 0
    portfolio = Portfolio("p1", {"AAPL": 0.10, "CASH": 0.90}, 30.0, 0.08)
    decision = Decision(
        run_id="run-1", decision_time=NOW, execute_after=NOW, action=Action.REBUILD,
        current_portfolio_id="seed", candidate_portfolio_id="p1",
        net_improvement_bps=12.0, estimated_transaction_cost_bps=3.0,
        safety_margin_bps=10.0, weekly_turnover=0.9, risk_gate_status="APPROVED",
        reason_codes=["INITIAL_PORTFOLIO_CONSTRUCTION"],
    )
    store.save_run(NOW, portfolio, {"CASH": 1.0}, decision, {"AAPL": 0.6})
    loaded = store.load_latest_portfolio()
    assert loaded is not None
    assert loaded.weights == {"AAPL": 0.10, "CASH": 0.90}
    assert store.previous_scores() == {"AAPL": 0.6}
    assert store.week_number() == 1
    assert store.decision_history()[0]["action"] == "REBUILD"


def test_pipeline_state_machine_first_run_rebuilds_then_persists(tmp_path: Path):
    evidence = demo_evidence(NOW)
    first = run_pipeline(NOW, str(tmp_path), evidence=evidence)
    assert first.decision.action == Action.REBUILD
    assert "INITIAL_PORTFOLIO_CONSTRUCTION" in first.decision.reason_codes
    assert first.current.weights == {"CASH": 1.0}

    second = run_pipeline(NOW, str(tmp_path), evidence=evidence)
    assert second.week_number == 2
    assert second.current.weights == dict(first.applied.weights)
    assert (tmp_path / "portfolio.sqlite").exists()


def test_backtest_is_pipeline_driven_and_deterministic(tmp_path: Path):
    store = synthetic_price_store(SYMBOLS, weeks=30, seed=7)
    universe = load_universe()
    one = run_backtest(store, weeks=6, output_dir=str(tmp_path / "a"), universe=universe)
    two = run_backtest(store, weeks=6, output_dir=str(tmp_path / "b"), universe=universe)
    assert one.weeks == 5  # last decision week has no forward return
    assert one.metrics == two.metrics
    assert sum(one.actions.values()) == 5
    report = json.loads((tmp_path / "a" / "backtest-report.json").read_text())
    assert len(report["equity_curve"]) == 5
    # every backtest week ran the real pipeline and wrote an audit artifact
    assert len(list((tmp_path / "a").glob("run-*.json"))) == 6
