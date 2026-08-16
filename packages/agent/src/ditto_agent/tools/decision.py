"""DailyDecision V3 evidence function tool and shared projection adapter."""

from __future__ import annotations

from collections.abc import Mapping

from ditto_application.queries.evidence_contracts import DecisionEvidenceQueryPort

from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import TemporalToolContext
from ditto_agent.models.port import ModelToolSpec
from ditto_agent.tools._common import (
    Arguments,
    application_context,
    function_spec,
    seal_decision_evidence,
)

_TEXT = {"type": "string", "minLength": 1}
_DECISION_PROPERTIES = {
    "strategy_id": _TEXT,
    "strategy_version": _TEXT,
    "trade_date": _TEXT,
    "account_id": _TEXT,
    "sleeve_id": _TEXT,
}
_DECISION_REQUIRED = tuple(_DECISION_PROPERTIES)


def decision_function_spec(*, name: str, description: str) -> ModelToolSpec:
    """Build the shared exact-identity schema for a V3 projection tool."""
    return function_spec(
        name=name,
        description=description,
        properties=_DECISION_PROPERTIES,
        required=_DECISION_REQUIRED,
    )


class DecisionProjectionEvidenceTool:
    """Base adapter for application-owned portfolio/risk/decision projections."""

    spec: ModelToolSpec
    evidence_kind: str

    def __init__(self, *, facade: DecisionEvidenceQueryPort) -> None:
        self._facade = facade

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        """Read one exact V3 projection under host-owned temporal context."""
        parsed = Arguments(arguments, required=_DECISION_REQUIRED)
        result = self._facade.get_evidence(
            strategy_id=parsed.text("strategy_id"),
            strategy_version=parsed.text("strategy_version"),
            trade_date=parsed.text("trade_date"),
            account_id=parsed.text("account_id"),
            sleeve_id=parsed.text("sleeve_id"),
            context=application_context(context),
        )
        return seal_decision_evidence(
            tool_name=self.spec.name,
            kind=self.evidence_kind,
            read_model=result,
            context=context,
        )


class DecisionEvidenceTool(DecisionProjectionEvidenceTool):
    """Expose the full, ready-or-review DailyDecision V3 projection."""

    spec = decision_function_spec(
        name="daily_decision_v3_evidence",
        description="Read one exact DailyDecision V3 evidence projection.",
    )
    evidence_kind = "daily_decision_v3"


__all__ = [
    "DecisionEvidenceTool",
    "DecisionProjectionEvidenceTool",
    "decision_function_spec",
]
