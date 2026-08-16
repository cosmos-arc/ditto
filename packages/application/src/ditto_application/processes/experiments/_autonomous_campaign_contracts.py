"""Immutable contracts and canonical codecs for autonomous Campaigns."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, TypedDict, Unpack, cast

from ditto_analysis.experiments.campaign import (
    EvaluationResult,
    ResearchCandidateSpec,
    SearchAxis,
)
from ditto_analysis.experiments.metric_schema import ResearchMetricId
from ditto_analysis.experiments.models import ContentHash, ExperimentId
from ditto_analysis.experiments.persistence import LeaseFence, canonical_payload
from ditto_analysis.experiments.search_ledger import StatisticalTrial

from ditto_application.exceptions import AppProcessError
from ditto_application.mutation_idempotency import canonical_request_hash

_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
NO_IMPROVEMENT_GENERATION_LIMIT = 2
_FORBIDDEN_CAMPAIGN_TOOL_TOKENS = frozenset(
    {"broker", "holdout", "order", "publish", "trade", "trading"}
)
TERMINAL_CAMPAIGN_STATUSES = frozenset(
    {
        "cancelled",
        "completed",
        "completed_with_failures",
        "failed",
    }
)


def campaign_error(
    message: str, *, code: str, reason: str, **details: object
) -> AppProcessError:
    return AppProcessError(
        message,
        details={"code": code, "reason": reason, **details},
    )


def require_text(value: object, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise campaign_error(
            f"{field} must be a non-empty canonical string",
            code="CAMPAIGN_INPUT_INVALID",
            reason="campaign_input_invalid",
            field=field,
        )
    return value


def require_content_hash(value: object, field: str) -> str:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        raise campaign_error(
            f"{field} must be a lowercase sha256 digest",
            code="CAMPAIGN_INPUT_INVALID",
            reason="campaign_input_invalid",
            field=field,
        )
    return value


def _positive(value: object, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise campaign_error(
            f"{field} must be a positive integer",
            code="CAMPAIGN_INPUT_INVALID",
            reason="campaign_input_invalid",
            field=field,
        )
    return value


def require_utc(value: object, field: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise campaign_error(
            f"{field} must be timezone-aware",
            code="CAMPAIGN_INPUT_INVALID",
            reason="campaign_input_invalid",
            field=field,
        )
    return value.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def campaign_epoch_us(value: datetime) -> int:
    normalized = require_utc(value, "occurred_at")
    seconds = int(normalized.timestamp())
    return seconds * 1_000_000 + normalized.microsecond


def datetime_from_epoch_us(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1_000_000, tz=UTC)


def campaign_event_id(kind: str, payload: Mapping[str, object]) -> str:
    return f"campaign-{kind}-{canonical_request_hash(payload)[:24]}"


def campaign_tool_is_forbidden(tool: str) -> bool:
    tokens = frozenset(re.split(r"[^a-z0-9]+", tool.lower()))
    return bool(tokens.intersection(_FORBIDDEN_CAMPAIGN_TOOL_TOKENS))


def encode_campaign_detail(value: Mapping[str, object]) -> bytes:
    return canonical_payload(dict(value)).json_bytes


def decode_campaign_detail(value: bytes) -> dict[str, object]:
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise campaign_error(
            "campaign persistence payload is malformed",
            code="CAMPAIGN_INTEGRITY_INVALID",
            reason="campaign_persistence_payload_invalid",
        )
    return cast("dict[str, object]", decoded)


class CampaignCoordinatorStatus(StrEnum):
    """Durable host-owned campaign state."""

    DRAFT = "draft"
    AUTHORIZED = "authorized"
    RUNNING = "running"
    PAUSED = "paused"
    PAUSED_BUDGET = "paused_budget"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    COMPLETED_WITH_FAILURES = "completed_with_failures"
    FAILED = "failed"


class _CampaignAuthorizationIssue(TypedDict):
    authorization_id: str
    authorization_hash: str
    authority_hash: str
    authorized_by: str
    authorized_at: datetime
    expires_at: datetime
    campaign_manifest_hash: str
    search_axis: str
    allowed_tools: Sequence[str]
    source_snapshot_id: str
    candidate_limit: int
    fold_run_limit: int
    generation_limit: int
    concurrent_sandbox_limit: int
    wall_time_limit_seconds: int
    temporary_storage_limit_bytes: int
    model_spend_limit_usd_micros: int


@dataclass(frozen=True, slots=True)
class CampaignAuthorizationProof:
    """Operator authorization binding one immutable manifest and finite budget."""

    authorization_id: str
    authorization_hash: str
    authority_hash: str
    authorized_by: str
    authorized_at: datetime
    expires_at: datetime
    campaign_manifest_hash: str
    search_axis: str
    allowed_tools: Sequence[str]
    source_snapshot_id: str
    candidate_limit: int
    fold_run_limit: int
    generation_limit: int
    concurrent_sandbox_limit: int
    wall_time_limit_seconds: int
    temporary_storage_limit_bytes: int
    model_spend_limit_usd_micros: int
    verification_hash: str

    def __post_init__(self) -> None:
        """Normalize authority fields without trusting the verification hash."""
        for field in (
            "authorization_id",
            "authorized_by",
            "search_axis",
            "source_snapshot_id",
        ):
            object.__setattr__(self, field, require_text(getattr(self, field), field))
        for field in (
            "authorization_hash",
            "authority_hash",
            "campaign_manifest_hash",
            "verification_hash",
        ):
            object.__setattr__(
                self, field, require_content_hash(getattr(self, field), field)
            )
        object.__setattr__(
            self, "authorized_at", require_utc(self.authorized_at, "authorized_at")
        )
        object.__setattr__(
            self, "expires_at", require_utc(self.expires_at, "expires_at")
        )
        if self.expires_at <= self.authorized_at:
            raise campaign_error(
                "expires_at must follow authorized_at",
                code="CAMPAIGN_AUTHORIZATION_INVALID",
                reason="campaign_authorization_integrity_invalid",
            )
        tools = tuple(
            sorted(require_text(item, "allowed_tools") for item in self.allowed_tools)
        )
        if not tools or len(tools) != len(set(tools)):
            raise campaign_error(
                "allowed_tools must contain unique tool names",
                code="CAMPAIGN_AUTHORIZATION_INVALID",
                reason="campaign_authorization_integrity_invalid",
            )
        object.__setattr__(self, "allowed_tools", tools)
        for field in (
            "candidate_limit",
            "fold_run_limit",
            "generation_limit",
            "concurrent_sandbox_limit",
            "wall_time_limit_seconds",
            "temporary_storage_limit_bytes",
            "model_spend_limit_usd_micros",
        ):
            object.__setattr__(self, field, _positive(getattr(self, field), field))

    @classmethod
    def issue(
        cls,
        **values: Unpack[_CampaignAuthorizationIssue],
    ) -> CampaignAuthorizationProof:
        """Issue a self-verifying proof over every authority-relevant field."""
        proof = cls(
            **values,
            verification_hash="0" * 64,
        )
        return replace(
            proof,
            verification_hash=canonical_request_hash(proof.canonical_payload()),
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return the proof body covered by verification_hash."""
        return {
            "schema_version": 1,
            "kind": "ditto_campaign_authorization_proof",
            "authorization_id": self.authorization_id,
            "authorization_hash": self.authorization_hash,
            "authority_hash": self.authority_hash,
            "authorized_by": self.authorized_by,
            "authorized_at": _utc_text(self.authorized_at),
            "expires_at": _utc_text(self.expires_at),
            "campaign_manifest_hash": self.campaign_manifest_hash,
            "search_axis": self.search_axis,
            "allowed_tools": list(self.allowed_tools),
            "source_snapshot_id": self.source_snapshot_id,
            "candidate_limit": self.candidate_limit,
            "fold_run_limit": self.fold_run_limit,
            "generation_limit": self.generation_limit,
            "concurrent_sandbox_limit": self.concurrent_sandbox_limit,
            "wall_time_limit_seconds": self.wall_time_limit_seconds,
            "temporary_storage_limit_bytes": self.temporary_storage_limit_bytes,
            "model_spend_limit_usd_micros": self.model_spend_limit_usd_micros,
        }

    def verify_integrity(self) -> bool:
        """Verify the complete authorization body."""
        return (
            canonical_request_hash(self.canonical_payload()) == self.verification_hash
        )


@dataclass(frozen=True, slots=True)
class CampaignTrialScheduleRequest:
    """Exact logical trial request passed to the host scheduler."""

    campaign_id: ExperimentId
    candidate: ResearchCandidateSpec
    trial: StatisticalTrial
    fold_run_budget_remaining: int


@dataclass(frozen=True, slots=True)
class CampaignTrialRetryRequest:
    """Attempt-only retry request that preserves the statistical identity."""

    campaign_id: ExperimentId
    trial: StatisticalTrial
    retry_id: str
    next_attempt_ordinal: int


@dataclass(frozen=True, slots=True)
class CampaignScheduledTrial:
    """Lease-fenced scheduler acknowledgement with reserved fold work."""

    lease: LeaseFence
    fold_run_count: int

    def __post_init__(self) -> None:
        """Require a typed live lease and positive fold reservation."""
        if type(self.lease) is not LeaseFence:
            raise campaign_error(
                "lease must be LeaseFence",
                code="CAMPAIGN_SCHEDULER_INVALID",
                reason="campaign_scheduler_response_invalid",
            )
        _positive(self.fold_run_count, "fold_run_count")


class CampaignTrialSchedulerPort(Protocol):
    """Host scheduler/lease boundary reused by autonomous Campaigns."""

    def schedule_trial(
        self,
        request: CampaignTrialScheduleRequest,
        *,
        now_epoch_us: int,
    ) -> CampaignScheduledTrial:
        """Reserve one immutable statistical trial under a live lease."""
        ...

    def schedule_retry(
        self,
        request: CampaignTrialRetryRequest,
        *,
        now_epoch_us: int,
    ) -> LeaseFence:
        """Reserve one attempt-only retry under a live lease."""
        ...

    def cancel_campaign(
        self,
        campaign_id: ExperimentId,
        *,
        now_epoch_us: int,
    ) -> None:
        """Cancel all scheduler work owned by a Campaign."""
        ...


@dataclass(frozen=True, slots=True)
class CampaignEvaluationObservation:
    """Trusted-host primary metric observation for one immutable result."""

    result: EvaluationResult
    primary_metric_value: float
    generation_complete: bool

    def __post_init__(self) -> None:
        """Reject model-like, non-finite, or partial observations."""
        if type(self.result) is not EvaluationResult:
            raise campaign_error(
                "result must be EvaluationResult",
                code="CAMPAIGN_EVALUATION_INVALID",
                reason="campaign_evaluation_invalid",
            )
        if type(self.primary_metric_value) not in {int, float} or not math.isfinite(
            self.primary_metric_value
        ):
            raise campaign_error(
                "primary_metric_value must be finite",
                code="CAMPAIGN_EVALUATION_INVALID",
                reason="campaign_evaluation_invalid",
            )
        object.__setattr__(
            self, "primary_metric_value", float(self.primary_metric_value)
        )
        if type(self.generation_complete) is not bool:
            raise campaign_error(
                "generation_complete must be bool",
                code="CAMPAIGN_EVALUATION_INVALID",
                reason="campaign_evaluation_invalid",
            )


@dataclass(frozen=True, slots=True)
class CampaignCoordinatorState:
    """Reconstructed campaign projection; the event stream remains authoritative."""

    campaign_id: ExperimentId
    status: CampaignCoordinatorStatus
    authorization_hash: str | None
    best_primary_metric_value: float | None
    no_improvement_generations: int
    statistical_trial_count: int
    operational_attempt_count: int
    revision: int


@dataclass(frozen=True, slots=True)
class CampaignManifestView:
    primary_metric_id: ResearchMetricId
    validation_protocol_hash: ContentHash
    snapshot_id: str
    search_axis: SearchAxis
    lineage_root: ContentHash
    candidate_limit: int
    fold_run_limit: int
    generation_limit: int
    concurrent_sandbox_limit: int
    wall_time_limit_seconds: int
    temporary_storage_limit_bytes: int
    model_spend_limit_usd_micros: int
    allowed_tools: tuple[str, ...]
