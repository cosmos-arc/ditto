"""Pure Application leaf contracts for host-scoped research-memory reads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast

from ditto_application.exceptions import AppQueryError
from ditto_application.mutation_idempotency import canonical_request_hash
from ditto_application.queries.evidence_contracts import (
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
)


def _text(value: object, field: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise AppQueryError(
            "research memory scope is invalid",
            details={
                "code": "RESEARCH_MEMORY_QUERY_INVALID",
                "reason": "research_memory_scope_invalid",
                "field": field,
            },
        )
    return value


def _utc_text(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class ResearchMemoryScope:
    """Host-owned local and optional strategy-family retrieval boundary."""

    campaign_id: str
    strategy_family_ref: str | None

    def __post_init__(self) -> None:
        """Reject absent or padded scope identities."""
        object.__setattr__(self, "campaign_id", _text(self.campaign_id, "campaign_id"))
        if self.strategy_family_ref is not None:
            object.__setattr__(
                self,
                "strategy_family_ref",
                _text(self.strategy_family_ref, "strategy_family_ref"),
            )

    def canonical_payload(self) -> dict[str, object]:
        """Return the exact retrieval authority bound into the result hash."""
        return {
            "campaign_id": self.campaign_id,
            "strategy_family_ref": self.strategy_family_ref,
        }


@dataclass(frozen=True, slots=True)
class ResearchMemoryReadModel:
    """Content-addressed structured memory safe for Agent consumption."""

    scope: ResearchMemoryScope
    temporal_context: EvidenceTemporalContext
    payload: EvidencePayloadReadModel
    result_hash: str

    def canonical_payload(self) -> dict[str, object]:
        """Return identities and payload digest covered by ``result_hash``."""
        context = self.temporal_context
        return {
            "schema_version": 1,
            "kind": "research_memory",
            "scope": self.scope.canonical_payload(),
            "temporal_context": {
                "decision_time": _utc_text(context.decision_time),
                "knowledge_cutoff": _utc_text(context.knowledge_cutoff),
                "publication_cutoff": _utc_text(context.publication_cutoff),
                "source_snapshot_id": context.source_snapshot_id,
            },
            "payload_schema_version": self.payload.schema_version,
            "payload_hash": self.payload.payload_hash,
        }

    def verify_integrity(self) -> bool:
        """Verify scope, temporal, and payload identity after transport."""
        verified = EvidencePayloadReadModel.seal(
            schema_version=self.payload.schema_version,
            value=cast("dict[str, object]", dict(self.payload.value)),
        )
        return (
            verified.payload_hash == self.payload.payload_hash
            and canonical_request_hash(self.canonical_payload()) == self.result_hash
        )


class ResearchMemoryQueryPort(Protocol):
    """Agent-safe leaf port for one exact host-scoped memory query."""

    def list_visible(
        self,
        *,
        scope: ResearchMemoryScope,
        context: EvidenceTemporalContext,
    ) -> ResearchMemoryReadModel:
        """Return active memory visible inside the supplied trusted boundary."""
        ...


__all__ = [
    "ResearchMemoryQueryPort",
    "ResearchMemoryReadModel",
    "ResearchMemoryScope",
]
