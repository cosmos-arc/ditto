"""Host-scoped, read-only research memory Agent tool."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from ditto_application.queries.research_memory_contracts import (
    ResearchMemoryQueryPort,
    ResearchMemoryScope,
)

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts._validation import normalized_text
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import TemporalToolContext
from ditto_agent.tools._common import Arguments, application_context, function_spec

RESEARCH_MEMORY_TOOL = "research_memory"
_SHA256_HEX_LENGTH = 64


@dataclass(frozen=True, slots=True)
class ResearchMemoryToolExecutionContext:
    """Retrieval scope injected by the trusted Campaign host."""

    campaign_id: str
    strategy_family_ref: str | None

    def __post_init__(self) -> None:
        """Normalize scope identities before querying Application."""
        object.__setattr__(
            self,
            "campaign_id",
            normalized_text(self.campaign_id, field="campaign_id"),
        )
        if self.strategy_family_ref is not None:
            object.__setattr__(
                self,
                "strategy_family_ref",
                normalized_text(
                    self.strategy_family_ref,
                    field="strategy_family_ref",
                ),
            )


def _artifact_refs(payload: Mapping[str, object], payload_hash: str) -> tuple[str, ...]:
    raw_items = payload.get("items", ())
    if not isinstance(raw_items, Sequence) or isinstance(
        raw_items,
        (str, bytes, bytearray),
    ):
        raise ValueError("application memory payload items are invalid")
    references = [f"research-memory:sha256:{payload_hash}"]
    for raw_item in cast("Sequence[object]", raw_items):
        if not isinstance(raw_item, Mapping):
            raise ValueError("application memory payload item is invalid")
        item = cast("Mapping[str, object]", raw_item)
        raw_evidence = item.get("evidence_refs", ())
        if not isinstance(raw_evidence, Sequence) or isinstance(
            raw_evidence,
            (str, bytes, bytearray),
        ):
            raise ValueError("application memory evidence refs are invalid")
        evidence_refs = tuple(cast("Sequence[object]", raw_evidence))
        if not evidence_refs or any(
            type(value) is not str
            or len(value) != _SHA256_HEX_LENGTH
            or any(character not in "0123456789abcdef" for character in value)
            for value in evidence_refs
        ):
            raise ValueError("application memory evidence refs are invalid")
        references.extend(
            f"research-evidence:sha256:{value}" for value in evidence_refs
        )
    return tuple(dict.fromkeys(references))


class ResearchMemoryTool:
    """Expose only active, PIT-visible memory inside a host-owned scope."""

    spec = function_spec(
        name=RESEARCH_MEMORY_TOOL,
        description=(
            "Read active research memory visible in the current Campaign scope."
        ),
        properties={},
        required=(),
    )

    def __init__(self, *, facade: ResearchMemoryQueryPort) -> None:
        self._facade = facade

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
        execution: ResearchMemoryToolExecutionContext,
    ) -> EvidenceEnvelope:
        """Inject exact scope and seal the Application read model."""
        Arguments(arguments, required=())
        if type(execution) is not ResearchMemoryToolExecutionContext:
            raise ValueError("execution must be ResearchMemoryToolExecutionContext")
        scope = ResearchMemoryScope(
            campaign_id=execution.campaign_id,
            strategy_family_ref=execution.strategy_family_ref,
        )
        result = self._facade.list_visible(
            scope=scope,
            context=application_context(context),
        )
        if (
            result.scope != scope
            or result.temporal_context != application_context(context)
            or not result.verify_integrity()
        ):
            raise ValueError("application research memory result is invalid")
        payload = cast("Mapping[str, object]", result.payload.value)
        envelope_result: Mapping[str, object] = {
            "schema_version": 1,
            "kind": RESEARCH_MEMORY_TOOL,
            "scope": scope.canonical_payload(),
            "payload_schema_version": result.payload.schema_version,
            "payload_hash": result.payload.payload_hash,
            "payload": payload,
            "result_hash": result.result_hash,
        }
        lineage = (f"campaign:{scope.campaign_id}",)
        if scope.strategy_family_ref is not None:
            lineage = (*lineage, f"strategy-family:{scope.strategy_family_ref}")
        evidence_hash = canonical_sha256(
            {
                "tool_name": RESEARCH_MEMORY_TOOL,
                "result_hash": result.result_hash,
                "temporal_context": context.canonical_payload(),
                "lineage": lineage,
            }
        )
        return EvidenceEnvelope.seal(
            evidence_id=f"evidence-{evidence_hash}",
            tool_name=RESEARCH_MEMORY_TOOL,
            result=envelope_result,
            artifact_refs=_artifact_refs(payload, result.payload.payload_hash),
            temporal_context=context,
            lineage=lineage,
        )


__all__ = [
    "RESEARCH_MEMORY_TOOL",
    "ResearchMemoryTool",
    "ResearchMemoryToolExecutionContext",
]
