"""Exact-identity, shadow-only DecisionOpinion read projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.decision_briefing_contracts import (
    DecisionBriefingEvidenceQueryPort,
)
from ditto_application.queries.evidence_contracts import EvidenceTemporalContext

DecisionOpinionReadStatus = Literal["completed", "blocked", "unavailable"]


def _text(value: str, *, field: str) -> str:
    if not value or value != value.strip():
        raise AppQueryError(f"{field} must be canonical text")
    return value


@dataclass(frozen=True, slots=True)
class DecisionOpinionIdentity:
    """Exact Daily Decision V3 and PIT identity requested by the caller."""

    strategy_id: str
    strategy_version: str
    trade_date: str
    account_id: str
    sleeve_id: str
    v3_artifact_id: str
    context: EvidenceTemporalContext

    def __post_init__(self) -> None:
        """Validate canonical fields and their deterministic artifact binding."""
        for field_name in (
            "strategy_id",
            "strategy_version",
            "trade_date",
            "account_id",
            "sleeve_id",
            "v3_artifact_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field=field_name),
            )
        expected_artifact = (
            "daily-decision-v3:"
            f"{self.strategy_id}:{self.trade_date}:{self.account_id}:{self.sleeve_id}"
        )
        if self.v3_artifact_id != expected_artifact:
            raise AppQueryError("v3_artifact_id does not match the decision identity")


class DecisionOpinionStoredView(Protocol):
    """Agent-independent structural view of one authenticated shadow record."""

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
    generated_at: datetime


class DecisionOpinionReaderPort(Protocol):
    """Read the newest authenticated record for one exact V3 artifact."""

    def get_latest_by_v3_artifact_id(
        self, v3_artifact_id: str
    ) -> DecisionOpinionStoredView | None:
        """Return newest-first deterministic shadow content, if present."""
        ...


@dataclass(frozen=True, slots=True)
class DecisionOpinionReadModel:
    """Fail-closed public projection that cannot mutate V3 state."""

    identity: DecisionOpinionIdentity
    status: DecisionOpinionReadStatus
    generated_at: datetime | None
    model_profile: str | None
    summary: str | None
    disagreements: tuple[str, ...]
    uncertainties: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    provenance_match: bool
    shadow_outcome_identity: str | None
    unavailable_reason: str | None


def _unavailable(
    identity: DecisionOpinionIdentity,
    reason: str,
) -> DecisionOpinionReadModel:
    return DecisionOpinionReadModel(
        identity=identity,
        status="unavailable",
        generated_at=None,
        model_profile=None,
        summary=None,
        disagreements=(),
        uncertainties=(),
        evidence_refs=(),
        provenance_match=False,
        shadow_outcome_identity=None,
        unavailable_reason=reason,
    )


class DecisionOpinionQueryService:
    """Join one opinion only to its exact current V3 evidence and provenance."""

    def __init__(
        self,
        *,
        evidence_reader: DecisionBriefingEvidenceQueryPort,
        opinion_reader: DecisionOpinionReaderPort,
    ) -> None:
        self._evidence_reader = evidence_reader
        self._opinion_reader = opinion_reader

    def get_opinion(
        self,
        identity: DecisionOpinionIdentity,
    ) -> DecisionOpinionReadModel:
        """Return readable content only when every V3/PIT binding still matches."""
        try:
            evidence = self._evidence_reader.get_briefing_evidence(
                strategy_id=identity.strategy_id,
                strategy_version=identity.strategy_version,
                trade_date=identity.trade_date,
                account_id=identity.account_id,
                sleeve_id=identity.sleeve_id,
                context=identity.context,
            )
        except AppQueryError:
            return _unavailable(identity, "decision_opinion_evidence_unavailable")
        artifacts = {
            item.artifact_id: item.content_hash for item in evidence.artifact_refs
        }
        if (
            evidence.strategy_id != identity.strategy_id
            or evidence.strategy_version != identity.strategy_version
            or evidence.trade_date != identity.trade_date
            or evidence.account_id != identity.account_id
            or evidence.sleeve_id != identity.sleeve_id
            or evidence.temporal_context != identity.context
            or set(artifacts) != {identity.v3_artifact_id}
        ):
            return _unavailable(
                identity,
                "decision_opinion_provenance_mismatch",
            )
        try:
            opinion = self._opinion_reader.get_latest_by_v3_artifact_id(
                identity.v3_artifact_id
            )
        except AppQueryError:
            return _unavailable(identity, "decision_opinion_store_unavailable")
        if opinion is None:
            return _unavailable(identity, "decision_opinion_unavailable")
        expected_status = "blocked" if evidence.readiness == "blocked" else "completed"
        expected_reason = (
            "daily_decision_v3_blocked" if evidence.readiness == "blocked" else None
        )
        if (
            opinion.v3_artifact_id != identity.v3_artifact_id
            or opinion.v3_evidence_hash != artifacts[identity.v3_artifact_id]
            or opinion.v3_readiness != evidence.readiness
            or opinion.status != expected_status
            or opinion.blocking_reasons != evidence.blocking_reasons
            or opinion.reason_code != expected_reason
            or not opinion.evidence_refs
            or not set(opinion.evidence_refs).issubset(artifacts)
            or opinion.generated_at < identity.context.decision_time
        ):
            return _unavailable(
                identity,
                "decision_opinion_provenance_mismatch",
            )
        return DecisionOpinionReadModel(
            identity=identity,
            status=expected_status,
            generated_at=opinion.generated_at,
            model_profile=opinion.model_profile,
            summary=opinion.summary,
            disagreements=(() if opinion.dissent is None else (opinion.dissent,)),
            uncertainties=(opinion.uncertainty,),
            evidence_refs=opinion.evidence_refs,
            provenance_match=True,
            shadow_outcome_identity=opinion.shadow_outcome_id,
            unavailable_reason=None,
        )


class UnavailableDecisionOpinionQuery:
    """Stable disabled/degraded projection used without a configured shadow store."""

    def __init__(self, reason: str = "decision_opinion_feature_unavailable") -> None:
        self._reason = _text(reason, field="reason")

    def get_opinion(
        self,
        identity: DecisionOpinionIdentity,
    ) -> DecisionOpinionReadModel:
        """Keep Daily Decision independent while reporting shadow unavailability."""
        return _unavailable(identity, self._reason)


class DecisionOpinionQueryPort(Protocol):
    """Transport-neutral public DecisionOpinion query surface."""

    def get_opinion(
        self,
        identity: DecisionOpinionIdentity,
    ) -> DecisionOpinionReadModel:
        """Return a completed, blocked, or explicitly unavailable shadow view."""
        ...


__all__ = [
    "DecisionOpinionIdentity",
    "DecisionOpinionQueryPort",
    "DecisionOpinionQueryService",
    "DecisionOpinionReadModel",
    "DecisionOpinionReadStatus",
    "DecisionOpinionReaderPort",
    "DecisionOpinionStoredView",
    "UnavailableDecisionOpinionQuery",
]
