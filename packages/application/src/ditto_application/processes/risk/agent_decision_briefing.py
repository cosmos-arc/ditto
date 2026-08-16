"""Post-V3 shadow orchestration for governed DecisionOpinion generation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol, cast

from ditto_application.exceptions import AppProcessError, AppQueryError
from ditto_application.queries.decision_briefing_contracts import (
    DecisionBriefingEvidenceQueryPort,
    DecisionBriefingEvidenceReadModel,
)
from ditto_application.queries.evidence_contracts import EvidenceTemporalContext

__all__ = [
    "DecisionBriefingInput",
    "DecisionBriefingOutcome",
    "DecisionBriefingProcess",
    "DecisionOpinionGenerationError",
    "DecisionOpinionGenerationRequest",
    "DecisionOpinionGeneratorPort",
    "DecisionOpinionRecord",
    "DecisionOpinionView",
    "DecisionOpinionWriterPort",
]

_SHA256_LENGTH = 64


class DecisionOpinionGenerationError(AppProcessError):
    """Typed failure from the replaceable shadow opinion generator."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message, details={"reason_code": reason_code})


class _DecisionOpinionContractError(AppProcessError):
    """Typed failure while validating the cross-package shadow record."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            details={"reason_code": "decision_opinion_evidence_conflict"},
        )


@dataclass(frozen=True, slots=True)
class DecisionBriefingInput:
    """Exact V3 identity and host-owned temporal inputs for one shadow run."""

    strategy_id: str
    strategy_version: str
    trade_date: str
    account_id: str
    sleeve_id: str
    context: EvidenceTemporalContext
    generated_at: datetime

    def __post_init__(self) -> None:
        """Validate exact identities and normalize the host-owned UTC time."""
        for field_name in (
            "strategy_id",
            "strategy_version",
            "trade_date",
            "account_id",
            "sleeve_id",
        ):
            value = getattr(self, field_name)
            if not value or value != value.strip():
                raise AppProcessError(
                    f"{field_name} must be canonical text",
                    details={"reason_code": "decision_briefing_input_invalid"},
                )
        if (
            self.generated_at.tzinfo is None
            or self.generated_at.utcoffset() != timedelta(0)
        ):
            raise AppProcessError(
                "generated_at must be UTC",
                details={"reason_code": "decision_briefing_input_invalid"},
            )
        object.__setattr__(self, "generated_at", self.generated_at.astimezone(UTC))


@dataclass(frozen=True, slots=True)
class DecisionOpinionGenerationRequest:
    """Authenticated V3 evidence plus host time supplied to the Agent generator."""

    evidence: DecisionBriefingEvidenceReadModel
    generated_at: datetime


class DecisionOpinionView(Protocol):
    """Read-only structural view returned across the application/Agent boundary."""

    def record_payload(self) -> Mapping[str, object]:
        """Return the exact closed persistence payload."""
        ...

    def verify_integrity(self) -> bool:
        """Verify the Agent-owned content identity."""
        ...


class DecisionOpinionGeneratorPort(Protocol):
    """Generate one read-only opinion from exact immutable V3 evidence."""

    async def generate(
        self,
        request: DecisionOpinionGenerationRequest,
    ) -> DecisionOpinionView:
        """Return one host-verifiable opinion or a typed generation error."""
        ...


@dataclass(frozen=True, slots=True)
class DecisionOpinionRecord:
    """Application persistence command for the isolated shadow namespace."""

    schema_version: int
    opinion_id: str
    shadow_outcome_id: str
    status: str
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


class DecisionOpinionWriterPort(Protocol):
    """Append opinions only to an isolated, idempotent shadow store."""

    def append_opinion(self, record: DecisionOpinionRecord) -> bool:
        """Append once; return False only for an exact replay."""
        ...


@dataclass(frozen=True, slots=True)
class DecisionBriefingOutcome:
    """Persisted shadow identity or a fail-closed refusal."""

    status: Literal["persisted", "refused"]
    reason_code: str | None
    opinion_id: str | None
    shadow_outcome_id: str | None
    replayed: bool


class DecisionBriefingProcess:
    """Read V3, generate an opinion, validate it, and append only shadow state."""

    def __init__(
        self,
        *,
        evidence_reader: DecisionBriefingEvidenceQueryPort,
        generator: DecisionOpinionGeneratorPort,
        writer: DecisionOpinionWriterPort,
    ) -> None:
        self._evidence_reader = evidence_reader
        self._generator = generator
        self._writer = writer

    async def execute(self, input_: DecisionBriefingInput) -> DecisionBriefingOutcome:
        """Run after V3 persistence without any portfolio/risk/execution writer."""
        try:
            evidence = self._evidence_reader.get_briefing_evidence(
                strategy_id=input_.strategy_id,
                strategy_version=input_.strategy_version,
                trade_date=input_.trade_date,
                account_id=input_.account_id,
                sleeve_id=input_.sleeve_id,
                context=input_.context,
            )
        except AppQueryError as exc:
            return _refused(
                str(exc.details.get("code", "decision_evidence_unavailable"))
            )
        try:
            opinion = await self._generator.generate(
                DecisionOpinionGenerationRequest(
                    evidence=evidence,
                    generated_at=input_.generated_at,
                )
            )
        except DecisionOpinionGenerationError as exc:
            return _refused(
                str(exc.details.get("reason_code", "model_provider_failed"))
            )
        try:
            record = _record(opinion)
        except (AppProcessError, TypeError, ValueError):
            return _refused("decision_opinion_evidence_conflict")
        if not _matches_evidence(
            record,
            evidence,
            generated_at=input_.generated_at,
            integrity_verified=opinion.verify_integrity(),
        ):
            return _refused("decision_opinion_evidence_conflict")
        appended = self._writer.append_opinion(record)
        return DecisionBriefingOutcome(
            status="persisted",
            reason_code=None,
            opinion_id=record.opinion_id,
            shadow_outcome_id=record.shadow_outcome_id,
            replayed=not appended,
        )


def _is_hash(value: str) -> bool:
    return len(value) == _SHA256_LENGTH and all(
        character in "0123456789abcdef" for character in value
    )


def _matches_evidence(
    opinion: DecisionOpinionRecord,
    evidence: DecisionBriefingEvidenceReadModel,
    *,
    generated_at: datetime,
    integrity_verified: bool,
) -> bool:
    artifacts = {item.artifact_id: item.content_hash for item in evidence.artifact_refs}
    expected_status = "blocked" if evidence.readiness == "blocked" else "completed"
    expected_reason = (
        "daily_decision_v3_blocked" if evidence.readiness == "blocked" else None
    )
    return (
        opinion.schema_version == 1
        and integrity_verified
        and _is_hash(opinion.opinion_hash)
        and _is_hash(opinion.prompt_hash)
        and opinion.opinion_id == f"decision-opinion-{opinion.opinion_hash}"
        and opinion.shadow_outcome_id == f"decision-shadow-{opinion.opinion_hash}"
        and opinion.status == expected_status
        and opinion.v3_artifact_id in artifacts
        and artifacts.get(opinion.v3_artifact_id) == evidence.payload.payload_hash
        and opinion.v3_evidence_hash == evidence.payload.payload_hash
        and opinion.v3_readiness == evidence.readiness
        and bool(opinion.evidence_refs)
        and set(opinion.evidence_refs).issubset(artifacts)
        and opinion.blocking_reasons == evidence.blocking_reasons
        and opinion.reason_code == expected_reason
        and opinion.generated_at == generated_at
    )


def _record(opinion: DecisionOpinionView) -> DecisionOpinionRecord:
    payload = opinion.record_payload()
    expected_fields = frozenset(DecisionOpinionRecord.__dataclass_fields__)
    if frozenset(payload) != expected_fields:
        raise _DecisionOpinionContractError(
            "DecisionOpinion record has an invalid field set"
        )
    required_text = (
        "opinion_id",
        "shadow_outcome_id",
        "status",
        "v3_artifact_id",
        "v3_evidence_hash",
        "v3_readiness",
        "summary",
        "uncertainty",
        "model_profile",
        "prompt_hash",
        "provider_id",
        "opinion_hash",
    )
    if any(not isinstance(payload[field], str) for field in required_text):
        raise _DecisionOpinionContractError(
            "DecisionOpinion record text fields are invalid"
        )
    dissent = payload["dissent"]
    reason_code = payload["reason_code"]
    if dissent is not None and not isinstance(dissent, str):
        raise _DecisionOpinionContractError(
            "DecisionOpinion dissent must be text or null"
        )
    if reason_code is not None and not isinstance(reason_code, str):
        raise _DecisionOpinionContractError(
            "DecisionOpinion reason_code must be text or null"
        )
    evidence_refs = _text_tuple(payload["evidence_refs"], field="evidence_refs")
    blocking_reasons = _text_tuple(
        payload["blocking_reasons"], field="blocking_reasons", allow_empty=True
    )
    schema_version = payload["schema_version"]
    generated_at = payload["generated_at"]
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise _DecisionOpinionContractError(
            "DecisionOpinion schema_version must be an integer"
        )
    if not isinstance(generated_at, datetime):
        raise _DecisionOpinionContractError(
            "DecisionOpinion generated_at must be a datetime"
        )
    return DecisionOpinionRecord(
        schema_version=schema_version,
        opinion_id=cast(str, payload["opinion_id"]),
        shadow_outcome_id=cast(str, payload["shadow_outcome_id"]),
        status=cast(str, payload["status"]),
        v3_artifact_id=cast(str, payload["v3_artifact_id"]),
        v3_evidence_hash=cast(str, payload["v3_evidence_hash"]),
        v3_readiness=cast(str, payload["v3_readiness"]),
        summary=cast(str, payload["summary"]),
        dissent=dissent,
        uncertainty=cast(str, payload["uncertainty"]),
        evidence_refs=evidence_refs,
        blocking_reasons=blocking_reasons,
        reason_code=reason_code,
        model_profile=cast(str, payload["model_profile"]),
        prompt_hash=cast(str, payload["prompt_hash"]),
        provider_id=cast(str, payload["provider_id"]),
        generated_at=generated_at,
        opinion_hash=cast(str, payload["opinion_hash"]),
    )


def _text_tuple(
    value: object, *, field: str, allow_empty: bool = False
) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise _DecisionOpinionContractError(f"DecisionOpinion {field} must be an array")
    items = tuple(cast(Sequence[object], value))
    if (not allow_empty and not items) or not all(
        isinstance(item, str) for item in items
    ):
        raise _DecisionOpinionContractError(
            f"DecisionOpinion {field} must contain text"
        )
    return cast(tuple[str, ...], items)


def _refused(reason_code: str) -> DecisionBriefingOutcome:
    return DecisionBriefingOutcome(
        status="refused",
        reason_code=reason_code,
        opinion_id=None,
        shadow_outcome_id=None,
        replayed=False,
    )
