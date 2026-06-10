from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, List

from .models import Evidence


@dataclass
class TemporalFirewall:
    violations: List[str] = field(default_factory=list)

    def filter(self, evidence: Iterable[Evidence], decision_time: datetime) -> List[Evidence]:
        visible = []
        for item in evidence:
            if item.available_at <= decision_time:
                visible.append(item)
            else:
                self.violations.append(
                    f"{item.evidence_id}: available_at {item.available_at.isoformat()} "
                    f"is after {decision_time.isoformat()}"
                )
        return visible

