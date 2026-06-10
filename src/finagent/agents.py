from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterable, List

from .evidence import EvidenceLedger
from .models import AgentView, Evidence, ThesisStatus
from .providers import LLMProvider


AGENTS = ("fundamental", "technical", "macro")


class ResearchGraph:
    def __init__(self, provider: LLMProvider, ledger: EvidenceLedger) -> None:
        self.provider = provider
        self.ledger = ledger

    def run(self, run_id: str, as_of: datetime, evidence: Iterable[Evidence]) -> List[AgentView]:
        by_symbol: Dict[str, List[Evidence]] = defaultdict(list)
        for item in evidence:
            self.ledger.add(item)
            if item.symbol:
                by_symbol[item.symbol].append(item)

        views: List[AgentView] = []
        for symbol, items in sorted(by_symbol.items()):
            numeric = [float(i.value) for i in items if isinstance(i.value, (int, float))]
            feature_score = sum(numeric) / len(numeric) if numeric else 0.0
            features = {
                str(item.feature): float(item.value)
                for item in items
                if item.feature and isinstance(item.value, (int, float))
            }
            payload = {"symbol": symbol, "feature_score": feature_score, "features": features}
            evidence_ids = [item.evidence_id for item in items]
            for agent in AGENTS:
                response = self._call_with_fallback(agent, payload)
                views.append(self._view(run_id, as_of, symbol, agent, response, evidence_ids))

            critic = self._call_with_fallback("critic", payload)
            views.append(self._view(run_id, as_of, symbol, "critic", critic, evidence_ids))
        return views

    def _call_with_fallback(self, agent: str, payload: Dict[str, object]) -> Dict[str, object]:
        for _ in range(3):
            try:
                result = self.provider.complete_structured(agent, payload)
                if -1 <= float(result["score"]) <= 1 and 0 <= float(result["confidence"]) <= 1:
                    return result
            except Exception:
                continue
        return {
            "score": 0.0,
            "confidence": 0.0,
            "stance": "neutral",
            "thesis": "Provider failed validation; safely degraded to neutral.",
            "risks": ["provider failure"],
        }

    @staticmethod
    def _view(
        run_id: str,
        as_of: datetime,
        symbol: str,
        agent: str,
        response: Dict[str, object],
        evidence_ids: List[str],
    ) -> AgentView:
        return AgentView(
            run_id=run_id,
            agent=agent,
            as_of=as_of,
            symbol=symbol,
            stance=str(response["stance"]),
            score=float(response["score"]),
            confidence=float(response["confidence"]),
            horizon_days=30,
            thesis=str(response["thesis"]),
            risks=list(response["risks"]),  # type: ignore[arg-type]
            evidence_ids=evidence_ids,
            missing_data=[],
            prompt_version=f"{agent}-v1",
        )


def review_holding(previous_score: float, current_score: float) -> ThesisStatus:
    if current_score <= -0.5 or previous_score - current_score >= 0.8:
        return ThesisStatus.INVALIDATED
    if current_score < 0 or previous_score - current_score >= 0.35:
        return ThesisStatus.WEAKENED
    return ThesisStatus.INTACT
