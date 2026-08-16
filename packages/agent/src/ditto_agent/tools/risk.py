"""Read-only risk evidence function tool."""

from __future__ import annotations

from ditto_agent.tools.decision import (
    DecisionProjectionEvidenceTool,
    decision_function_spec,
)


class RiskEvidenceTool(DecisionProjectionEvidenceTool):
    """Expose the application-owned V3 risk projection."""

    spec = decision_function_spec(
        name="risk_evidence",
        description="Read one exact DailyDecision V3 risk projection.",
    )
    evidence_kind = "risk"


__all__ = ["RiskEvidenceTool"]
