"""Agent-owned, content-addressed DecisionOpinion and model generator."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast

from ditto_application.processes.risk.agent_decision_briefing import (
    DecisionOpinionGenerationError,
    DecisionOpinionGenerationRequest,
)
from ditto_application.queries.decision_briefing_contracts import (
    DecisionBriefingEvidenceReadModel,
)

from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.contracts._validation import (
    enum_value,
    normalized_text,
    normalized_unique_tuple,
    sha256_hex,
    utc_datetime,
)
from ditto_agent.models.port import (
    AgentModelPort,
    ModelProviderError,
    ModelRequest,
    ModelResult,
)

__all__ = [
    "DecisionOpinion",
    "DecisionOpinionGenerator",
    "DecisionOpinionStatus",
]

_PROMPT = (
    "You produce a shadow-only explanation of immutable DailyDecision V3 evidence. "
    "Return exactly summary, dissent, uncertainty, and evidence_refs. Cite only "
    "supplied artifact IDs. Never propose or emit weights, risk status, actions, "
    "orders, publication, trading, broker operations, or changes to the underlying "
    "V3 report."
)


class DecisionOpinionStatus(StrEnum):
    """Terminal statuses for a shadow-only opinion."""

    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class _DecisionOpinionContent:
    status: DecisionOpinionStatus
    v3_artifact_id: str
    v3_evidence_hash: str
    v3_readiness: str
    summary: str
    dissent: str | None
    uncertainty: str
    evidence_refs: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    reason_code: str | None
    model_profile: str
    prompt_hash: str
    provider_id: str
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class DecisionOpinion:
    """Immutable V3 explanation with no portfolio, risk, action, or order surface."""

    schema_version: int
    opinion_id: str
    shadow_outcome_id: str
    status: DecisionOpinionStatus
    v3_artifact_id: str
    v3_evidence_hash: str
    v3_readiness: str
    summary: str
    dissent: str | None
    uncertainty: str
    evidence_refs: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    reason_code: str | None
    model_profile: str
    prompt_hash: str
    provider_id: str
    generated_at: datetime
    opinion_hash: str

    def __post_init__(self) -> None:
        """Validate the closed shadow contract and derived identities."""
        if self.schema_version != 1:
            raise ValueError("DecisionOpinion schema_version must be 1")
        enum_value(self.status, DecisionOpinionStatus, field="status")
        _normalize_opinion_text(self)
        _normalize_opinion_collections(self)
        _normalize_opinion_hashes(self)
        _validate_opinion_identities(self)
        _validate_opinion_status(self)

    @classmethod
    def create(
        cls,
        content: _DecisionOpinionContent,
    ) -> DecisionOpinion:
        """Seal a normalized opinion under a deterministic content identity."""
        payload = cls._identity_payload(content)
        digest = canonical_sha256(payload)
        return cls(
            schema_version=1,
            opinion_id=f"decision-opinion-{digest}",
            shadow_outcome_id=f"decision-shadow-{digest}",
            status=content.status,
            v3_artifact_id=content.v3_artifact_id,
            v3_evidence_hash=content.v3_evidence_hash,
            v3_readiness=content.v3_readiness,
            summary=content.summary,
            dissent=content.dissent,
            uncertainty=content.uncertainty,
            evidence_refs=content.evidence_refs,
            blocking_reasons=content.blocking_reasons,
            reason_code=content.reason_code,
            model_profile=content.model_profile,
            prompt_hash=content.prompt_hash,
            provider_id=content.provider_id,
            generated_at=content.generated_at,
            opinion_hash=digest,
        )

    @staticmethod
    def _identity_payload(content: _DecisionOpinionContent) -> dict[str, object]:
        return {
            "schema_version": 1,
            "status": content.status,
            "v3_artifact_id": content.v3_artifact_id,
            "v3_evidence_hash": content.v3_evidence_hash,
            "v3_readiness": content.v3_readiness,
            "summary": content.summary,
            "dissent": content.dissent,
            "uncertainty": content.uncertainty,
            "evidence_refs": content.evidence_refs,
            "blocking_reasons": content.blocking_reasons,
            "reason_code": content.reason_code,
            "model_profile": content.model_profile,
            "prompt_hash": content.prompt_hash,
            "provider_id": content.provider_id,
            "generated_at": content.generated_at,
        }

    def integrity_payload(self) -> dict[str, object]:
        """Return all content fields bound by opinion_hash."""
        return self._identity_payload(
            _DecisionOpinionContent(
                status=self.status,
                v3_artifact_id=self.v3_artifact_id,
                v3_evidence_hash=self.v3_evidence_hash,
                v3_readiness=self.v3_readiness,
                summary=self.summary,
                dissent=self.dissent,
                uncertainty=self.uncertainty,
                evidence_refs=self.evidence_refs,
                blocking_reasons=self.blocking_reasons,
                reason_code=self.reason_code,
                model_profile=self.model_profile,
                prompt_hash=self.prompt_hash,
                provider_id=self.provider_id,
                generated_at=self.generated_at,
            )
        )

    def record_payload(self) -> dict[str, object]:
        """Project the exact closed persistence record for application storage."""
        return {
            "schema_version": self.schema_version,
            "opinion_id": self.opinion_id,
            "shadow_outcome_id": self.shadow_outcome_id,
            "status": self.status.value,
            "v3_artifact_id": self.v3_artifact_id,
            "v3_evidence_hash": self.v3_evidence_hash,
            "v3_readiness": self.v3_readiness,
            "summary": self.summary,
            "dissent": self.dissent,
            "uncertainty": self.uncertainty,
            "evidence_refs": self.evidence_refs,
            "blocking_reasons": self.blocking_reasons,
            "reason_code": self.reason_code,
            "model_profile": self.model_profile,
            "prompt_hash": self.prompt_hash,
            "provider_id": self.provider_id,
            "generated_at": self.generated_at,
            "opinion_hash": self.opinion_hash,
        }

    def verify_integrity(self) -> bool:
        """Verify content, V3 binding, and both independent shadow identities."""
        return (
            canonical_sha256(self.integrity_payload()) == self.opinion_hash
            and self.opinion_id == f"decision-opinion-{self.opinion_hash}"
            and self.shadow_outcome_id == f"decision-shadow-{self.opinion_hash}"
        )


def _normalize_opinion_text(opinion: DecisionOpinion) -> None:
    for field_name in (
        "v3_artifact_id",
        "v3_readiness",
        "summary",
        "uncertainty",
        "model_profile",
        "provider_id",
    ):
        maximum = 8192 if field_name == "summary" else 4096
        object.__setattr__(
            opinion,
            field_name,
            normalized_text(
                getattr(opinion, field_name),
                field=field_name,
                maximum=maximum,
            ),
        )
    if opinion.v3_readiness not in {"ready", "review", "blocked"}:
        raise ValueError("v3_readiness is invalid")
    if opinion.dissent is not None:
        object.__setattr__(
            opinion,
            "dissent",
            normalized_text(opinion.dissent, field="dissent", maximum=4096),
        )


def _normalize_opinion_collections(opinion: DecisionOpinion) -> None:
    object.__setattr__(
        opinion,
        "evidence_refs",
        normalized_unique_tuple(opinion.evidence_refs, field="evidence_refs"),
    )
    if opinion.blocking_reasons:
        object.__setattr__(
            opinion,
            "blocking_reasons",
            normalized_unique_tuple(
                opinion.blocking_reasons,
                field="blocking_reasons",
            ),
        )


def _normalize_opinion_hashes(opinion: DecisionOpinion) -> None:
    for field_name in ("v3_evidence_hash", "prompt_hash", "opinion_hash"):
        object.__setattr__(
            opinion,
            field_name,
            sha256_hex(getattr(opinion, field_name), field=field_name),
        )
    object.__setattr__(
        opinion,
        "generated_at",
        utc_datetime(opinion.generated_at, field="generated_at"),
    )


def _validate_opinion_identities(opinion: DecisionOpinion) -> None:
    if opinion.opinion_id != f"decision-opinion-{opinion.opinion_hash}":
        raise ValueError("opinion_id does not match opinion_hash")
    if opinion.shadow_outcome_id != f"decision-shadow-{opinion.opinion_hash}":
        raise ValueError("shadow_outcome_id does not match opinion_hash")


def _validate_opinion_status(opinion: DecisionOpinion) -> None:
    if opinion.status is DecisionOpinionStatus.BLOCKED:
        if opinion.v3_readiness != "blocked" or not opinion.blocking_reasons:
            raise ValueError("blocked opinion requires blocked V3 reasons")
        if opinion.reason_code != "daily_decision_v3_blocked":
            raise ValueError("blocked opinion requires the fixed reason_code")
    elif (
        opinion.v3_readiness == "blocked"
        or opinion.blocking_reasons
        or opinion.reason_code is not None
    ):
        raise ValueError("completed opinion cannot carry blocking state")


class DecisionOpinionGenerator:
    """Use a bounded model only for ready/review V3 semantic explanation."""

    def __init__(
        self,
        *,
        model: AgentModelPort,
        model_profile: str,
        provider_id: str,
        max_output_tokens: int,
    ) -> None:
        if isinstance(max_output_tokens, bool) or max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        self._model = model
        self._model_profile = normalized_text(model_profile, field="model_profile")
        self._provider_id = normalized_text(provider_id, field="provider_id")
        self._max_output_tokens = max_output_tokens
        self._prompt_hash = canonical_sha256(_PROMPT)

    async def generate(
        self,
        request: DecisionOpinionGenerationRequest,
    ) -> DecisionOpinion:
        """Generate, validate, and seal one opinion without registering tools."""
        evidence = request.evidence
        if not _valid_briefing_evidence(evidence):
            raise DecisionOpinionGenerationError(
                "V3 evidence failed integrity validation",
                reason_code="decision_evidence_invalid",
            )
        artifact_ids = tuple(item.artifact_id for item in evidence.artifact_refs)
        if evidence.readiness == "blocked":
            return DecisionOpinion.create(
                _DecisionOpinionContent(
                    status=DecisionOpinionStatus.BLOCKED,
                    v3_artifact_id=artifact_ids[0],
                    v3_evidence_hash=evidence.payload.payload_hash,
                    v3_readiness=evidence.readiness,
                    summary=(
                        "DailyDecision V3 is blocked: "
                        + ", ".join(evidence.blocking_reasons)
                    ),
                    dissent=None,
                    uncertainty=(
                        "No actionable interpretation is produced while V3 is blocked."
                    ),
                    evidence_refs=artifact_ids,
                    blocking_reasons=evidence.blocking_reasons,
                    reason_code="daily_decision_v3_blocked",
                    model_profile=self._model_profile,
                    prompt_hash=self._prompt_hash,
                    provider_id=self._provider_id,
                    generated_at=request.generated_at,
                )
            )
        model_request = ModelRequest(
            run_id=f"decision-opinion-{evidence.payload.payload_hash[:24]}",
            agent_name="decision-briefing",
            instructions=_PROMPT,
            input_text=_model_input(evidence),
            max_turns=1,
            max_output_tokens=self._max_output_tokens,
            tools=(),
        )
        try:
            result = await self._model.run(model_request)
        except (TimeoutError, ModelProviderError) as exc:
            raise DecisionOpinionGenerationError(
                "DecisionOpinion provider failed",
                reason_code="model_provider_failed",
            ) from exc
        try:
            parsed = _parse_result(
                result,
                allowed_evidence_refs=frozenset(artifact_ids),
                max_output_tokens=self._max_output_tokens,
            )
            return DecisionOpinion.create(
                _DecisionOpinionContent(
                    status=DecisionOpinionStatus.COMPLETED,
                    v3_artifact_id=artifact_ids[0],
                    v3_evidence_hash=evidence.payload.payload_hash,
                    v3_readiness=evidence.readiness,
                    summary=parsed[0],
                    dissent=parsed[1],
                    uncertainty=parsed[2],
                    evidence_refs=parsed[3],
                    blocking_reasons=(),
                    reason_code=None,
                    model_profile=self._model_profile,
                    prompt_hash=self._prompt_hash,
                    provider_id=self._provider_id,
                    generated_at=request.generated_at,
                )
            )
        except (TypeError, ValueError) as exc:
            raise DecisionOpinionGenerationError(
                "DecisionOpinion model output is invalid",
                reason_code="model_output_invalid",
            ) from exc


def _valid_briefing_evidence(evidence: DecisionBriefingEvidenceReadModel) -> bool:
    if len(evidence.artifact_refs) != 1:
        return False
    artifact = evidence.artifact_refs[0]
    if (
        artifact.artifact_kind != "daily_decision_v3"
        or artifact.content_hash != evidence.payload.payload_hash
    ):
        return False
    payload_readiness = evidence.payload.value.get("readiness")
    payload_reasons = evidence.payload.value.get("blocking_reasons")
    if payload_readiness != evidence.readiness:
        return False
    if not isinstance(payload_reasons, tuple):
        return False
    if payload_reasons != evidence.blocking_reasons:
        return False
    return (evidence.readiness == "blocked") == bool(evidence.blocking_reasons)


def _model_input(evidence: DecisionBriefingEvidenceReadModel) -> str:
    payload = cast("Mapping[str, object]", evidence.payload.value)
    artifact_refs = tuple(
        {
            "artifact_id": item.artifact_id,
            "artifact_kind": item.artifact_kind,
            "content_hash": item.content_hash,
        }
        for item in evidence.artifact_refs
    )
    return canonical_bytes(
        {
            "v3_evidence_hash": evidence.payload.payload_hash,
            "readiness": evidence.readiness,
            "payload": payload,
            "artifact_refs": artifact_refs,
            "lineage": evidence.lineage,
        }
    ).decode()


def _parse_result(
    result: ModelResult,
    *,
    allowed_evidence_refs: frozenset[str],
    max_output_tokens: int,
) -> tuple[str, str | None, str, tuple[str, ...]]:
    if result.tool_calls or result.interruptions or result.continuation is not None:
        raise ValueError("DecisionOpinion model cannot call tools or interrupt")
    if result.usage.output_tokens > max_output_tokens:
        raise ValueError("DecisionOpinion output exceeded the host token limit")
    output = result.final_output
    if not isinstance(output, Mapping) or set(output) != {
        "summary",
        "dissent",
        "uncertainty",
        "evidence_refs",
    }:
        raise ValueError("DecisionOpinion output has an invalid field set")
    summary = output["summary"]
    dissent = output["dissent"]
    uncertainty = output["uncertainty"]
    raw_refs = output["evidence_refs"]
    if not isinstance(summary, str) or not isinstance(uncertainty, str):
        raise TypeError("DecisionOpinion text fields are invalid")
    if dissent is not None and not isinstance(dissent, str):
        raise TypeError("DecisionOpinion dissent must be text or null")
    if not isinstance(raw_refs, Sequence) or isinstance(raw_refs, str):
        raise TypeError("DecisionOpinion evidence_refs must be an array")
    refs = tuple(cast(Sequence[object], raw_refs))
    if not refs or not all(isinstance(item, str) for item in refs):
        raise TypeError("DecisionOpinion evidence_refs must contain text")
    evidence_refs = cast(tuple[str, ...], refs)
    if not set(evidence_refs).issubset(allowed_evidence_refs):
        raise ValueError("DecisionOpinion cited evidence outside V3")
    return summary, dissent, uncertainty, evidence_refs
