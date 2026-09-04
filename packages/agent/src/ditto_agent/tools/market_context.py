"""Read-only certified MarketContext evidence function tool."""

from __future__ import annotations

from collections.abc import Mapping

from ditto_application.queries.evidence_contracts import (
    MarketContextEvidenceQueryPort,
)

from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import TemporalToolContext
from ditto_agent.models.port import ModelToolSpec
from ditto_agent.tools._common import (
    Arguments,
    application_context,
    function_spec,
    seal_market_context_evidence,
)


class MarketContextEvidenceTool:
    """Expose the exact host-selected certified MarketContext to the model."""

    spec: ModelToolSpec = function_spec(
        name="market_context_evidence",
        description=(
            "Read the certified exact-PIT MarketContext selected by the host, "
            "including regime, drivers, metrics, impacts, gaps, and evidence refs."
        ),
        properties={},
        required=(),
    )

    def __init__(self, *, facade: MarketContextEvidenceQueryPort) -> None:
        self._facade = facade

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        """Read without accepting any model-controlled temporal identity."""
        _ = Arguments(arguments, required=())
        result = self._facade.get_evidence(context=application_context(context))
        return seal_market_context_evidence(
            tool_name=self.spec.name,
            read_model=result,
            context=context,
        )


__all__ = ["MarketContextEvidenceTool"]
