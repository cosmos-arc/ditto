"""Deterministic claim-level grounding and structured abstention."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_agent.contracts._validation import normalized_text
from ditto_agent.contracts.evidence import (
    EvidenceEnvelope,
    GroundedAnswer,
    GroundedClaim,
)
from ditto_agent.contracts.temporal import TemporalToolContext


@dataclass(frozen=True, slots=True)
class GroundingDraft:
    """Untrusted structured claim intent returned by a model."""

    claim: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        """Normalize intent while allowing the builder to reject missing refs."""
        object.__setattr__(
            self,
            "claim",
            normalized_text(self.claim, field="claim", maximum=4096),
        )
        normalized_refs = tuple(
            normalized_text(item, field="evidence_ref") for item in self.evidence_refs
        )
        if len(set(normalized_refs)) != len(normalized_refs):
            raise ValueError("evidence_refs must not contain duplicates")
        object.__setattr__(self, "evidence_refs", normalized_refs)


@dataclass(frozen=True, slots=True)
class ToolExecutionFailure:
    """Safe error identity supplied by the deterministic host."""

    call_id: str
    tool_name: str
    error_code: str

    def __post_init__(self) -> None:
        """Normalize safe identifiers without accepting a model-authored message."""
        for field_name in ("call_id", "tool_name", "error_code"):
            object.__setattr__(
                self,
                field_name,
                normalized_text(getattr(self, field_name), field=field_name),
            )


class GroundingBuilder:
    """Convert model claim intents only when every cited envelope is trustworthy."""

    def __init__(self, *, expected_context: TemporalToolContext) -> None:
        self._expected_context = expected_context

    def build(
        self,
        *,
        drafts: tuple[GroundingDraft, ...],
        evidence: tuple[EvidenceEnvelope, ...],
        uncertainty: str | None = None,
        tool_failures: tuple[ToolExecutionFailure, ...] = (),
    ) -> GroundedAnswer:
        """Produce a fully cited answer or a deterministic structured refusal."""
        if tool_failures:
            missing = tuple(
                dict.fromkeys(
                    f"tool:{item.tool_name}:{item.call_id}" for item in tool_failures
                )
            )
            return self._refuse(
                reason="tool_execution_failed",
                missing=missing,
                uncertainty=uncertainty,
            )

        index, evidence_failure = self._validated_evidence_index(evidence)
        if evidence_failure is not None:
            reason, missing = evidence_failure
            return self._refuse(
                reason=reason,
                missing=missing,
                uncertainty=uncertainty,
            )
        if not drafts:
            return self._refuse(
                reason="no_grounded_claims",
                missing=("claim:1",),
                uncertainty=uncertainty,
            )

        missing_refs: list[str] = []
        for position, draft in enumerate(drafts, start=1):
            if not draft.evidence_refs:
                missing_refs.append(f"claim:{position}")
            else:
                missing_refs.extend(
                    ref for ref in draft.evidence_refs if ref not in index
                )
        if missing_refs:
            return self._refuse(
                reason="missing_evidence",
                missing=tuple(dict.fromkeys(missing_refs)),
                uncertainty=uncertainty,
            )
        claims = tuple(
            GroundedClaim(claim=item.claim, evidence_refs=item.evidence_refs)
            for item in drafts
        )
        return GroundedAnswer(
            claims=claims,
            uncertainty=uncertainty,
            missing_evidence=(),
            refusal_reason=None,
        )

    def _validated_evidence_index(
        self,
        evidence: tuple[EvidenceEnvelope, ...],
    ) -> tuple[
        dict[str, EvidenceEnvelope],
        tuple[str, tuple[str, ...]] | None,
    ]:
        index: dict[str, EvidenceEnvelope] = {}
        for item in evidence:
            existing = index.get(item.evidence_id)
            if existing is not None and existing.integrity_hash != item.integrity_hash:
                return index, (
                    "conflicting_evidence_identity",
                    (item.evidence_id,),
                )
            index[item.evidence_id] = item
        invalid = tuple(
            item.evidence_id for item in index.values() if not item.verify_integrity()
        )
        if invalid:
            return index, ("evidence_integrity_failed", invalid)
        wrong_context = tuple(
            item.evidence_id
            for item in index.values()
            if item.temporal_context != self._expected_context
        )
        if wrong_context:
            return index, ("evidence_context_conflict", wrong_context)
        return index, None

    @staticmethod
    def _refuse(
        *,
        reason: str,
        missing: tuple[str, ...],
        uncertainty: str | None,
    ) -> GroundedAnswer:
        return GroundedAnswer(
            claims=(),
            uncertainty=uncertainty,
            missing_evidence=missing,
            refusal_reason=reason,
        )


__all__ = ["GroundingBuilder", "GroundingDraft", "ToolExecutionFailure"]
