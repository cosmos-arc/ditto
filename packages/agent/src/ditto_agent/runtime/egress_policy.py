"""Fail-closed evidence policy applied before any model provider call."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
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
        result: Mapping[str, object] | None = None,
        artifact_refs: tuple[str, ...] | None = None,
    ) -> ModelEvidencePayload:
        """Project a verified envelope without internal policy or license notes."""
        payload = cls(
            evidence_id=evidence.evidence_id,
            tool_name=evidence.tool_name,
            result=evidence.result if result is None else result,
            artifact_refs=(
                evidence.artifact_refs if artifact_refs is None else artifact_refs
            ),
            lineage=evidence.lineage,
            temporal_context_hash=temporal_context_hash,
            integrity_hash=evidence.integrity_hash,
            payload_hash="0" * 64,
        )
        return replace(payload, payload_hash=canonical_sha256(payload._hash_payload()))


_APPROVED_RESEARCH_LICENSE = "approved-research"
_MINIMAL_PROFILE = "approved-research-minimal-v1"
_SELECTION_TOOL = "selection_run_evidence"
_CANDIDATE_FIELDS = (
    "rank",
    "instrument_id",
    "instrument_name",
    "industry_id",
    "score",
    "factor_contributions",
)


def _candidate_rank(item: Mapping[str, object]) -> int:
    rank = item.get("rank")
    return rank if isinstance(rank, int) else 2**31


def _minimal_candidate(item: Mapping[str, object]) -> dict[str, object]:
    projected: dict[str, object] = {}
    for key in _CANDIDATE_FIELDS:
        if key in item:
            projected[key] = item[key]
    return projected


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise EvidenceEgressPolicyError(
            f"{field} must be a mapping",
            reason_code="evidence_minimal_projection_invalid",
        )
    raw = cast(Mapping[object, object], value)
    if not all(isinstance(key, str) for key in raw):
        raise EvidenceEgressPolicyError(
            f"{field} must use string keys",
            reason_code="evidence_minimal_projection_invalid",
        )
    return cast(Mapping[str, object], raw)


def _sequence(value: object, *, field: str) -> Sequence[object]:
    if not isinstance(value, (tuple, list)):
        raise EvidenceEgressPolicyError(
            f"{field} must be a sequence",
            reason_code="evidence_minimal_projection_invalid",
        )
    return cast(Sequence[object], value)


def _selection_projection(
    evidence: EvidenceEnvelope,
) -> tuple[Mapping[str, object], tuple[str, ...]]:
    payload = _mapping(evidence.result.get("payload"), field="selection payload")
    candidates = tuple(
        _mapping(item, field="selection candidate")
        for item in _sequence(payload.get("candidates"), field="selection candidates")
    )
    exclusions = tuple(
        _mapping(item, field="selection exclusion")
        for item in _sequence(payload.get("exclusions"), field="selection exclusions")
    )
    ranked: list[Mapping[str, object]] = sorted(candidates, key=_candidate_rank)
    summary: Counter[tuple[str, str]] = Counter(
        (
            str(item.get("stage", "unknown")),
            str(item.get("reason_code", "unknown")),
        )
        for item in exclusions
    )
    top_candidates: tuple[dict[str, object], ...] = tuple(
        _minimal_candidate(item) for item in ranked[:3]
    )
    exclusion_summary: tuple[dict[str, object], ...] = tuple(
        {"stage": stage, "reason_code": reason_code, "count": count}
        for (stage, reason_code), count in sorted(summary.items())
    )
    minimal_payload: dict[str, object] = {
        "run_id": payload.get("run_id", evidence.result.get("run_id")),
        "status": payload.get("status", evidence.result.get("status")),
        "seed": payload.get("seed"),
        "candidate_count": len(candidates),
        "exclusion_count": len(exclusions),
        "top_candidates": top_candidates,
        "exclusion_summary": exclusion_summary,
        "missing_inputs": payload.get("missing_inputs", ()),
        "source_snapshot_ids": payload.get("source_snapshot_ids", ()),
    }
    result: dict[str, object] = {
        "schema_version": 1,
        "kind": "selection_run",
        "redaction_profile": _MINIMAL_PROFILE,
        "source_payload_hash": evidence.result.get("payload_hash"),
        "payload": minimal_payload,
    }
    artifact_refs = tuple(
        dict.fromkeys(
            (
                *evidence.artifact_refs,
                f"minimal-egress:sha256:{canonical_sha256(minimal_payload)}",
            )
        )
    )
    return result, artifact_refs


def _model_projection(
    evidence: EvidenceEnvelope,
    *,
    context: TemporalToolContext,
) -> tuple[Mapping[str, object], tuple[str, ...]]:
    if (
        context.license_class == _APPROVED_RESEARCH_LICENSE
        and evidence.tool_name == _SELECTION_TOOL
    ):
        return _selection_projection(evidence)
    return evidence.result, evidence.artifact_refs


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
            result, artifact_refs = _model_projection(item, context=context)
            payloads.append(
                ModelEvidencePayload.from_evidence(
                    item,
                    temporal_context_hash=context_hash,
                    result=result,
                    artifact_refs=artifact_refs,
                )
            )
        return tuple(payloads)


__all__ = [
    "EvidenceEgressPolicy",
    "EvidenceEgressPolicyError",
    "ModelEvidencePayload",
]
