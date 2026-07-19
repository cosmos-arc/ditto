"""
Pure typed persistence contracts and canonical codecs for experiments.

The values in this module are adapter-independent. SQLite runtime behavior stays
under :mod:`ditto_analysis.storage.sqlite.experiments`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, cast

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments._validation import require_utc_datetime
from ditto_analysis.experiments.models import (
    AttemptId,
    BacktestRunId,
    CandidateId,
    CheckpointRef,
    ContentHash,
    ExperimentDesiredState,
    ExperimentFailureCode,
    ExperimentId,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
    FoldId,
    SnapshotId,
    StrategyVersion,
)
from ditto_analysis.experiments.specs import (
    CandidateSpec,
    ExperimentBudget,
    ExperimentFailurePolicy,
    ExperimentLaunchSpec,
    FoldProtocolSpec,
    FrozenValue,
)

__all__ = [
    "ArtifactRecord",
    "AttemptPersistenceSpec",
    "AttemptProjection",
    "AttemptView",
    "CanonicalPayload",
    "DateWindow",
    "ExperimentProjection",
    "FoldKey",
    "FoldPersistenceSpec",
    "FoldProjection",
    "FoldRole",
    "FoldView",
    "GateEvaluationRecord",
    "HoldoutClaimRecord",
    "LeaseFence",
    "ResearchCycleIdentity",
    "SchedulerLease",
    "SchedulerSlot",
    "StatusEventRecord",
    "StatusSubjectType",
    "canonical_payload",
    "decode_launch_spec",
    "encode_candidate_parameters",
    "encode_launch_spec",
]

_CANONICAL_SCHEMA_VERSION = 1
_DRIVE_PREFIX_LENGTH = 2


def _error(message: str, reason_code: str, **details: object) -> ExperimentSpecError:
    return ExperimentSpecError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _require_non_empty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise _error(
            f"{field} must be a non-empty unpadded string",
            "invalid_persistence_identity",
            field=field,
        )
    return value


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return {str(key): _json_value(item) for key, item in mapping.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sequence = cast("Sequence[object]", value)
        return [_json_value(item) for item in sequence]
    if value is None or isinstance(value, str) or type(value) in (int, float, bool):
        return value
    raise _error(
        "canonical payload contains an unsupported value",
        "invalid_canonical_payload",
        value_type=type(value).__name__,
    )


@dataclass(frozen=True, slots=True)
class CanonicalPayload:
    """Versioned canonical JSON bytes and their SHA-256 digest."""

    schema_version: int
    json_bytes: bytes
    content_hash: ContentHash

    def __post_init__(self) -> None:
        """Validate version, bytes, and the content digest as one value."""
        if type(self.schema_version) is not int or self.schema_version <= 0:
            raise _error(
                "canonical schema version must be positive",
                "invalid_canonical_schema_version",
            )
        if not isinstance(cast("object", self.json_bytes), bytes):
            raise _error("canonical JSON must be bytes", "invalid_canonical_payload")
        actual = hashlib.sha256(self.json_bytes).hexdigest()
        if self.content_hash != ContentHash(actual):
            raise _error(
                "canonical payload hash does not match its bytes",
                "canonical_payload_hash_mismatch",
            )


def canonical_payload(
    value: Mapping[str, object], *, schema_version: int = _CANONICAL_SCHEMA_VERSION
) -> CanonicalPayload:
    """Encode one mapping with deterministic RFC-8259-compatible JSON rules."""
    if type(schema_version) is not int or schema_version <= 0:
        raise _error(
            "canonical schema version must be positive",
            "invalid_canonical_schema_version",
        )
    normalized = _json_value(value)
    json_bytes = json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return CanonicalPayload(
        schema_version=schema_version,
        json_bytes=json_bytes,
        content_hash=ContentHash(hashlib.sha256(json_bytes).hexdigest()),
    )


def encode_candidate_parameters(
    parameters: Mapping[str, FrozenValue],
) -> CanonicalPayload:
    """Encode candidate parameters with the shared stable mapping codec."""
    return canonical_payload(cast("Mapping[str, object]", parameters))


def _epoch_us(value: datetime) -> int:
    require_utc_datetime(value, "datetime")
    return int(value.timestamp() * 1_000_000)


def _datetime_from_epoch_us(value: object, field: str) -> datetime:
    if type(value) is not int or value < 0:
        raise _error(
            f"{field} is not a valid epoch-us value", "invalid_canonical_payload"
        )
    return datetime.fromtimestamp(value / 1_000_000, tz=UTC)


def encode_launch_spec(spec: ExperimentLaunchSpec) -> CanonicalPayload:
    """Encode the complete typed launch specification without lossy fields."""
    return canonical_payload(
        {
            "schema_version": _CANONICAL_SCHEMA_VERSION,
            "experiment_id": str(spec.experiment_id),
            "strategy_version": str(spec.strategy_version),
            "strategy_spec_hash": str(spec.strategy_spec_hash),
            "snapshot_id": str(spec.snapshot_id),
            "candidates": [
                {
                    "candidate_id": str(candidate.candidate_id),
                    "ordinal": candidate.ordinal,
                    "is_baseline": candidate.is_baseline,
                    "parameters": _json_value(candidate.parameters),
                }
                for candidate in spec.candidates
            ],
            "fold_protocol": {
                "protocol_id": spec.fold_protocol.protocol_id,
                "protocol_version": spec.fold_protocol.protocol_version,
                "protocol_hash": str(spec.fold_protocol.protocol_hash),
            },
            "seed": spec.seed,
            "worker_count": spec.worker_count,
            "failure_policy": spec.failure_policy.value,
            "budget": {
                "candidate_limit": spec.budget.candidate_limit,
                "fold_run_limit": spec.budget.fold_run_limit,
            },
            "desired_state": spec.desired_state.value,
            "created_at_epoch_us": _epoch_us(spec.created_at),
        }
    )


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error(f"{field} must be an object", "invalid_canonical_payload")
    return cast("Mapping[str, Any]", value)


def decode_launch_spec(
    payload: bytes,
    expected_hash: ContentHash,
) -> ExperimentLaunchSpec:
    """Verify and decode a canonical launch payload into the full typed spec."""
    actual_hash = ContentHash(hashlib.sha256(payload).hexdigest())
    if actual_hash != expected_hash:
        raise _error(
            "launch payload hash mismatch",
            "canonical_payload_hash_mismatch",
            expected_hash=str(expected_hash),
            actual_hash=str(actual_hash),
        )
    try:
        decoded = json.loads(payload)
        root = _mapping(decoded, "launch_spec")
        if root.get("schema_version") != _CANONICAL_SCHEMA_VERSION:
            raise _error(
                "unsupported launch schema version",
                "unsupported_canonical_schema_version",
            )
        candidates_value = root["candidates"]
        if not isinstance(candidates_value, list):
            raise _error("candidates must be a list", "invalid_canonical_payload")
        candidate_items = cast("list[object]", candidates_value)
        candidates = tuple(
            CandidateSpec(
                candidate_id=CandidateId(str(item["candidate_id"])),
                ordinal=int(item["ordinal"]),
                is_baseline=bool(item["is_baseline"]),
                parameters=_mapping(item["parameters"], "parameters"),
            )
            for item_value in candidate_items
            for item in (_mapping(item_value, "candidate"),)
        )
        protocol = _mapping(root["fold_protocol"], "fold_protocol")
        budget = _mapping(root["budget"], "budget")
        spec = ExperimentLaunchSpec(
            experiment_id=ExperimentId(str(root["experiment_id"])),
            strategy_version=StrategyVersion(str(root["strategy_version"])),
            strategy_spec_hash=ContentHash(str(root["strategy_spec_hash"])),
            snapshot_id=SnapshotId(str(root["snapshot_id"])),
            candidates=candidates,
            fold_protocol=FoldProtocolSpec(
                protocol_id=str(protocol["protocol_id"]),
                protocol_version=int(protocol["protocol_version"]),
                protocol_hash=ContentHash(str(protocol["protocol_hash"])),
            ),
            seed=int(root["seed"]),
            worker_count=int(root["worker_count"]),
            failure_policy=ExperimentFailurePolicy(str(root["failure_policy"])),
            budget=ExperimentBudget(
                candidate_limit=int(budget["candidate_limit"]),
                fold_run_limit=int(budget["fold_run_limit"]),
            ),
            desired_state=ExperimentDesiredState(str(root["desired_state"])),
            created_at=_datetime_from_epoch_us(
                root["created_at_epoch_us"], "created_at_epoch_us"
            ),
        )
    except ExperimentSpecError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise _error(
            "launch payload is malformed",
            "invalid_canonical_payload",
            error_type=type(exc).__name__,
        ) from exc
    if encode_launch_spec(spec).json_bytes != payload:
        raise _error(
            "launch payload is not in canonical form",
            "noncanonical_payload",
        )
    return spec


@dataclass(frozen=True, slots=True)
class ResearchCycleIdentity:
    """Frozen research-cycle identity shared by every experiment clone."""

    cycle_id: str
    cycle_hash: ContentHash

    def __post_init__(self) -> None:
        """Validate the opaque cycle identity and canonical digest."""
        _require_non_empty(self.cycle_id, "cycle_id")
        if not isinstance(cast("object", self.cycle_hash), ContentHash):
            raise _error("cycle_hash must be ContentHash", "invalid_cycle_identity")


@dataclass(frozen=True, slots=True)
class DateWindow:
    """Inclusive calendar-date window with a nondecreasing boundary."""

    start: date
    end: date

    def __post_init__(self) -> None:
        """Reject datetimes and inverted date windows."""
        raw_start = cast("object", self.start)
        raw_end = cast("object", self.end)
        if (
            not isinstance(raw_start, date)
            or isinstance(raw_start, datetime)
            or not isinstance(raw_end, date)
            or isinstance(raw_end, datetime)
            or raw_start > raw_end
        ):
            raise _error("date window is invalid", "invalid_date_window")


class FoldRole(StrEnum):
    """Stable fold role controlling train-window semantics."""

    EXPLORATION = "exploration"
    WALK_FORWARD = "walk_forward"
    HOLDOUT = "holdout"


@dataclass(frozen=True, slots=True)
class FoldKey:
    """Full fold identity; fold IDs alone are intentionally insufficient."""

    experiment_id: ExperimentId
    candidate_id: CandidateId
    fold_id: FoldId


@dataclass(frozen=True, slots=True)
class ExperimentProjection:
    """Mutable experiment projection guarded by an optimistic revision."""

    record: ExperimentRecord
    queue_ordinal: int | None
    revision: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class FoldPersistenceSpec:
    """Immutable, canonical fold relation and protocol payload."""

    key: FoldKey
    ordinal: int
    fold_role: FoldRole
    train_window: DateWindow | None
    test_window: DateWindow
    purge_sessions: int
    embargo_sessions: int
    canonical_payload: bytes
    payload_hash: ContentHash

    @classmethod
    def create(
        cls,
        key: FoldKey,
        ordinal: int,
        fold_role: FoldRole,
        train_window: DateWindow | None,
        test_window: DateWindow,
        purge_sessions: int,
        embargo_sessions: int,
    ) -> FoldPersistenceSpec:
        """Create a fold whose canonical payload exactly mirrors its relation."""
        payload = canonical_payload(
            {
                "experiment_id": str(key.experiment_id),
                "candidate_id": str(key.candidate_id),
                "fold_id": str(key.fold_id),
                "ordinal": ordinal,
                "fold_role": fold_role.value,
                "train_window": None
                if train_window is None
                else {
                    "start": train_window.start.isoformat(),
                    "end": train_window.end.isoformat(),
                },
                "test_window": {
                    "start": test_window.start.isoformat(),
                    "end": test_window.end.isoformat(),
                },
                "purge_sessions": purge_sessions,
                "embargo_sessions": embargo_sessions,
            }
        )
        return cls(
            key=key,
            ordinal=ordinal,
            fold_role=fold_role,
            train_window=train_window,
            test_window=test_window,
            purge_sessions=purge_sessions,
            embargo_sessions=embargo_sessions,
            canonical_payload=payload.json_bytes,
            payload_hash=payload.content_hash,
        )


@dataclass(frozen=True, slots=True)
class FoldProjection:
    """Mutable fold work projection guarded by an optimistic revision."""

    key: FoldKey
    status: ExperimentStatus
    claim_owner_token: str | None
    created_at: datetime
    updated_at: datetime
    revision: int


@dataclass(frozen=True, slots=True)
class FoldView:
    """Lossless fold specification and projection pair."""

    spec: FoldPersistenceSpec
    projection: FoldProjection


@dataclass(frozen=True, slots=True)
class AttemptPersistenceSpec:
    """Immutable attempt lineage and reproduction identity."""

    attempt_id: AttemptId
    fold_key: FoldKey
    ordinal: int
    parent_attempt_id: AttemptId | None
    resume_from_run_id: BacktestRunId | None
    reproduction_fingerprint: ContentHash
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AttemptProjection:
    """Mutable attempt execution projection guarded by a revision."""

    attempt_id: AttemptId
    status: ExperimentStatus
    backtest_run_id: BacktestRunId | None
    checkpoint_ref: CheckpointRef | None
    failure_code: ExperimentFailureCode | None
    created_at: datetime
    updated_at: datetime
    revision: int


@dataclass(frozen=True, slots=True)
class AttemptView:
    """Lossless attempt specification and projection pair."""

    spec: AttemptPersistenceSpec
    projection: AttemptProjection


class StatusSubjectType(StrEnum):
    """Typed subject lineage for append-only status events."""

    EXPERIMENT = "experiment"
    FOLD = "fold"
    ATTEMPT = "attempt"


@dataclass(frozen=True, slots=True)
class StatusEventRecord:
    """Append-only, hash-verified lifecycle event."""

    event_id: str
    experiment_id: ExperimentId
    candidate_id: CandidateId | None
    fold_id: FoldId | None
    attempt_id: AttemptId | None
    subject_type: StatusSubjectType
    subject_revision: int
    previous_status: ExperimentStatus | None
    status: ExperimentStatus
    desired_state: ExperimentDesiredState | None
    stage: ExperimentStage | None
    failure_code: ExperimentFailureCode | None
    reason_code: str | None
    detail: Mapping[str, object]
    detail_hash: ContentHash
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    """Immutable artifact lineage plus one-way pin projection."""

    artifact_id: str
    experiment_id: ExperimentId
    candidate_id: CandidateId | None
    fold_id: FoldId | None
    attempt_id: AttemptId | None
    artifact_kind: str
    relative_path: str
    content_hash: ContentHash
    schema_hash: ContentHash
    row_count: int
    byte_size: int
    reproduction_fingerprint: ContentHash
    manifest: Mapping[str, object]
    is_pinned: bool
    pinned_at: datetime | None
    created_at: datetime
    revision: int


@dataclass(frozen=True, slots=True)
class GateEvaluationRecord:
    """Append-only policy gate evaluation with canonical payload identity."""

    evaluation_id: str
    experiment_id: ExperimentId
    candidate_id: CandidateId | None
    fold_id: FoldId | None
    attempt_id: AttemptId | None
    rule_id: str
    policy_version: str
    layer: str
    outcome: str
    observed: object
    policy: object
    artifact_id: str | None
    evaluated_at: datetime

    @property
    def payload_hash(self) -> ContentHash:
        """Hash the complete canonical evaluation payload."""
        return canonical_payload(
            {
                "evaluation_id": self.evaluation_id,
                "experiment_id": str(self.experiment_id),
                "candidate_id": None
                if self.candidate_id is None
                else str(self.candidate_id),
                "fold_id": None if self.fold_id is None else str(self.fold_id),
                "attempt_id": None if self.attempt_id is None else str(self.attempt_id),
                "rule_id": self.rule_id,
                "policy_version": self.policy_version,
                "layer": self.layer,
                "outcome": self.outcome,
                "observed": self.observed,
                "policy": self.policy,
                "artifact_id": self.artifact_id,
                "evaluated_at_epoch_us": _epoch_us(self.evaluated_at),
            }
        ).content_hash


@dataclass(frozen=True, slots=True)
class HoldoutClaimRecord:
    """One-shot research-cycle holdout claim and operator confirmation."""

    claim_id: str
    cycle: ResearchCycleIdentity
    fold_key: FoldKey
    resolved_spec_hash: ContentHash
    parameters_hash: ContentHash
    snapshot_id: SnapshotId
    window: DateWindow
    reproduction_fingerprint: ContentHash
    logical_run_id: str
    operator_confirmation: str
    selection_reason: Mapping[str, object]
    claimed_at: datetime

    @property
    def claim_payload_hash(self) -> ContentHash:
        """Hash every immutable holdout claim field."""
        return canonical_payload(
            {
                "claim_id": self.claim_id,
                "cycle_id": self.cycle.cycle_id,
                "cycle_hash": str(self.cycle.cycle_hash),
                "experiment_id": str(self.fold_key.experiment_id),
                "candidate_id": str(self.fold_key.candidate_id),
                "fold_id": str(self.fold_key.fold_id),
                "resolved_spec_hash": str(self.resolved_spec_hash),
                "parameters_hash": str(self.parameters_hash),
                "snapshot_id": str(self.snapshot_id),
                "window_start": self.window.start.isoformat(),
                "window_end": self.window.end.isoformat(),
                "reproduction_fingerprint": str(self.reproduction_fingerprint),
                "logical_run_id": self.logical_run_id,
                "operator_confirmation": self.operator_confirmation,
                "selection_reason": self.selection_reason,
                "claimed_at_epoch_us": _epoch_us(self.claimed_at),
            }
        ).content_hash


@dataclass(frozen=True, slots=True)
class LeaseFence:
    """Worker authority bound to experiment, owner, revision, and expiry."""

    experiment_id: ExperimentId
    owner_token: str
    revision: int
    lease_until_epoch_us: int


@dataclass(frozen=True, slots=True)
class SchedulerSlot:
    """Current singleton scheduler-slot projection, free or leased."""

    slot_id: str
    experiment_id: ExperimentId | None
    owner_token: str | None
    lease_until_epoch_us: int | None
    acquired_at_epoch_us: int | None
    renewed_at_epoch_us: int | None
    revision: int


@dataclass(frozen=True, slots=True)
class SchedulerLease:
    """Owned scheduler lease returned after a successful fenced CAS."""

    experiment_id: ExperimentId
    owner_token: str
    lease_until_epoch_us: int
    acquired_at_epoch_us: int
    renewed_at_epoch_us: int
    revision: int

    @property
    def fence(self) -> LeaseFence:
        """Return the immutable authority token for downstream writes."""
        return LeaseFence(
            experiment_id=self.experiment_id,
            owner_token=self.owner_token,
            revision=self.revision,
            lease_until_epoch_us=self.lease_until_epoch_us,
        )


def validate_artifact_relative_path(relative_path: str) -> PurePosixPath:
    """Validate a canonical relative POSIX path before it reaches SQLite."""
    raw_path = cast("object", relative_path)
    if (
        not isinstance(raw_path, str)
        or not relative_path
        or relative_path != relative_path.strip()
        or relative_path.startswith("/")
        or "\\" in relative_path
        or "\x00" in relative_path
        or "//" in relative_path
        or (
            len(relative_path) >= _DRIVE_PREFIX_LENGTH
            and relative_path[0].isalpha()
            and relative_path[1] == ":"
        )
    ):
        raise _error(
            "artifact path must be a canonical relative POSIX path",
            "invalid_artifact_relative_path",
            relative_path=relative_path,
        )
    path = PurePosixPath(relative_path)
    if any(part in ("", ".", "..") for part in relative_path.split("/")):
        raise _error(
            "artifact path cannot contain dot or empty segments",
            "invalid_artifact_relative_path",
            relative_path=relative_path,
        )
    return path
