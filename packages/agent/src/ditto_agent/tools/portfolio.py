"""Read-only portfolio evidence function tool."""

from __future__ import annotations

from ditto_agent.tools.decision import (
    DecisionProjectionEvidenceTool,
    decision_function_spec,
)


class PortfolioEvidenceTool(DecisionProjectionEvidenceTool):
    """Expose the application-owned V3 portfolio projection."""

    spec = decision_function_spec(
        name="portfolio_evidence",
        description="Read one exact DailyDecision V3 portfolio projection.",
    )
    evidence_kind = "portfolio"


__all__ = ["PortfolioEvidenceTool"]
