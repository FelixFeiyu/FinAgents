"""Portfolio state machine persistence (ported from maipf's PortfolioStateStore).

SQLite keeps portfolio snapshots, decision history, and per-symbol aggregated
scores across weekly runs, so ``decide`` compares the candidate against the
*actual* previous portfolio and thesis review compares this week's score with
last week's instead of with itself.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .models import Decision, Portfolio


class PortfolioStore:
    def __init__(self, path: str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                as_of TEXT NOT NULL,
                week_number INTEGER NOT NULL,
                weights_json TEXT NOT NULL,
                expected_return_bps REAL NOT NULL,
                expected_volatility REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS decision_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                as_of TEXT NOT NULL,
                week_number INTEGER NOT NULL,
                action TEXT NOT NULL CHECK(action IN ('HOLD', 'REBALANCE', 'REBUILD')),
                weights_before_json TEXT NOT NULL,
                weights_after_json TEXT NOT NULL,
                weekly_turnover REAL NOT NULL,
                net_improvement_bps REAL NOT NULL,
                estimated_cost_bps REAL NOT NULL,
                reason_codes_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS score_snapshots (
                run_id TEXT NOT NULL,
                as_of TEXT NOT NULL,
                week_number INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                score REAL NOT NULL
            );
            """
        )
        self.connection.commit()

    def week_number(self) -> int:
        row = self.connection.execute(
            "SELECT COALESCE(MAX(week_number), 0) FROM decision_records"
        ).fetchone()
        return int(row[0])

    def load_latest_portfolio(self) -> Optional[Portfolio]:
        row = self.connection.execute(
            "SELECT run_id, weights_json, expected_return_bps, expected_volatility "
            "FROM portfolio_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return Portfolio(
            portfolio_id=f"portfolio-{row[0]}",
            weights=json.loads(row[1]),
            expected_return_bps=float(row[2]),
            expected_volatility=float(row[3]),
        )

    def previous_scores(self) -> Dict[str, float]:
        row = self.connection.execute(
            "SELECT COALESCE(MAX(week_number), 0) FROM score_snapshots"
        ).fetchone()
        latest_week = int(row[0])
        if latest_week == 0:
            return {}
        rows = self.connection.execute(
            "SELECT symbol, score FROM score_snapshots WHERE week_number = ?", (latest_week,)
        ).fetchall()
        return {symbol: float(score) for symbol, score in rows}

    def save_run(
        self,
        as_of: datetime,
        applied: Portfolio,
        previous_weights: Mapping[str, float],
        decision: Decision,
        scores: Mapping[str, float],
    ) -> int:
        week = self.week_number() + 1
        self.connection.execute(
            "INSERT INTO portfolio_snapshots "
            "(run_id, as_of, week_number, weights_json, expected_return_bps, expected_volatility) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                decision.run_id,
                as_of.isoformat(),
                week,
                json.dumps(dict(applied.weights)),
                applied.expected_return_bps,
                applied.expected_volatility,
            ),
        )
        self.connection.execute(
            "INSERT INTO decision_records "
            "(run_id, as_of, week_number, action, weights_before_json, weights_after_json, "
            "weekly_turnover, net_improvement_bps, estimated_cost_bps, reason_codes_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                decision.run_id,
                as_of.isoformat(),
                week,
                decision.action.value,
                json.dumps(dict(previous_weights)),
                json.dumps(dict(applied.weights)),
                decision.weekly_turnover,
                decision.net_improvement_bps,
                decision.estimated_transaction_cost_bps,
                json.dumps(list(decision.reason_codes)),
            ),
        )
        self.connection.executemany(
            "INSERT INTO score_snapshots (run_id, as_of, week_number, symbol, score) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (decision.run_id, as_of.isoformat(), week, symbol, float(score))
                for symbol, score in scores.items()
            ],
        )
        self.connection.commit()
        return week

    def decision_history(self, limit: int = 52) -> List[Dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT run_id, as_of, week_number, action, weights_before_json, weights_after_json, "
            "weekly_turnover, net_improvement_bps, estimated_cost_bps, reason_codes_json "
            "FROM decision_records ORDER BY week_number DESC LIMIT ?",
            (limit,),
        ).fetchall()
        history = []
        for row in rows:
            history.append(
                {
                    "run_id": row[0],
                    "as_of": row[1],
                    "week_number": row[2],
                    "action": row[3],
                    "weights_before": json.loads(row[4]),
                    "weights_after": json.loads(row[5]),
                    "weekly_turnover": row[6],
                    "net_improvement_bps": row[7],
                    "estimated_cost_bps": row[8],
                    "reason_codes": json.loads(row[9]),
                }
            )
        return history

    def close(self) -> None:
        self.connection.close()
