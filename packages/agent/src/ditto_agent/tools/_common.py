"""Shared validation and envelope construction for read-only evidence tools."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, cast

from ditto_application.queries.evidence_contracts import (
    DecisionEvidenceReadModel,
    EvidenceArtifactReference,
    EvidenceTemporalContext,
    ResearchEvidenceReadModel,
)

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import TemporalToolContext
from ditto_agent.models.port import ModelToolKind, ModelToolSpec

_TRUSTED_CONTEXT_FIELDS = frozenset(
    {
        "decision_time",
        "knowledge_cutoff",
        "publication_cutoff",
        "source_snapshot_id",
        "execution_eligible_at",
        "allowed_universe",
        "license_class",
        "egress_class",
        "campaign_authorization_id",
        "campaign_authority_hash",
    }
)


class EvidenceFunctionTool(Protocol):
    """Structural contract used by the deterministic read-tool registry."""

    @property
    def spec(self) -> ModelToolSpec:
        """Return the immutable provider-facing function declaration."""
        ...

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        """Execute against a host-injected temporal context."""
        ...


def object_schema(
    *,
    properties: Mapping[str, object],
    required: tuple[str, ...],
) -> Mapping[str, object]:
    """Build a closed JSON object schema without trusted context fields."""
    overlap = _TRUSTED_CONTEXT_FIELDS.intersection(properties)
    if overlap:
        raise ValueError(
            f"tool schema exposes trusted context fields: {sorted(overlap)}"
        )
    return {
        "type": "object",
        "properties": dict(properties),
        "required": required,
        "additionalProperties": False,
    }


def function_spec(
    *,
    name: str,
    description: str,
    properties: Mapping[str, object],
    required: tuple[str, ...],
) -> ModelToolSpec:
    """Create one no-approval, read-only function tool spec."""
    return ModelToolSpec(
        kind=ModelToolKind.FUNCTION,
        name=name,
        description=description,
        input_schema=object_schema(properties=properties, required=required),
        requires_approval=False,
    )


class Arguments:
    """Exact typed reader for provider-supplied JSON arguments."""

    def __init__(
        self,
        value: Mapping[str, object],
        *,
        required: tuple[str, ...],
        optional: tuple[str, ...] = (),
    ) -> None:
        allowed = frozenset((*required, *optional))
        unexpected = tuple(sorted(set(value).difference(allowed)))
        missing = tuple(field for field in required if field not in value)
        if unexpected:
            raise ValueError(f"unexpected arguments: {unexpected}")
        if missing:
            raise ValueError(f"missing required arguments: {missing}")
        self._value = value

    def text(self, field: str) -> str:
        """Read one canonical non-empty string."""
        value = self._value[field]
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError(f"{field} must be a non-empty canonical string")
        return value

    def optional_text(self, field: str) -> str | None:
        """Read one absent/null or canonical non-empty string."""
        value = self._value.get(field)
        if value is None:
            return None
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError(f"{field} must be null or a non-empty canonical string")
        return value

    def positive_integer(self, field: str) -> int:
        """Read one positive integer, excluding booleans."""
        value = self._value[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{field} must be a positive integer")
        return value

    def boolean(self, field: str, *, default: bool = False) -> bool:
        """Read one optional strict boolean."""
        value = self._value.get(field, default)
        if not isinstance(value, bool):
            raise ValueError(f"{field} must be a boolean")
        return value


def application_context(context: TemporalToolContext) -> EvidenceTemporalContext:
    """Project a trusted Agent context into the application leaf contract."""
    return EvidenceTemporalContext(
        decision_time=context.decision_time,
        knowledge_cutoff=context.knowledge_cutoff,
        publication_cutoff=context.publication_cutoff,
        source_snapshot_id=context.source_snapshot_id,
    )


def _artifact_payload(
    artifact: EvidenceArtifactReference,
) -> Mapping[str, object]:
    return {
        "artifact_id": artifact.artifact_id,
        "artifact_kind": artifact.artifact_kind,
        "content_hash": artifact.content_hash,
        "schema_hash": artifact.schema_hash,
    }


def _artifact_ref(artifact: EvidenceArtifactReference) -> str:
    schema = f":schema256:{artifact.schema_hash}" if artifact.schema_hash else ""
    return (
        f"artifact:{artifact.artifact_kind}:{artifact.artifact_id}"
        f":sha256:{artifact.content_hash}{schema}"
    )


@dataclass(frozen=True, slots=True)
class _EnvelopeSource:
    tool_name: str
    kind: str
    identity: Mapping[str, object]
    payload_schema_version: int
    payload_hash: str
    payload_value: Mapping[str, object]
    artifacts: tuple[EvidenceArtifactReference, ...]
    lineage: tuple[str, ...]


def _seal(
    source: _EnvelopeSource,
    *,
    context: TemporalToolContext,
) -> EvidenceEnvelope:
    artifact_payloads = tuple(_artifact_payload(item) for item in source.artifacts)
    result: Mapping[str, object] = {
        "schema_version": 1,
        "kind": source.kind,
        **source.identity,
        "payload_schema_version": source.payload_schema_version,
        "payload_hash": source.payload_hash,
        "payload": source.payload_value,
        "artifacts": artifact_payloads,
    }
    artifact_refs = tuple(
        dict.fromkeys(
            (
                f"payload:sha256:{source.payload_hash}",
                *(_artifact_ref(item) for item in source.artifacts),
            )
        )
    )
    evidence_hash = canonical_sha256(
        {
            "tool_name": source.tool_name,
            "result": result,
            "artifact_refs": artifact_refs,
            "temporal_context": context.canonical_payload(),
            "lineage": source.lineage,
        }
    )
    return EvidenceEnvelope.seal(
        evidence_id=f"evidence-{evidence_hash}",
        tool_name=source.tool_name,
        result=result,
        artifact_refs=artifact_refs,
        temporal_context=context,
        lineage=source.lineage,
    )


def seal_research_evidence(
    *,
    tool_name: str,
    expected_kind: str,
    read_model: ResearchEvidenceReadModel,
    context: TemporalToolContext,
) -> EvidenceEnvelope:
    """Validate an application research projection and seal it for the model."""
    if read_model.temporal_context != application_context(context):
        raise ValueError("application evidence temporal context mismatch")
    if read_model.kind.value != expected_kind:
        raise ValueError("application evidence kind mismatch")
    return _seal(
        _EnvelopeSource(
            tool_name=tool_name,
            kind=expected_kind,
            identity={
                "subject_id": read_model.subject_id,
                "subject_version": read_model.subject_version,
                "strategy_id": read_model.strategy_id,
                "strategy_version": read_model.strategy_version,
                "dataset_id": read_model.dataset_id,
            },
            payload_schema_version=read_model.payload.schema_version,
            payload_hash=read_model.payload.payload_hash,
            payload_value=cast(Mapping[str, object], read_model.payload.value),
            artifacts=read_model.artifact_refs,
            lineage=read_model.lineage,
        ),
        context=context,
    )


def seal_decision_evidence(
    *,
    tool_name: str,
    kind: str,
    read_model: DecisionEvidenceReadModel,
    context: TemporalToolContext,
) -> EvidenceEnvelope:
    """Validate an application decision projection and seal it for the model."""
    if read_model.temporal_context != application_context(context):
        raise ValueError("application evidence temporal context mismatch")
    return _seal(
        _EnvelopeSource(
            tool_name=tool_name,
            kind=kind,
            identity={
                "strategy_id": read_model.strategy_id,
                "strategy_version": read_model.strategy_version,
                "trade_date": read_model.trade_date,
                "account_id": read_model.account_id,
                "sleeve_id": read_model.sleeve_id,
                "readiness": read_model.readiness,
            },
            payload_schema_version=read_model.payload.schema_version,
            payload_hash=read_model.payload.payload_hash,
            payload_value=cast(Mapping[str, object], read_model.payload.value),
            artifacts=read_model.artifact_refs,
            lineage=read_model.lineage,
        ),
        context=context,
    )


def read_only_tools(
    tools: Mapping[str, EvidenceFunctionTool],
) -> Mapping[str, EvidenceFunctionTool]:
    """Expose an immutable tool index."""
    return MappingProxyType(dict(tools))


__all__ = [
    "Arguments",
    "EvidenceFunctionTool",
    "application_context",
    "function_spec",
    "read_only_tools",
    "seal_decision_evidence",
    "seal_research_evidence",
]
