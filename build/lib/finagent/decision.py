from __future__ import annotations

from datetime import datetime, timedelta
from typing import Mapping

from .models import Action, Decision, Portfolio, RiskResult, ThesisStatus
from .portfolio import turnover


class DecisionGate:
    def __init__(self, transaction_cost_bps: float = 15.0, safety_margin_bps: float = 10.0) -> None:
        self.transaction_cost_bps = transaction_cost_bps
        self.safety_margin_bps = safety_margin_bps

    def decide(
        self,
        run_id: str,
        decision_time: datetime,
        current: Portfolio,
        candidate: Portfolio,
        candidate_risk: RiskResult,
        current_risk: RiskResult,
        thesis_statuses: Mapping[str, ThesisStatus],
    ) -> Decision:
        weekly_turnover = turnover(current.weights, candidate.weights)
        estimated_cost = weekly_turnover * self.transaction_cost_bps
        net = (
            candidate.expected_return_bps
            - current.expected_return_bps
            - estimated_cost
            - self.safety_margin_bps
        )
        invalidated = sum(status == ThesisStatus.INVALIDATED for status in thesis_statuses.values())

        if current_risk.status == "REJECTED":
            action = Action.REBUILD if invalidated >= 2 else Action.REBALANCE
            reasons = ["CURRENT_PORTFOLIO_RISK_BREACH", *current_risk.violations]
            if candidate_risk.status == "REJECTED":
                reasons = ["RISK_REDUCING_FALLBACK_REQUIRED", *reasons, *candidate_risk.violations]
        elif candidate_risk.status == "REJECTED":
            action = Action.HOLD
            reasons = ["CANDIDATE_RISK_REJECTED", *candidate_risk.violations]
        elif invalidated >= 2:
            action = Action.REBUILD
            reasons = ["MULTIPLE_CORE_THESES_INVALIDATED"]
        elif net > 0:
            action = Action.REBALANCE
            reasons = ["POSITIVE_NET_IMPROVEMENT"]
        else:
            action = Action.HOLD
            reasons = ["INSUFFICIENT_NET_IMPROVEMENT"]

        return Decision(
            run_id=run_id,
            decision_time=decision_time,
            execute_after=decision_time + timedelta(days=1),
            action=action,
            current_portfolio_id=current.portfolio_id,
            candidate_portfolio_id=candidate.portfolio_id,
            net_improvement_bps=round(net, 4),
            estimated_transaction_cost_bps=round(estimated_cost, 4),
            safety_margin_bps=self.safety_margin_bps,
            weekly_turnover=round(weekly_turnover, 6),
            risk_gate_status=candidate_risk.status,
            reason_codes=reasons,
        )
