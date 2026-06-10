"""Real market data layer.

Daily closes come from Yahoo Finance (free, no API key) or Alpha Vantage (key
required), are cached on disk as a JSON price store, and are turned into
point-in-time ``Evidence`` (momentum / volatility features) that flows through
the temporal firewall exactly like demo evidence.

A deterministic synthetic price generator keeps the offline demo, backtest,
and tests runnable without network access.
"""

from __future__ import annotations

import json
import math
import random
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from .evidence import make_evidence
from .models import Evidence

# symbol -> sorted list of ("YYYY-MM-DD", close)
PriceStore = Dict[str, List[List[object]]]
# symbol -> list of {"start", "end", "filed", "revenue", "net_income"}
FundamentalsStore = Dict[str, List[Dict[str, object]]]

DEFAULT_PRICE_STORE = "data/processed/prices.json"
DEFAULT_FUNDAMENTALS_STORE = "data/processed/fundamentals.json"
DEFAULT_MACRO_STORE = "data/processed/macro.json"

# Macro market series fetched through the free Yahoo chart API:
# ^TNX = 10y treasury yield (percent), ^VIX = implied volatility index.
MACRO_TICKERS = ("^TNX", "^VIX")
SEC_USER_AGENT_ENV = "SEC_USER_AGENT"


def _fetch_with_retries(url: str, user_agent: str = "FinAgent/0.1") -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    last_error: Optional[Exception] = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except Exception as error:  # noqa: BLE001 - retry then surface
            last_error = error
            time.sleep(2**attempt)
    raise RuntimeError(f"data fetch failed after retries: {last_error}")


def fetch_yahoo_daily(
    symbol: str, cache_dir: str = "data/raw/yahoo", range_: str = "5y"
) -> Dict[str, float]:
    """Daily adjusted closes from the free Yahoo Finance chart API (no key)."""
    cache = Path(cache_dir) / f"{symbol.upper()}.json"
    if cache.exists():
        body = json.loads(cache.read_text(encoding="utf-8"))
    else:
        url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{urllib.parse.quote(symbol)}?range={range_}&interval=1d"
        )
        body = json.loads(_fetch_with_retries(url, user_agent="Mozilla/5.0 FinAgent/0.1"))
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(body), encoding="utf-8")
    try:
        result = body["chart"]["result"][0]
        timestamps = result["timestamp"]
        quote = result["indicators"]
        closes_raw = (quote.get("adjclose") or quote["quote"])[0]
        values = closes_raw.get("adjclose") or closes_raw.get("close")
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError(f"yahoo returned no data for {symbol}: {error}")
    closes: Dict[str, float] = {}
    for stamp, value in zip(timestamps, values):
        if value is None:
            continue
        day = datetime.fromtimestamp(stamp, tz=timezone.utc).date().isoformat()
        closes[day] = float(value)
    if not closes:
        raise RuntimeError(f"no parsable closes for {symbol}")
    return closes


def fetch_alpha_vantage_daily(symbol: str) -> Dict[str, float]:
    from .market_data import AlphaVantageProvider

    snapshot = AlphaVantageProvider().daily(symbol)
    series = snapshot.get("data", {}).get("Time Series (Daily)", {})
    closes = {}
    for day, values in series.items():
        try:
            closes[day] = float(values.get("5. adjusted close") or values["4. close"])
        except (KeyError, ValueError):
            continue
    if not closes:
        raise RuntimeError(f"alpha vantage returned no closes for {symbol}")
    return closes


def _sec_user_agent() -> str:
    import os

    return os.environ.get(SEC_USER_AGENT_ENV, "FinAgent research@example.com")


def fetch_sec_ticker_ciks(cache_dir: str = "data/raw/sec") -> Dict[str, str]:
    """Ticker -> zero-padded CIK from the official SEC mapping file."""
    cache = Path(cache_dir) / "company_tickers.json"
    if cache.exists():
        body = json.loads(cache.read_text(encoding="utf-8"))
    else:
        raw = _fetch_with_retries(
            "https://www.sec.gov/files/company_tickers.json", user_agent=_sec_user_agent()
        )
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(raw)
        body = json.loads(raw)
    return {row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in body.values()}


_SEC_REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)


def fetch_sec_fundamentals(
    symbol: str, cik: str, cache_dir: str = "data/raw/sec"
) -> List[Dict[str, object]]:
    """Quarterly revenue / net income periods from SEC XBRL company facts.

    Each record keeps the earliest ``filed`` date for its period, which is the
    moment the figure became publicly available (point-in-time correctness).
    """
    cache = Path(cache_dir) / f"companyfacts_{cik}.json"
    if cache.exists():
        body = json.loads(cache.read_text(encoding="utf-8"))
    else:
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        raw = _fetch_with_retries(url, user_agent=_sec_user_agent())
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(raw)
        body = json.loads(raw)
    gaap = body.get("facts", {}).get("us-gaap", {})

    def quarterly_entries(tag: str) -> Dict[tuple, Dict[str, object]]:
        periods: Dict[tuple, Dict[str, object]] = {}
        for entry in gaap.get(tag, {}).get("units", {}).get("USD", []):
            start, end, filed = entry.get("start"), entry.get("end"), entry.get("filed")
            value = entry.get("val")
            if not (start and end and filed) or value is None:
                continue
            duration = (date.fromisoformat(end) - date.fromisoformat(start)).days
            if not 70 <= duration <= 100:  # quarterly periods only
                continue
            key = (start, end)
            known = periods.get(key)
            if known is None or str(filed) < str(known["filed"]):
                periods[key] = {"start": start, "end": end, "filed": filed, "value": value}
        return periods

    revenue: Dict[tuple, Dict[str, object]] = {}
    for tag in _SEC_REVENUE_TAGS:
        for key, entry in quarterly_entries(tag).items():
            revenue.setdefault(key, entry)
    income = quarterly_entries("NetIncomeLoss")

    records = []
    for key in sorted(set(revenue) | set(income), key=lambda item: item[1]):
        rev, ni = revenue.get(key), income.get(key)
        filed_dates = [str(e["filed"]) for e in (rev, ni) if e]
        records.append(
            {
                "start": key[0],
                "end": key[1],
                "filed": min(filed_dates),
                "revenue": rev["value"] if rev else None,
                "net_income": ni["value"] if ni else None,
            }
        )
    return records


def ingest_fundamentals(
    symbols: List[str], path: str = DEFAULT_FUNDAMENTALS_STORE
) -> FundamentalsStore:
    ciks = fetch_sec_ticker_ciks()
    store: FundamentalsStore = {}
    for symbol in symbols:
        cik = ciks.get(symbol.upper())
        if cik is None:
            continue
        store[symbol] = fetch_sec_fundamentals(symbol, cik)
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(store, indent=1), encoding="utf-8")
    return store


def ingest_macro(path: str = DEFAULT_MACRO_STORE) -> PriceStore:
    """Macro market series (10y yield, VIX) into a price-store-shaped file."""
    store: PriceStore = {}
    for ticker in MACRO_TICKERS:
        closes = fetch_yahoo_daily(ticker, cache_dir="data/raw/yahoo_macro")
        store[ticker] = [[day, value] for day, value in sorted(closes.items())]
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(store, indent=1), encoding="utf-8")
    return store


def synthetic_price_store(
    symbols: List[str], weeks: int = 60, seed: int = 42, end: Optional[date] = None
) -> PriceStore:
    """Deterministic weekly random-walk prices for offline use."""
    end = end or date(2026, 6, 5)
    rng = random.Random(seed)
    store: PriceStore = {}
    for index, symbol in enumerate(sorted(symbols)):
        drift = 0.0015 + 0.0006 * (index % 5) - 0.001 * (index % 3)
        sigma = 0.02 + 0.004 * (index % 4)
        price = 50.0 + 10.0 * index
        series: List[List[object]] = []
        for week in range(weeks):
            day = end - timedelta(weeks=weeks - 1 - week)
            price *= math.exp(drift + sigma * rng.gauss(0.0, 1.0))
            series.append([day.isoformat(), round(price, 4)])
        store[symbol] = series
    return store


def save_price_store(store: PriceStore, path: str = DEFAULT_PRICE_STORE) -> Path:
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(store, indent=1), encoding="utf-8")
    return file


def load_price_store(path: str = DEFAULT_PRICE_STORE) -> PriceStore:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_fundamentals_store(path: str = DEFAULT_FUNDAMENTALS_STORE) -> FundamentalsStore:
    file = Path(path)
    if not file.exists():
        return {}
    return json.loads(file.read_text(encoding="utf-8"))


def load_macro_store(path: str = DEFAULT_MACRO_STORE) -> PriceStore:
    file = Path(path)
    if not file.exists():
        return {}
    return json.loads(file.read_text(encoding="utf-8"))


def synthetic_fundamentals(
    symbols: List[str], quarters: int = 16, end: Optional[date] = None
) -> FundamentalsStore:
    """Deterministic quarterly SEC-shaped records for offline tests."""
    end = end or date(2026, 3, 31)
    store: FundamentalsStore = {}
    for index, symbol in enumerate(sorted(symbols)):
        records: List[Dict[str, object]] = []
        revenue = 5_000_000_000.0 * (1.0 + 0.08 * index)
        margin = 0.12 + 0.01 * (index % 4)
        for q in range(quarters):
            period_end = end - timedelta(days=90 * (quarters - 1 - q))
            period_start = period_end - timedelta(days=89)
            filed = period_end + timedelta(days=35)
            growth = 1.0 + 0.03 + 0.005 * (q % 3)
            revenue *= growth
            net_income = revenue * margin
            records.append(
                {
                    "start": period_start.isoformat(),
                    "end": period_end.isoformat(),
                    "filed": filed.isoformat(),
                    "revenue": round(revenue, 2),
                    "net_income": round(net_income, 2),
                }
            )
        store[symbol] = records
    return store


def synthetic_macro(weeks: int = 260, end: Optional[date] = None) -> PriceStore:
    """Deterministic ^TNX / ^VIX series for offline macro evidence."""
    end = end or date(2026, 6, 5)
    rng = random.Random(99)
    store: PriceStore = {}
    tnx, vix = 4.2, 18.0
    for ticker, base, sigma in (("^TNX", tnx, 0.04), ("^VIX", vix, 1.5)):
        level = base
        series: List[List[object]] = []
        for week in range(weeks):
            day = end - timedelta(weeks=weeks - 1 - week)
            level += rng.gauss(0.0, sigma)
            if ticker == "^TNX":
                level = max(0.5, min(level, 8.0))
            else:
                level = max(10.0, min(level, 45.0))
            series.append([day.isoformat(), round(level, 4)])
        store[ticker] = series
    return store


def save_fundamentals_store(store: FundamentalsStore, path: str = DEFAULT_FUNDAMENTALS_STORE) -> Path:
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(store, indent=1), encoding="utf-8")
    return file


def save_macro_store(store: PriceStore, path: str = DEFAULT_MACRO_STORE) -> Path:
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(store, indent=1), encoding="utf-8")
    return file


def write_dataset_manifest(
    processed_dir: str = "data/processed",
    symbols: Optional[List[str]] = None,
) -> Path:
    """Summarize ingested datasets for doctor / dashboard."""
    processed = Path(processed_dir)
    symbols = symbols or []
    manifest: Dict[str, object] = {"generated_at": datetime.now(timezone.utc).isoformat(), "datasets": {}}

    prices_file = processed / "prices.json"
    if prices_file.exists():
        prices = load_price_store(str(prices_file))
        manifest["datasets"]["technical"] = {
            "file": str(prices_file),
            "symbols": len(prices),
            "bars": {s: len(v) for s, v in prices.items()},
            "features": ["momentum_4w", "momentum_12w"],
        }
        manifest["datasets"]["critic"] = {
            "file": str(prices_file),
            "features": ["risk_drawdown_52w"],
            "note": "derived from the same price store as technical",
        }

    fundamentals_file = processed / "fundamentals.json"
    if fundamentals_file.exists():
        fundamentals = load_fundamentals_store(str(fundamentals_file))
        manifest["datasets"]["fundamental"] = {
            "file": str(fundamentals_file),
            "symbols": len(fundamentals),
            "quarters": {s: len(v) for s, v in fundamentals.items()},
            "features": ["growth_revenue_yoy", "growth_earnings_yoy", "quality_net_margin"],
        }

    macro_file = processed / "macro.json"
    if macro_file.exists():
        macro = load_macro_store(str(macro_file))
        manifest["datasets"]["macro"] = {
            "file": str(macro_file),
            "series": list(macro.keys()),
            "bars": {s: len(v) for s, v in macro.items()},
            "features": ["macro_rate_trend", "macro_risk_appetite"],
        }

    if symbols:
        as_of = datetime.now(timezone.utc)
        sample = build_evidence(
            as_of,
            symbols,
            price_store=load_price_store(str(prices_file)) if prices_file.exists() else None,
            fundamentals=load_fundamentals_store(str(fundamentals_file))
            if fundamentals_file.exists() else None,
            macro_store=load_macro_store(str(macro_file)) if macro_file.exists() else None,
        )
        by_feature = sorted({str(item.feature) for item in sample})
        manifest["sample_evidence_features"] = by_feature
        manifest["sample_evidence_count"] = len(sample)

    out = processed / "manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out


def dataset_status(processed_dir: str = "data/processed") -> Dict[str, bool]:
    processed = Path(processed_dir)
    return {
        "technical": (processed / "prices.json").exists(),
        "fundamental": (processed / "fundamentals.json").exists(),
        "macro": (processed / "macro.json").exists(),
        "critic": (processed / "prices.json").exists(),
    }


def ingest_prices(
    symbols: List[str],
    source: str = "yahoo",
    path: str = DEFAULT_PRICE_STORE,
    weeks: int = 260,
) -> PriceStore:
    """Fetch daily closes for the universe and persist them as a price store."""
    fetchers = {"yahoo": fetch_yahoo_daily, "alpha_vantage": fetch_alpha_vantage_daily}
    if source == "synthetic":
        store = synthetic_price_store(symbols, weeks=weeks)
        save_price_store(store, path)
        return store
    fetch = fetchers.get(source)
    if fetch is None:
        valid = ", ".join(sorted([*fetchers, "synthetic"]))
        raise ValueError(f"unknown ingest source: {source!r} (expected one of: {valid})")
    store: PriceStore = {}
    for symbol in symbols:
        closes = fetch(symbol)
        series = sorted(closes.items())[-weeks * 5 :]
        store[symbol] = [[day, value] for day, value in series]
    save_price_store(store, path)
    return store


def closes_before(store: PriceStore, symbol: str, as_of: date) -> List[float]:
    cutoff = as_of.isoformat()
    return [float(close) for day, close in store.get(symbol, []) if str(day) <= cutoff]


def last_close_date(store: PriceStore, symbol: str, as_of: date) -> Optional[date]:
    cutoff = as_of.isoformat()
    days = [str(day) for day, _ in store.get(symbol, []) if str(day) <= cutoff]
    return date.fromisoformat(days[-1]) if days else None


def _squash(value: float, scale: float) -> float:
    return math.tanh(value / scale)


def compute_features(closes: List[float]) -> Dict[str, float]:
    """Point-in-time features in [-1, 1] from a close series ending at as_of."""
    if len(closes) < 9:
        return {}
    last = closes[-1]
    features: Dict[str, float] = {}
    lookback_long = min(len(closes) - 1, 60)
    features["momentum_12w"] = _squash(last / closes[-1 - lookback_long] - 1.0, 0.25)
    lookback_short = min(len(closes) - 1, 20)
    features["momentum_4w"] = _squash(last / closes[-1 - lookback_short] - 1.0, 0.12)
    window = closes[-min(len(closes), 61) :]
    returns = [window[i] / window[i - 1] - 1.0 for i in range(1, len(window))]
    mean = sum(returns) / len(returns)
    variance = sum((item - mean) ** 2 for item in returns) / len(returns)
    annualized_vol = math.sqrt(variance) * math.sqrt(252)
    # Low volatility scores positive, high volatility negative (risk penalty).
    features["low_volatility"] = _squash(0.25 - annualized_vol, 0.20)
    # Bear-case feature for the critic: drawdown from the 52-week high in [0, 1).
    year_window = closes[-min(len(closes), 252) :]
    peak = max(year_window)
    drawdown = 1.0 - last / peak if peak > 0 else 0.0
    features["risk_drawdown_52w"] = _squash(drawdown, 0.20)
    return features


def evidence_from_prices(
    store: PriceStore, symbols: List[str], as_of: datetime, source: str = "price_store"
) -> List[Evidence]:
    """Build point-in-time evidence; ``available_at`` is the next midnight UTC
    after the close date so the temporal firewall sees realistic timing.

    Only closes that are already available at ``as_of`` are used (a close dated
    D becomes available at D+1 00:00 UTC), so the data layer never emits
    evidence the firewall would have to reject."""
    cutoff = (as_of - timedelta(days=1)).date()
    items: List[Evidence] = []
    for symbol in symbols:
        closes = closes_before(store, symbol, cutoff)
        observed_day = last_close_date(store, symbol, cutoff)
        features = compute_features(closes)
        if not features or observed_day is None:
            continue
        observed_at = datetime.combine(observed_day, dt_time(21, 0), tzinfo=timezone.utc)
        available_at = datetime.combine(
            observed_day + timedelta(days=1), dt_time(0, 0), tzinfo=timezone.utc
        )
        stale = (as_of.date() - observed_day).days > 7
        for feature, value in features.items():
            items.append(
                make_evidence(
                    source=source,
                    source_url=f"store://{symbol}/{feature}",
                    observed_at=observed_at,
                    available_at=available_at,
                    fetched_at=as_of,
                    value=round(value, 6),
                    unit="normalized_score",
                    symbol=symbol,
                    feature=feature,
                    stale=stale,
                )
            )
    return items


def fundamental_features(
    records: List[Dict[str, object]], as_of: datetime
) -> Optional[Dict[str, object]]:
    """Point-in-time fundamental features from quarterly SEC records.

    Returns {"features": {...}, "observed": end_date, "filed": filed_date}
    using only periods filed strictly before ``as_of``."""
    cutoff = (as_of - timedelta(days=1)).date().isoformat()
    visible = [r for r in records if str(r["filed"]) <= cutoff and r.get("revenue")]
    if not visible:
        return None
    visible.sort(key=lambda r: str(r["end"]))
    latest = visible[-1]
    latest_end = date.fromisoformat(str(latest["end"]))
    base = None
    for record in visible:
        delta = (latest_end - date.fromisoformat(str(record["end"]))).days
        if 330 <= delta <= 400:
            base = record
    features: Dict[str, float] = {}
    if base and base.get("revenue"):
        growth = float(latest["revenue"]) / float(base["revenue"]) - 1.0  # type: ignore[arg-type]
        features["growth_revenue_yoy"] = round(_squash(growth, 0.25), 6)
        if latest.get("net_income") is not None and base.get("net_income"):
            ni_growth = float(latest["net_income"]) / abs(float(base["net_income"])) - 1.0  # type: ignore[arg-type]
            features["growth_earnings_yoy"] = round(_squash(ni_growth, 0.40), 6)
    if latest.get("net_income") is not None and latest["revenue"]:
        margin = float(latest["net_income"]) / float(latest["revenue"])  # type: ignore[arg-type]
        features["quality_net_margin"] = round(_squash(margin - 0.10, 0.15), 6)
    if not features:
        return None
    return {"features": features, "observed": str(latest["end"]), "filed": str(latest["filed"])}


def macro_features(macro_store: PriceStore, as_of: datetime) -> Dict[str, float]:
    """Macro regime features from market series (same for every symbol)."""
    cutoff = (as_of - timedelta(days=1)).date()
    features: Dict[str, float] = {}
    tnx = closes_before(macro_store, "^TNX", cutoff)
    if len(tnx) > 63:
        # Rising 10y yields over ~3 months are a headwind for equities.
        features["macro_rate_trend"] = round(_squash(-(tnx[-1] - tnx[-64]), 0.8), 6)
    vix = closes_before(macro_store, "^VIX", cutoff)
    if vix:
        # VIX below ~20 signals risk appetite; above it, stress.
        features["macro_risk_appetite"] = round(_squash(20.0 - vix[-1], 10.0), 6)
    return features


def build_evidence(
    as_of: datetime,
    symbols: List[str],
    price_store: Optional[PriceStore] = None,
    fundamentals: Optional[FundamentalsStore] = None,
    macro_store: Optional[PriceStore] = None,
) -> List[Evidence]:
    """Combine all available real datasets into point-in-time evidence.

    - prices  -> momentum_* (technical), low_volatility, risk_* (critic)
    - SEC     -> growth_* / quality_* (fundamental), available at filing time
    - macro   -> macro_* (macro agent), replicated onto every symbol
    """
    items: List[Evidence] = []
    if price_store:
        items.extend(evidence_from_prices(price_store, symbols, as_of))

    if fundamentals:
        for symbol in symbols:
            snapshot = fundamental_features(fundamentals.get(symbol, []), as_of)
            if snapshot is None:
                continue
            observed = datetime.combine(
                date.fromisoformat(str(snapshot["observed"])), dt_time(21, 0), tzinfo=timezone.utc
            )
            filed = date.fromisoformat(str(snapshot["filed"]))
            available = datetime.combine(
                filed + timedelta(days=1), dt_time(0, 0), tzinfo=timezone.utc
            )
            stale = (as_of.date() - filed).days > 120  # older than a quarter cycle
            for feature, value in snapshot["features"].items():  # type: ignore[union-attr]
                items.append(
                    make_evidence(
                        source="sec_edgar",
                        source_url=f"https://data.sec.gov/api/xbrl/companyfacts ({symbol})",
                        observed_at=observed,
                        available_at=available,
                        fetched_at=as_of,
                        value=value,
                        unit="normalized_score",
                        symbol=symbol,
                        feature=feature,
                        stale=stale,
                    )
                )

    if macro_store:
        shared = macro_features(macro_store, as_of)
        observed_day = last_close_date(macro_store, MACRO_TICKERS[0], (as_of - timedelta(days=1)).date())
        if shared and observed_day is not None:
            observed = datetime.combine(observed_day, dt_time(21, 0), tzinfo=timezone.utc)
            available = datetime.combine(
                observed_day + timedelta(days=1), dt_time(0, 0), tzinfo=timezone.utc
            )
            stale = (as_of.date() - observed_day).days > 7
            for symbol in symbols:
                for feature, value in shared.items():
                    items.append(
                        make_evidence(
                            source="yahoo_macro",
                            source_url=f"yahoo://{'+'.join(MACRO_TICKERS)}/{feature}",
                            observed_at=observed,
                            available_at=available,
                            fetched_at=as_of,
                            value=value,
                            unit="normalized_score",
                            symbol=symbol,
                            feature=feature,
                            stale=stale,
                        )
                    )
    return items


def evidence_to_jsonable(items: List[Evidence]) -> List[Dict[str, object]]:
    from .models import to_dict

    return [to_dict(item) for item in items]


def evidence_from_jsonable(rows: List[Mapping[str, object]]) -> List[Evidence]:
    items = []
    for row in rows:
        data = dict(row)
        for key in ("observed_at", "available_at", "fetched_at"):
            data[key] = datetime.fromisoformat(str(data[key]))
        items.append(Evidence(**data))  # type: ignore[arg-type]
    return items
