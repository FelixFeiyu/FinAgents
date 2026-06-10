from collections import defaultdict
from statistics import mean, pstdev
from typing import Dict, Iterable, List

from .evidence import EvidenceLedger
from .models import AgentView, AggregatedView


class ViewAggregator:
    def __init__(self, ledger: EvidenceLedger) -> None:
        self.ledger = ledger

    def aggregate(self, views: Iterable[AgentView]) -> Dict[str, AggregatedView]:
        grouped: Dict[str, List[AgentView]] = defaultdict(list)
        for view in views:
            if view.evidence_ids and all(self.ledger.exists(item) for item in view.evidence_ids):
                grouped[view.symbol].append(view)

        output = {}
        for symbol, valid in grouped.items():
            scores = [view.score for view in valid]
            confidence = mean(view.confidence for view in valid)
            disagreement = min(1.0, pstdev(scores) if len(scores) > 1 else 0.0)
            calibrated = confidence * (1.0 - 0.5 * disagreement)
            weighted = sum(v.score * v.confidence for v in valid) / max(
                0.0001, sum(v.confidence for v in valid)
            )
            evidence_ids = sorted({item for view in valid for item in view.evidence_ids})
            output[symbol] = AggregatedView(
                symbol=symbol,
                score=weighted * calibrated,
                confidence=calibrated,
                evidence_ids=evidence_ids,
                contributors=[view.agent for view in valid],
                disagreement=disagreement,
            )
        return output

