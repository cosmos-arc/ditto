"""Pure transport-neutral contracts for governed Campaign public surfaces."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Literal, Protocol, cast

import orjson

from ditto_application.exceptions import AppCommandError
from ditto_application.mutation_idempotency import canonical_request_hash

_SHA256_HEX_LENGTH = 64


class CampaignRuntimeError(RuntimeError):
    """Base failure exposed to HTTP and CLI adapters."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class CampaignRuntimeUnavailable(CampaignRuntimeError):
    """Campaign feature or its durable providers are unavailable."""

    def __init__(self, reason_code: str) -> None:
        super().__init__("Campaign runtime is unavailable", reason_code=reason_code)


class CampaignResourceNotFound(CampaignRuntimeError):
    """Requested Campaign identity is absent."""


class CampaignRequestConflict(CampaignRuntimeError):
    """Idempotency, immutable identity, or lifecycle fence rejected a write."""


class CampaignInvalidRequest(CampaignRuntimeError):
    """Transport-neutral Campaign request is malformed or unauthorized."""


class CampaignStatus(StrEnum):
    """Stable public projection of the host-owned Campaign state machine."""

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


def _text(value: object, field: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise ValueError(f"{field} must be a non-empty canonical string")
    return value


def _hash(value: object, field: str) -> str:
    text = _text(value, field)
    if len(text) != _SHA256_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise ValueError(f"{field} must be a lowercase sha256 digest")
    return text


def _utc(value: object, field: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _freeze_json(value: object) -> object:
    if isinstance(value, Mapping):
        raw = cast("Mapping[object, object]", value)
        if any(type(key) is not str for key in raw):
            raise ValueError("Campaign manifest keys must be strings")
        return MappingProxyType(
            {
                cast("str", key): _freeze_json(item)
                for key, item in sorted(
                    raw.items(), key=lambda pair: cast("str", pair[0])
                )
            }
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_freeze_json(item) for item in cast("Sequence[object]", value))
    if value is None or type(value) in {str, bool, int, float}:
        try:
            orjson.dumps(value)
        except (TypeError, orjson.JSONEncodeError) as exc:
            raise ValueError("Campaign manifest must be strict JSON") from exc
        return value
    raise ValueError("Campaign manifest must be strict JSON")


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _plain_json(item)
            for key, item in cast("Mapping[object, object]", value).items()
        }
    if isinstance(value, tuple):
        return [_plain_json(item) for item in cast("tuple[object, ...]", value)]
    return value


@dataclass(frozen=True, slots=True)
class CampaignCreateCommand:
    """Create one immutable draft under a durable request identity."""

    manifest_document: Mapping[str, object]
    idempotency_key: str

    def __post_init__(self) -> None:
        """Deep-freeze the document and validate canonical JSON."""
        frozen = _freeze_json(self.manifest_document)
        if not isinstance(frozen, Mapping):
            raise ValueError("manifest_document must be a JSON object")
        frozen_mapping = cast("Mapping[str, object]", frozen)
        try:
            canonical_request_hash(_plain_json(frozen_mapping))
        except AppCommandError as exc:
            raise ValueError("manifest_document must be canonical JSON") from exc
        object.__setattr__(
            self,
            "manifest_document",
            frozen_mapping,
        )
        object.__setattr__(
            self,
            "idempotency_key",
            _text(self.idempotency_key, "idempotency_key"),
        )

    @property
    def request_hash(self) -> str:
        """Bind the full input document, not only its derived manifest hash."""
        return canonical_request_hash({"manifest": _plain_json(self.manifest_document)})


@dataclass(frozen=True, slots=True)
class CampaignValidationCommand:
    """Validate one structured Campaign wizard step without persistence."""

    step: Literal["hypothesis", "experiment_plan", "governance", "manifest"]
    document: Mapping[str, object]

    def __post_init__(self) -> None:
        """Deep-freeze the step document before validation."""
        if self.step not in {
            "hypothesis",
            "experiment_plan",
            "governance",
            "manifest",
        }:
            raise ValueError("Campaign validation step is unsupported")
        frozen = _freeze_json(self.document)
        if not isinstance(frozen, Mapping):
            raise ValueError("Campaign validation document must be an object")
        object.__setattr__(self, "document", cast("Mapping[str, object]", frozen))


@dataclass(frozen=True, slots=True)
class CampaignValidationView:
    """Successful validation receipt with final canonical authority when complete."""

    step: Literal["hypothesis", "experiment_plan", "governance", "manifest"]
    canonical_manifest: Mapping[str, object] | None
    manifest_hash: str | None
    valid: bool = True


@dataclass(frozen=True, slots=True)
class CampaignApproveCommand:
    """Approve one exact persisted manifest until an explicit expiry."""

    campaign_id: str
    expected_manifest_hash: str
    operator_id: str
    expires_at: datetime
    idempotency_key: str

    def __post_init__(self) -> None:
        """Validate every approval identity before reaching the coordinator."""
        object.__setattr__(self, "campaign_id", _text(self.campaign_id, "campaign_id"))
        object.__setattr__(
            self,
            "expected_manifest_hash",
            _hash(self.expected_manifest_hash, "expected_manifest_hash"),
        )
        object.__setattr__(self, "operator_id", _text(self.operator_id, "operator_id"))
        object.__setattr__(self, "expires_at", _utc(self.expires_at, "expires_at"))
        object.__setattr__(
            self,
            "idempotency_key",
            _text(self.idempotency_key, "idempotency_key"),
        )

    @property
    def request_hash(self) -> str:
        """Return the exact human approval request identity."""
        return canonical_request_hash(
            {
                "campaign_id": self.campaign_id,
                "expected_manifest_hash": self.expected_manifest_hash,
                "operator_id": self.operator_id,
                "expires_at": _utc_text(self.expires_at),
            }
        )


@dataclass(frozen=True, slots=True)
class CampaignCancelCommand:
    """Cancel one Campaign under its immutable authorization hash."""

    campaign_id: str
    expected_authorization_hash: str
    idempotency_key: str

    def __post_init__(self) -> None:
        """Validate exact cancellation authority and request identity."""
        object.__setattr__(self, "campaign_id", _text(self.campaign_id, "campaign_id"))
        object.__setattr__(
            self,
            "expected_authorization_hash",
            _hash(self.expected_authorization_hash, "expected_authorization_hash"),
        )
        object.__setattr__(
            self,
            "idempotency_key",
            _text(self.idempotency_key, "idempotency_key"),
        )

    @property
    def request_hash(self) -> str:
        """Return the exact cancellation request identity."""
        return canonical_request_hash(
            {
                "campaign_id": self.campaign_id,
                "expected_authorization_hash": self.expected_authorization_hash,
            }
        )


@dataclass(frozen=True, slots=True)
class CampaignSandboxBudgetView:
    """Immutable per-sandbox limits shown before and after approval."""

    cpu_count: int
    memory_bytes: int
    process_limit: int
    temporary_storage_bytes: int
    wall_time_seconds: int
    output_bytes: int


@dataclass(frozen=True, slots=True)
class CampaignBudgetView:
    """Complete finite authority budget displayed by public adapters."""

    candidate_limit: int
    fold_run_limit: int
    generation_limit: int
    concurrent_sandbox_limit: int
    wall_time_limit_seconds: int
    temporary_storage_limit_bytes: int
    model_spend_limit_usd_micros: int
    sandbox_resource_limits: CampaignSandboxBudgetView


@dataclass(frozen=True, slots=True)
class CampaignToolRecordView:
    """Redacted Campaign tool activity safe for presentation."""

    call_id: str
    tool_name: str
    arguments_hash: str
    result_hash: str
    evidence_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CampaignGuardrailView:
    """Stable Campaign guardrail outcome without internal payloads."""

    status: Literal["passed", "blocked", "unknown"]
    reason_code: str | None


@dataclass(frozen=True, slots=True)
class CampaignUsageView:
    """Durable Campaign work counters and bounded spend visibility."""

    statistical_trial_count: int
    operational_attempt_count: int
    no_improvement_generations: int
    model_spend_usd_micros: int | None
    exhausted_reason: str | None


@dataclass(frozen=True, slots=True)
class CampaignView:
    """Non-sensitive Campaign projection reconstructed from persisted facts."""

    campaign_id: str
    status: CampaignStatus
    manifest_hash: str
    authorization_hash: str | None
    authorized_by: str | None
    authorization_expires_at: datetime | None
    search_axis: str
    source_snapshot_id: str
    allowed_tools: tuple[str, ...]
    budget: CampaignBudgetView
    best_primary_metric_value: float | None
    no_improvement_generations: int
    statistical_trial_count: int
    operational_attempt_count: int
    revision: int
    canonical_manifest: Mapping[str, object]
    objective: str | None = None
    output_summary: str | None = None
    tool_records: tuple[CampaignToolRecordView, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    guardrail: CampaignGuardrailView | None = None
    usage: CampaignUsageView | None = None
    event_cursor: int = 0
    projection_state: Literal["complete", "partial"] = "partial"
    projection_reason: str | None = "campaign_result_projection_unavailable"
    projection_version: int | None = None
    projection_updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CampaignListView:
    """Stable newest-first Campaign page."""

    items: tuple[CampaignView, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class CampaignEventView:
    """One persisted Campaign event suitable for deterministic SSE replay."""

    event_id: int
    durable_event_id: str
    campaign_id: str
    event_type: str
    previous_status: str | None
    status: CampaignStatus
    payload_hash: str
    occurred_at: datetime
    schema_version: int = 1


class CampaignRuntimePort(Protocol):
    """Shared Campaign use-case surface; transports never access stores directly."""

    def create_campaign(self, command: CampaignCreateCommand) -> CampaignView:
        """Create or recover one immutable draft."""
        ...

    def validate_campaign(
        self,
        command: CampaignValidationCommand,
    ) -> CampaignValidationView:
        """Validate a wizard step without creating durable state."""
        ...

    def approve_campaign(self, command: CampaignApproveCommand) -> CampaignView:
        """Approve or exactly replay one manifest-bound finite authority."""
        ...

    def get_campaign(self, campaign_id: str) -> CampaignView:
        """Return one persisted Campaign projection."""
        ...

    def list_campaigns(
        self,
        *,
        status: CampaignStatus | None,
        limit: int,
        offset: int,
    ) -> CampaignListView:
        """List durable Campaigns with an optional status filter."""
        ...

    def list_campaign_events(
        self,
        campaign_id: str,
        *,
        after_event_id: int | None = None,
    ) -> tuple[CampaignEventView, ...]:
        """Replay only persisted events after an optional public event ID."""
        ...

    def cancel_campaign(self, command: CampaignCancelCommand) -> CampaignView:
        """Cancel or exactly replay one authorized Campaign."""
        ...


__all__ = [
    "CampaignApproveCommand",
    "CampaignBudgetView",
    "CampaignCancelCommand",
    "CampaignCreateCommand",
    "CampaignEventView",
    "CampaignGuardrailView",
    "CampaignInvalidRequest",
    "CampaignListView",
    "CampaignRequestConflict",
    "CampaignResourceNotFound",
    "CampaignRuntimeError",
    "CampaignRuntimePort",
    "CampaignRuntimeUnavailable",
    "CampaignSandboxBudgetView",
    "CampaignStatus",
    "CampaignToolRecordView",
    "CampaignUsageView",
    "CampaignValidationCommand",
    "CampaignValidationView",
    "CampaignView",
]
