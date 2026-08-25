"""Typed persistence contracts for governed research campaigns."""

# Protocol signatures are the documentation surface for consumer-owned verbs.
# ruff: noqa: D102

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.campaign import (
    ResearchCampaignManifest,
    ResearchCandidateSpec,
    SearchAxis,
)
from ditto_analysis.experiments.generated_code import (
    ResearchCodeArtifact,
    SandboxExecutionManifest,
)
from ditto_analysis.experiments.models import AttemptId, ContentHash, ExperimentId
from ditto_analysis.experiments.research_memory import (
    KnowledgeItem,
    KnowledgeStatusEvent,
    ResearchFeedback,
)
from ditto_analysis.experiments.search_ledger import (
    OperationalAttempt,
    SearchLedger,
    StatisticalTrial,
)

__all__ = [
    "CampaignEventRecord",
    "CampaignManifestRecord",
    "CampaignReaderProtocol",
    "CampaignWriterProtocol",
    "CandidateLineageRecord",
    "ResearchFeedbackRecord",
    "SandboxExecutionRecord",
]


def _error(message: str, reason_code: str, **details: object) -> ExperimentSpecError:
    return ExperimentSpecError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _identity(value: object, field: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise _error(
            f"{field} must be a non-empty unpadded string",
            "invalid_campaign_persistence_record",
            field=field,
        )
    return value


def _epoch_us(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise _error(
            f"{field} must be a non-negative epoch-us integer",
            "invalid_campaign_persistence_record",
            field=field,
        )
    return value


def _json_bytes(value: object, field: str) -> tuple[bytes, dict[str, object]]:
    if type(value) is not bytes:
        raise _error(
            f"{field} must be canonical JSON bytes",
            "invalid_campaign_persistence_record",
            field=field,
        )
    try:
        decoded = json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error(
            f"{field} must contain JSON",
            "invalid_campaign_persistence_record",
            field=field,
        ) from exc
    if not isinstance(decoded, dict):
        raise _error(
            f"{field} must contain a JSON object",
            "invalid_campaign_persistence_record",
            field=field,
        )
    typed = cast("dict[str, object]", decoded)
    canonical = json.dumps(
        typed,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if value != canonical:
        raise _error(
            f"{field} must use canonical JSON encoding",
            "invalid_campaign_persistence_record",
            field=field,
        )
    return value, typed


@dataclass(frozen=True, slots=True)
class CampaignManifestRecord:
    """Lossless immutable campaign manifest payload and storage metadata."""

    campaign_id: ExperimentId
    manifest_hash: ContentHash
    manifest_payload: bytes
    search_axis: SearchAxis
    lineage_root: ContentHash
    created_at_epoch_us: int

    def __post_init__(self) -> None:
        """Require the relational identity to agree with canonical bytes."""
        for value, expected, field in (
            (self.campaign_id, ExperimentId, "campaign_id"),
            (self.manifest_hash, ContentHash, "manifest_hash"),
            (self.lineage_root, ContentHash, "lineage_root"),
        ):
            if type(value) is not expected:
                raise _error(
                    f"{field} must be {expected.__name__}",
                    "invalid_campaign_persistence_record",
                    field=field,
                )
        payload, root = _json_bytes(self.manifest_payload, "manifest_payload")
        if ContentHash(hashlib.sha256(payload).hexdigest()) != self.manifest_hash:
            raise _error(
                "manifest_hash does not match manifest_payload",
                "campaign_manifest_hash_mismatch",
            )
        if type(self.search_axis) is not SearchAxis:
            raise _error(
                "search_axis must be SearchAxis",
                "invalid_campaign_persistence_record",
                field="search_axis",
            )
        expected_identity = (
            root.get("schema_id"),
            root.get("schema_version"),
            root.get("campaign_id"),
            root.get("search_axis"),
            root.get("lineage_root"),
        )
        if expected_identity != (
            "r5-research-campaign-manifest",
            1,
            str(self.campaign_id),
            self.search_axis.value,
            str(self.lineage_root),
        ):
            raise _error(
                "manifest payload disagrees with its relational identity",
                "campaign_manifest_identity_mismatch",
            )
        _epoch_us(self.created_at_epoch_us, "created_at_epoch_us")

    @classmethod
    def from_manifest(
        cls,
        manifest: ResearchCampaignManifest,
        *,
        created_at_epoch_us: int,
    ) -> CampaignManifestRecord:
        """Create a persistence record from the canonical domain aggregate."""
        if type(manifest) is not ResearchCampaignManifest:
            raise _error(
                "manifest must be ResearchCampaignManifest",
                "invalid_campaign_persistence_record",
                field="manifest",
            )
        return cls(
            campaign_id=manifest.campaign_id,
            manifest_hash=manifest.manifest_hash,
            manifest_payload=manifest.canonical_payload.json_bytes,
            search_axis=manifest.search_axis,
            lineage_root=manifest.lineage_root,
            created_at_epoch_us=created_at_epoch_us,
        )


@dataclass(frozen=True, slots=True)
class CampaignEventRecord:
    """One append-only campaign lifecycle event."""

    event_id: str
    campaign_id: ExperimentId
    ordinal: int
    event_type: str
    previous_status: str | None
    status: str
    detail_payload: bytes
    occurred_at_epoch_us: int

    def __post_init__(self) -> None:
        """Reject malformed lifecycle identities, payloads, and timestamps."""
        _identity(self.event_id, "event_id")
        if type(self.campaign_id) is not ExperimentId:
            raise _error(
                "campaign_id must be ExperimentId",
                "invalid_campaign_persistence_record",
                field="campaign_id",
            )
        _epoch_us(self.ordinal, "ordinal")
        _identity(self.event_type, "event_type")
        if self.previous_status is not None:
            _identity(self.previous_status, "previous_status")
        _identity(self.status, "status")
        _json_bytes(self.detail_payload, "detail_payload")
        _epoch_us(self.occurred_at_epoch_us, "occurred_at_epoch_us")


@dataclass(frozen=True, slots=True)
class CandidateLineageRecord:
    """One immutable campaign candidate and its generation lineage."""

    campaign_id: ExperimentId
    candidate: ResearchCandidateSpec
    generation: int
    created_at_epoch_us: int

    def __post_init__(self) -> None:
        """Require a typed candidate and non-negative generation metadata."""
        if type(self.campaign_id) is not ExperimentId:
            raise _error(
                "campaign_id must be ExperimentId",
                "invalid_campaign_persistence_record",
                field="campaign_id",
            )
        if type(self.candidate) is not ResearchCandidateSpec:
            raise _error(
                "candidate must be ResearchCandidateSpec",
                "invalid_campaign_persistence_record",
                field="candidate",
            )
        _epoch_us(self.generation, "generation")
        _epoch_us(self.created_at_epoch_us, "created_at_epoch_us")


@dataclass(frozen=True, slots=True)
class SandboxExecutionRecord:
    """Campaign/attempt association for one sandbox attestation."""

    campaign_id: ExperimentId
    attempt_id: AttemptId | None
    manifest: SandboxExecutionManifest
    created_at_epoch_us: int

    def __post_init__(self) -> None:
        """Require typed campaign, attempt, manifest, and timestamp values."""
        if type(self.campaign_id) is not ExperimentId:
            raise _error(
                "campaign_id must be ExperimentId",
                "invalid_campaign_persistence_record",
                field="campaign_id",
            )
        if self.attempt_id is not None and type(self.attempt_id) is not AttemptId:
            raise _error(
                "attempt_id must be AttemptId when present",
                "invalid_campaign_persistence_record",
                field="attempt_id",
            )
        if type(self.manifest) is not SandboxExecutionManifest:
            raise _error(
                "manifest must be SandboxExecutionManifest",
                "invalid_campaign_persistence_record",
                field="manifest",
            )
        _epoch_us(self.created_at_epoch_us, "created_at_epoch_us")


@dataclass(frozen=True, slots=True)
class ResearchFeedbackRecord:
    """Stable persistence identity around one PIT-safe feedback value."""

    feedback_id: str
    feedback: ResearchFeedback

    def __post_init__(self) -> None:
        """Require a stable record identity around typed research feedback."""
        _identity(self.feedback_id, "feedback_id")
        if type(self.feedback) is not ResearchFeedback:
            raise _error(
                "feedback must be ResearchFeedback",
                "invalid_campaign_persistence_record",
                field="feedback",
            )


class CampaignReaderProtocol(Protocol):
    """Read governed research state through typed, PIT-aware values."""

    def get_campaign(
        self, campaign_id: ExperimentId
    ) -> CampaignManifestRecord | None: ...

    def list_campaigns(self) -> tuple[CampaignManifestRecord, ...]: ...

    def list_campaign_events(
        self, campaign_id: ExperimentId
    ) -> tuple[CampaignEventRecord, ...]: ...

    def list_candidates(
        self, campaign_id: ExperimentId
    ) -> tuple[CandidateLineageRecord, ...]: ...

    def get_search_ledger(self, campaign_id: ExperimentId) -> SearchLedger | None: ...

    def get_code_artifact(
        self, artifact_hash: ContentHash
    ) -> ResearchCodeArtifact | None: ...

    def get_sandbox_execution(
        self, attestation_hash: ContentHash
    ) -> SandboxExecutionRecord | None: ...

    def list_feedback_visible_at(
        self, campaign_id: ExperimentId, knowledge_cutoff: datetime
    ) -> tuple[ResearchFeedbackRecord, ...]: ...

    def list_knowledge_visible_at(
        self, campaign_id: ExperimentId, knowledge_cutoff: datetime
    ) -> tuple[KnowledgeItem, ...]: ...

    def get_knowledge_visible_at(
        self,
        knowledge_id: str,
        knowledge_cutoff: datetime,
    ) -> KnowledgeItem | None: ...

    def list_knowledge_visible_for_scope(
        self,
        campaign_id: ExperimentId,
        strategy_family_ref: str | None,
        knowledge_cutoff: datetime,
    ) -> tuple[KnowledgeItem, ...]: ...

    def list_knowledge_status_events(
        self, knowledge_id: str
    ) -> tuple[KnowledgeStatusEvent, ...]: ...


class CampaignWriterProtocol(Protocol):
    """Write immutable campaign facts and append-only event streams."""

    def add_campaign(self, record: CampaignManifestRecord) -> None: ...

    def append_campaign_event(self, record: CampaignEventRecord) -> None: ...

    def add_candidate(self, record: CandidateLineageRecord) -> None: ...

    def add_statistical_trial(
        self,
        campaign_id: ExperimentId,
        trial: StatisticalTrial,
        *,
        created_at_epoch_us: int,
    ) -> None: ...

    def add_operational_attempt(
        self,
        campaign_id: ExperimentId,
        attempt: OperationalAttempt,
        *,
        created_at_epoch_us: int,
    ) -> None: ...

    def add_code_artifact(
        self, artifact: ResearchCodeArtifact, *, created_at_epoch_us: int
    ) -> None: ...

    def add_sandbox_execution(self, record: SandboxExecutionRecord) -> None: ...

    def add_feedback(self, record: ResearchFeedbackRecord) -> None: ...

    def add_knowledge(self, item: KnowledgeItem) -> None: ...

    def append_knowledge_status_event(self, event: KnowledgeStatusEvent) -> None: ...
