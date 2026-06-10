from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class MarketDataProvider(ABC):
    @abstractmethod
    def fetch(self, endpoint: str, params: Dict[str, str]) -> Dict[str, Any]:
        raise NotImplementedError


class CachedHttpProvider(MarketDataProvider):
    """HTTP JSON provider with immutable cache, explicit user agent, and retries."""

    def __init__(self, base_url: str, cache_dir: str, user_agent: str) -> None:
        self.base_url = base_url
        self.cache_dir = Path(cache_dir)
        self.user_agent = user_agent

    def fetch(self, endpoint: str, params: Dict[str, str]) -> Dict[str, Any]:
        query = urllib.parse.urlencode(sorted(params.items()))
        url = f"{self.base_url}/{endpoint}?{query}"
        cache_key = __import__("hashlib").sha256(url.encode()).hexdigest()
        path = self.cache_dir / f"{cache_key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        last_error = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    data = json.loads(response.read())
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                snapshot = {
                    "source_url": url,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "stale": False,
                    "data": data,
                }
                path.write_text(json.dumps(snapshot), encoding="utf-8")
                return snapshot
            except Exception as error:
                last_error = error
                time.sleep(2**attempt)
        raise RuntimeError(f"data provider failed after retries: {last_error}")


class AlphaVantageProvider(CachedHttpProvider):
    def __init__(self, cache_dir: str = "data/raw/alpha_vantage") -> None:
        super().__init__("https://www.alphavantage.co/query", cache_dir, "FinAgent/0.1")

    def daily(self, symbol: str) -> Dict[str, Any]:
        return self.fetch(
            "",
            {
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": symbol,
                "outputsize": "full",
                "apikey": os.environ.get("ALPHA_VANTAGE_API_KEY", ""),
            },
        )


class SecEdgarProvider(CachedHttpProvider):
    def __init__(self, cache_dir: str = "data/raw/sec") -> None:
        user_agent = os.environ.get("SEC_USER_AGENT", "FinAgent research@example.com")
        super().__init__("https://data.sec.gov/api/xbrl", cache_dir, user_agent)

    def company_facts(self, cik: str) -> Dict[str, Any]:
        return self.fetch(f"companyfacts/CIK{cik.zfill(10)}.json", {})


class FredProvider(CachedHttpProvider):
    def __init__(self, cache_dir: str = "data/raw/fred") -> None:
        super().__init__("https://api.stlouisfed.org/fred", cache_dir, "FinAgent/0.1")

    def series(self, series_id: str) -> Dict[str, Any]:
        return self.fetch(
            "series/observations",
            {
                "series_id": series_id,
                "api_key": os.environ.get("FRED_API_KEY", ""),
                "file_type": "json",
            },
        )

