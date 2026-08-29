"""Fail-closed evidence policy applied before any model provider call."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import cast

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts._validation import (
    freeze_json,
    normalized_text,
    sha256_hex,
)
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import EgressClass, TemporalToolContext


class EvidenceEgressPolicyError(PermissionError):
    """Evidence cannot cross the requested model-provider boundary."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.details = MappingProxyType(dict(details or {}))


@dataclass(frozen=True, slots=True)
class ModelEvidencePayload:
    """Minimal immutable evidence projection allowed to enter a model request."""

    evidence_id: str
    tool_name: str
    result: Mapping[str, object]
    artifact_refs: tuple[str, ...]
    lineage: tuple[str, ...]
    temporal_context_hash: str
    integrity_hash: str
    payload_hash: str

    def __post_init__(self) -> None:
        """Freeze model-visible data and validate all stored digests."""
        frozen = freeze_json(self.result, field="model evidence result")
        if not isinstance(frozen, Mapping):
            raise TypeError("model evidence result must be a mapping")
        object.__setattr__(self, "result", cast(Mapping[str, object], frozen))
        object.__setattr__(
            self,
            "temporal_context_hash",
            sha256_hex(
                self.temporal_context_hash,
                field="temporal_context_hash",
            ),
        )
        object.__setattr__(
            self,
            "integrity_hash",
            sha256_hex(self.integrity_hash, field="integrity_hash"),
        )
        object.__setattr__(
            self,
            "payload_hash",
            sha256_hex(self.payload_hash, field="payload_hash"),
        )

    def _hash_payload(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "tool_name": self.tool_name,
            "result": self.result,
            "artifact_refs": self.artifact_refs,
            "lineage": self.lineage,
            "temporal_context_hash": self.temporal_context_hash,
            "integrity_hash": self.integrity_hash,
        }

    def verify_payload_hash(self) -> bool:
        """Return whether the model projection is byte-identical to its seal."""
        return canonical_sha256(self._hash_payload()) == self.payload_hash

    @classmethod
    def from_evidence(
        cls,
        evidence: EvidenceEnvelope,
        *,
        temporal_context_hash: str,
    ) -> ModelEvidencePayload:
        """Project a verified envelope without internal policy or license notes."""
        payload = cls(
            evidence_id=evidence.evidence_id,
            tool_name=evidence.tool_name,
            result=evidence.result,
            artifact_refs=evidence.artifact_refs,
            lineage=evidence.lineage,
            temporal_context_hash=temporal_context_hash,
            integrity_hash=evidence.integrity_hash,
            payload_hash="0" * 64,
        )
        return replace(payload, payload_hash=canonical_sha256(payload._hash_payload()))


class EvidenceEgressPolicy:
    """Require explicit cloud and license grants for every evidence envelope."""

    def __init__(self, *, approved_license_classes: tuple[str, ...]) -> None:
        normalized = tuple(
            normalized_text(item, field="approved license class")
            for item in approved_license_classes
        )
        if len(normalized) != len(set(normalized)):
            raise ValueError("approved license classes must not contain duplicates")
        self._approved_license_classes = frozenset(normalized)

    @classmethod
    def deny_all(cls) -> EvidenceEgressPolicy:
        """Build the default policy used while no cloud dataset grant exists."""
        return cls(approved_license_classes=())

    def prepare_for_model(
        self,
        evidence: tuple[EvidenceEnvelope, ...],
        *,
        context: object,
    ) -> tuple[ModelEvidencePayload, ...]:
        """Atomically validate and project one context-bound evidence batch."""
        if not isinstance(context, TemporalToolContext):
            raise EvidenceEgressPolicyError(
                "Model egress requires a trusted temporal context",
                reason_code="evidence_temporal_context_invalid",
            )
        if context.egress_class is not EgressClass.CLOUD_ALLOWED:
            raise EvidenceEgressPolicyError(
                "Evidence is not classified for cloud egress",
                reason_code="evidence_egress_not_cloud_allowed",
            )
        if context.license_class not in self._approved_license_classes:
            raise EvidenceEgressPolicyError(
                "Evidence license class is not approved for model egress",
                reason_code="evidence_license_not_approved",
            )
        if not evidence:
            raise EvidenceEgressPolicyError(
                "Model egress requires at least one evidence envelope",
                reason_code="evidence_batch_empty",
            )
        identifiers = tuple(item.evidence_id for item in evidence)
        if len(identifiers) != len(set(identifiers)):
            raise EvidenceEgressPolicyError(
                "Evidence batch contains duplicate identities",
                reason_code="evidence_identity_duplicate",
            )
        context_hash = canonical_sha256(context.canonical_payload())
        ordered = sorted(evidence, key=lambda item: item.evidence_id)
        payloads: list[ModelEvidencePayload] = []
        for item in ordered:
            if not item.verify_integrity():
                raise EvidenceEgressPolicyError(
                    "Evidence integrity verification failed",
                    reason_code="evidence_integrity_invalid",
                    details={"evidence_id": item.evidence_id},
                )
            item_context_hash = canonical_sha256(
                item.temporal_context.canonical_payload()
            )
            if item_context_hash != context_hash:
                raise EvidenceEgressPolicyError(
                    "Evidence belongs to a different temporal authority",
                    reason_code="evidence_temporal_context_mismatch",
                    details={"evidence_id": item.evidence_id},
                )
            payloads.append(
                ModelEvidencePayload.from_evidence(
                    item,
                    temporal_context_hash=context_hash,
                )
            )
        return tuple(payloads)


__all__ = [
    "EvidenceEgressPolicy",
    "EvidenceEgressPolicyError",
    "ModelEvidencePayload",
]
