"""Evidence envelopes and claim-level grounding contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import cast

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts._validation import (
    freeze_json,
    normalized_text,
    normalized_unique_tuple,
    sha256_hex,
)
from ditto_agent.contracts.temporal import TemporalToolContext


@dataclass(frozen=True, slots=True)
class EvidenceEnvelope:
    """Immutable tool result bound to PIT context, artifacts, and lineage."""

    evidence_id: str
    tool_name: str
    result: Mapping[str, object]
    artifact_refs: tuple[str, ...]
    temporal_context: TemporalToolContext
    lineage: tuple[str, ...]
    integrity_hash: str

    def __post_init__(self) -> None:
        """Deep-freeze evidence and validate its canonical integrity digest."""
        object.__setattr__(
            self, "evidence_id", normalized_text(self.evidence_id, field="evidence_id")
        )
        object.__setattr__(
            self, "tool_name", normalized_text(self.tool_name, field="tool_name")
        )
        frozen = freeze_json(self.result, field="result")
        if not isinstance(frozen, Mapping):
            raise TypeError("result must be a mapping")
        object.__setattr__(self, "result", frozen)
        object.__setattr__(
            self,
            "artifact_refs",
            normalized_unique_tuple(self.artifact_refs, field="artifact_refs"),
        )
        object.__setattr__(
            self, "lineage", normalized_unique_tuple(self.lineage, field="lineage")
        )
        object.__setattr__(
            self,
            "integrity_hash",
            sha256_hex(self.integrity_hash, field="integrity_hash"),
        )

    @classmethod
    def seal(
        cls,
        *,
        evidence_id: str,
        tool_name: str,
        result: Mapping[str, object],
        artifact_refs: tuple[str, ...],
        temporal_context: TemporalToolContext,
        lineage: tuple[str, ...],
    ) -> EvidenceEnvelope:
        """Seal normalized evidence under a canonical integrity hash."""
        frozen = freeze_json(result, field="result")
        if not isinstance(frozen, Mapping):
            raise TypeError("result must be a mapping")
        frozen_result = cast(Mapping[str, object], frozen)
        envelope = cls(
            evidence_id=evidence_id,
            tool_name=tool_name,
            result=frozen_result,
            artifact_refs=artifact_refs,
            temporal_context=temporal_context,
            lineage=lineage,
            integrity_hash="0" * 64,
        )
        return replace(
            envelope,
            integrity_hash=canonical_sha256(envelope.integrity_payload()),
        )

    @staticmethod
    def _integrity_payload(
        *,
        evidence_id: str,
        tool_name: str,
        result: Mapping[str, object],
        artifact_refs: tuple[str, ...],
        temporal_context: TemporalToolContext,
        lineage: tuple[str, ...],
    ) -> dict[str, object]:
        return {
            "evidence_id": evidence_id,
            "tool_name": tool_name,
            "result": result,
            "artifact_refs": artifact_refs,
            "temporal_context": temporal_context.canonical_payload(),
            "lineage": lineage,
        }

    def verify_integrity(self) -> bool:
        """Verify that no evidence, context, artifact, or lineage field drifted."""
        return canonical_sha256(self.integrity_payload()) == self.integrity_hash

    def integrity_payload(self) -> dict[str, object]:
        """Return normalized fields authenticated by the integrity hash."""
        return self._integrity_payload(
            evidence_id=self.evidence_id,
            tool_name=self.tool_name,
            result=self.result,
            artifact_refs=self.artifact_refs,
            temporal_context=self.temporal_context,
            lineage=self.lineage,
        )


@dataclass(frozen=True, slots=True)
class GroundedClaim:
    """One claim that cites at least one concrete evidence envelope."""

    claim: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        """Require a bounded claim and unique non-empty evidence references."""
        object.__setattr__(
            self, "claim", normalized_text(self.claim, field="claim", maximum=4096)
        )
        object.__setattr__(
            self,
            "evidence_refs",
            normalized_unique_tuple(self.evidence_refs, field="evidence_refs"),
        )


@dataclass(frozen=True, slots=True)
class GroundedAnswer:
    """Grounded claims or a structured refusal with uncertainty metadata."""

    claims: tuple[GroundedClaim, ...]
    uncertainty: str | None
    missing_evidence: tuple[str, ...]
    refusal_reason: str | None

    def __post_init__(self) -> None:
        """Enforce mutual exclusion between grounded claims and refusal."""
        if not self.claims and self.refusal_reason is None:
            raise ValueError("an answer without claims requires a refusal reason")
        if self.claims and self.refusal_reason is not None:
            raise ValueError("a grounded answer cannot also be a refusal")
        if self.uncertainty is not None:
            object.__setattr__(
                self,
                "uncertainty",
                normalized_text(self.uncertainty, field="uncertainty", maximum=4096),
            )
        if self.missing_evidence:
            object.__setattr__(
                self,
                "missing_evidence",
                normalized_unique_tuple(
                    self.missing_evidence, field="missing_evidence"
                ),
            )
        if self.refusal_reason is not None:
            object.__setattr__(
                self,
                "refusal_reason",
                normalized_text(
                    self.refusal_reason, field="refusal_reason", maximum=4096
                ),
            )


__all__ = ["EvidenceEnvelope", "GroundedAnswer", "GroundedClaim"]
