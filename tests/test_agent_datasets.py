"""Tests for per-agent real datasets under data/processed/."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from finagent.data import (
    build_evidence,
    dataset_status,
    fundamental_features,
    load_fundamentals_store,
    load_macro_store,
    load_price_store,
    save_fundamentals_store,
    save_macro_store,
    synthetic_fundamentals,
    synthetic_macro,
    synthetic_price_store,
    write_dataset_manifest,
)
from finagent.providers import MockLLMProvider

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
SYMBOLS = ["AAPL", "MSFT", "JPM"]


def test_agent_dataset_manifest_exists():
    manifest = Path("data/agent_datasets.json")
    assert manifest.exists()
    body = manifest.read_text(encoding="utf-8")
    for agent in ("technical", "fundamental", "macro", "critic"):
        assert agent in body


def test_synthetic_ingest_builds_all_four_agent_datasets(tmp_path: Path):
    processed = tmp_path / "processed"
    prices_path = processed / "prices.json"
    fundamentals_path = processed / "fundamentals.json"
    macro_path = processed / "macro.json"

    from finagent.data import save_price_store

    save_price_store(synthetic_price_store(SYMBOLS, weeks=40), str(prices_path))
    save_fundamentals_store(synthetic_fundamentals(SYMBOLS), str(fundamentals_path))
    save_macro_store(synthetic_macro(weeks=80), str(macro_path))
    write_dataset_manifest(str(processed), SYMBOLS)

    status = {
        "technical": prices_path.exists(),
        "fundamental": fundamentals_path.exists(),
        "macro": macro_path.exists(),
        "critic": prices_path.exists(),
    }
    assert all(status.values())
    assert (processed / "manifest.json").exists()


def test_build_evidence_emits_agent_specific_features(tmp_path: Path):
    processed = tmp_path / "processed"
    from finagent.data import save_price_store

    save_price_store(synthetic_price_store(SYMBOLS, weeks=40), str(processed / "prices.json"))
    save_fundamentals_store(synthetic_fundamentals(SYMBOLS), str(processed / "fundamentals.json"))
    save_macro_store(synthetic_macro(weeks=80), str(processed / "macro.json"))

    items = build_evidence(
        NOW,
        SYMBOLS,
        price_store=load_price_store(str(processed / "prices.json")),
        fundamentals=load_fundamentals_store(str(processed / "fundamentals.json")),
        macro_store=load_macro_store(str(processed / "macro.json")),
    )
    by_agent = {
        "technical": {"momentum_4w", "momentum_12w"},
        "fundamental": {"growth_revenue_yoy", "growth_earnings_yoy", "quality_net_margin"},
        "macro": {"macro_rate_trend", "macro_risk_appetite"},
        "critic": {"risk_drawdown_52w"},
    }
    features = {str(item.feature) for item in items}
    for expected in by_agent.values():
        assert expected <= features, f"missing {expected - features}"
    assert all(item.available_at <= NOW for item in items)


def test_fundamental_features_respect_filing_date():
    records = synthetic_fundamentals(["AAPL"], quarters=8)["AAPL"]
    # Before the first filing becomes public, no fundamentals.
    early = datetime(2020, 1, 1, tzinfo=timezone.utc)
    assert fundamental_features(records, early) is None
    late = datetime(2026, 6, 10, tzinfo=timezone.utc)
    snapshot = fundamental_features(records, late)
    assert snapshot is not None
    assert "growth_revenue_yoy" in snapshot["features"]


def test_mock_provider_reads_each_agent_dataset_features():
    provider = MockLLMProvider()
    payload = {
        "symbol": "AAPL",
        "feature_score": 0.0,
        "features": {
            "momentum_4w": 0.5,
            "growth_revenue_yoy": 0.4,
            "macro_risk_appetite": 0.2,
            "risk_drawdown_52w": 0.8,
        },
    }
    assert provider.complete_structured("technical", payload)["score"] == pytest.approx(0.5)
    assert provider.complete_structured("fundamental", payload)["score"] == pytest.approx(0.4)
    assert provider.complete_structured("macro", payload)["score"] == pytest.approx(0.2)
    assert provider.complete_structured("critic", payload)["score"] == pytest.approx(-0.4)


def test_dataset_status_reflects_files(tmp_path: Path):
    processed = tmp_path / "processed"
    processed.mkdir()
    (processed / "prices.json").write_text("{}", encoding="utf-8")
    status = dataset_status(str(processed))
    assert status["technical"] is True
    assert status["critic"] is True
    assert status["fundamental"] is False
