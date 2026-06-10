from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, List, Optional

from .models import Evidence


def make_evidence(
    source: str,
    source_url: str,
    observed_at: datetime,
    available_at: datetime,
    fetched_at: datetime,
    value: Any,
    unit: str = "",
    symbol: Optional[str] = None,
    feature: Optional[str] = None,
    stale: bool = False,
) -> Evidence:
    payload = json.dumps(value, sort_keys=True, default=str).encode()
    return Evidence(
        evidence_id=f"ev-{uuid.uuid4()}",
        source=source,
        source_url=source_url,
        observed_at=observed_at,
        available_at=available_at,
        fetched_at=fetched_at,
        content_hash=hashlib.sha256(payload).hexdigest(),
        value=value,
        unit=unit,
        stale=stale,
        symbol=symbol,
        feature=feature,
    )


class EvidenceLedger:
    def __init__(self, path: str = ":memory:") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS evidence (
            evidence_id TEXT PRIMARY KEY, source TEXT, source_url TEXT,
            observed_at TEXT, available_at TEXT, fetched_at TEXT,
            content_hash TEXT, value_json TEXT, unit TEXT, stale INTEGER,
            symbol TEXT, feature TEXT)"""
        )

    def add(self, evidence: Evidence) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                evidence.evidence_id,
                evidence.source,
                evidence.source_url,
                evidence.observed_at.isoformat(),
                evidence.available_at.isoformat(),
                evidence.fetched_at.isoformat(),
                evidence.content_hash,
                json.dumps(evidence.value, default=str),
                evidence.unit,
                int(evidence.stale),
                evidence.symbol,
                evidence.feature,
            ),
        )
        self.connection.commit()

    def add_many(self, evidence: Iterable[Evidence]) -> None:
        for item in evidence:
            self.add(item)

    def exists(self, evidence_id: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM evidence WHERE evidence_id = ?", (evidence_id,)
        ).fetchone()
        return row is not None

    def all(self) -> List[Evidence]:
        rows = self.connection.execute("SELECT * FROM evidence ORDER BY available_at").fetchall()
        return [
            Evidence(
                evidence_id=row[0],
                source=row[1],
                source_url=row[2],
                observed_at=datetime.fromisoformat(row[3]),
                available_at=datetime.fromisoformat(row[4]),
                fetched_at=datetime.fromisoformat(row[5]),
                content_hash=row[6],
                value=json.loads(row[7]),
                unit=row[8],
                stale=bool(row[9]),
                symbol=row[10],
                feature=row[11],
            )
            for row in rows
        ]

