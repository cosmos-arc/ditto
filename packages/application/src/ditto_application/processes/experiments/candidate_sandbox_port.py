"""Consumer-owned raw sandbox I/O contracts for generated research candidates."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, cast

from ditto_analysis.experiments.generated_code import (
    ResearchCodeArtifact,
    SandboxExecutionManifest,
    SandboxExitStatus,
    SandboxResourceLimits,
)
from ditto_analysis.experiments.models import ContentHash, SnapshotId
from ditto_analysis.experiments.persistence import canonical_payload

from ditto_application.exceptions import AppProcessError

__all__ = [
    "CandidateSandboxPort",
    "FrozenSandboxArtifact",
    "FrozenSandboxWindow",
    "SandboxArtifactFormat",
    "SandboxExecutionResult",
    "SandboxFitRequest",
    "SandboxScoreKey",
    "SandboxScoreRequest",
    "build_successful_sandbox_result",
    "freeze_sandbox_artifact",
    "sandbox_manifest_attestation_hash",
]


def _error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        "generated candidate sandbox contract is invalid",
        details={"code": "GENERATED_CANDIDATE_INVALID", "reason": reason, **details},
    )


class SandboxArtifactFormat(StrEnum):
    """Approved non-executable artifact serializations."""

    JSON = "application/json"
    ARROW_IPC = "application/vnd.apache.arrow.file"
    NUMPY_NPY = "application/x-npy"


@dataclass(frozen=True, slots=True)
class FrozenSandboxArtifact:
    """Content-addressed raw bytes crossing the sandbox boundary."""

    payload: bytes
    serialization: SandboxArtifactFormat
    content_hash: ContentHash
    schema_hash: ContentHash
    row_count: int
    allow_pickle: bool = False

    def __post_init__(self) -> None:
        """Copy bytes and reject executable serialization semantics."""
        if not isinstance(cast("object", self.payload), bytes) or not self.payload:
            raise _error("sandbox_artifact_payload_invalid")
        if type(self.serialization) is not SandboxArtifactFormat:
            raise _error("sandbox_artifact_serialization_invalid")
        if (
            type(self.content_hash) is not ContentHash
            or type(self.schema_hash) is not ContentHash
        ):
            raise _error("sandbox_artifact_identity_invalid")
        if type(self.row_count) is not int or self.row_count < 0:
            raise _error("sandbox_artifact_row_count_invalid")
        if type(self.allow_pickle) is not bool or self.allow_pickle:
            raise _error("sandbox_pickle_forbidden")
        copied = bytes(self.payload)
        actual = ContentHash(hashlib.sha256(copied).hexdigest())
        if actual != self.content_hash:
            raise _error("sandbox_artifact_hash_mismatch")
        object.__setattr__(self, "payload", copied)


def freeze_sandbox_artifact(
    payload: bytes,
    *,
    serialization: SandboxArtifactFormat,
    schema_hash: ContentHash,
    row_count: int,
) -> FrozenSandboxArtifact:
    """Freeze adapter bytes with a host-computed content identity."""
    if not isinstance(cast("object", payload), bytes):
        raise _error("sandbox_artifact_payload_invalid")
    copied = bytes(payload)
    return FrozenSandboxArtifact(
        payload=copied,
        serialization=serialization,
        content_hash=ContentHash(hashlib.sha256(copied).hexdigest()),
        schema_hash=schema_hash,
        row_count=row_count,
        allow_pickle=False,
    )


@dataclass(frozen=True, slots=True)
class SandboxScoreKey:
    """Trusted identity/time key expected from one visible row."""

    entity_id: str
    event_time_epoch_us: int
    known_at_epoch_us: int

    def __post_init__(self) -> None:
        """Reject ambiguous row identities and timestamps."""
        if (
            type(self.entity_id) is not str
            or not self.entity_id
            or self.entity_id != self.entity_id.strip()
        ):
            raise _error("sandbox_score_identity_invalid")
        for field_name in ("event_time_epoch_us", "known_at_epoch_us"):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise _error("sandbox_score_time_invalid", field=field_name)


def _freeze_score_keys(value: object) -> tuple[SandboxScoreKey, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _error("sandbox_window_keys_invalid")
    keys = tuple(cast("Sequence[object]", value))
    if any(type(item) is not SandboxScoreKey for item in keys):
        raise _error("sandbox_window_keys_invalid")
    return cast("tuple[SandboxScoreKey, ...]", keys)


@dataclass(frozen=True, slots=True)
class FrozenSandboxWindow:
    """One exact PIT-visible input artifact and its trusted output row keys."""

    artifact: FrozenSandboxArtifact
    snapshot_id: SnapshotId
    knowledge_cutoff_epoch_us: int
    score_keys: Sequence[SandboxScoreKey]

    def __post_init__(self) -> None:
        """Freeze keys and fail closed on any future-visible row."""
        if type(self.artifact) is not FrozenSandboxArtifact:
            raise _error("sandbox_window_artifact_invalid")
        if type(self.snapshot_id) is not SnapshotId:
            raise _error("sandbox_window_snapshot_invalid")
        if (
            type(self.knowledge_cutoff_epoch_us) is not int
            or self.knowledge_cutoff_epoch_us < 0
        ):
            raise _error("sandbox_window_cutoff_invalid")
        typed = _freeze_score_keys(cast("object", self.score_keys))
        if len(typed) != self.artifact.row_count:
            raise _error("sandbox_window_row_count_mismatch")
        identities = tuple((item.entity_id, item.event_time_epoch_us) for item in typed)
        if len(set(identities)) != len(identities):
            raise _error("sandbox_window_duplicate_identity")
        if any(
            item.known_at_epoch_us > self.knowledge_cutoff_epoch_us for item in typed
        ):
            raise _error("sandbox_window_future_visibility")
        object.__setattr__(self, "score_keys", typed)

    @property
    def identity_hash(self) -> ContentHash:
        """Bind bytes to their exact snapshot, cutoff, and visible row keys."""
        return canonical_payload(
            {
                "artifact_hash": str(self.artifact.content_hash),
                "schema_hash": str(self.artifact.schema_hash),
                "row_count": self.artifact.row_count,
                "snapshot_id": str(self.snapshot_id),
                "knowledge_cutoff_epoch_us": self.knowledge_cutoff_epoch_us,
                "score_keys": [
                    {
                        "entity_id": item.entity_id,
                        "event_time_epoch_us": item.event_time_epoch_us,
                        "known_at_epoch_us": item.known_at_epoch_us,
                    }
                    for item in self.score_keys
                ],
            }
        ).content_hash


@dataclass(frozen=True, slots=True)
class SandboxFitRequest:
    """Exact sandbox fit invocation over a trusted training stream."""

    code_artifact: ResearchCodeArtifact
    training_stream: FrozenSandboxWindow
    resource_limits: SandboxResourceLimits
    seed: int

    def __post_init__(self) -> None:
        """Validate the exact code, window, limits, and seed inputs."""
        _validate_invocation_fields(self)

    @property
    def input_hash(self) -> ContentHash:
        """Return the complete fit invocation identity."""
        return _invocation_hash(self, phase="fit")


@dataclass(frozen=True, slots=True)
class SandboxScoreRequest:
    """Exact sandbox score invocation over one immutable fitted state."""

    code_artifact: ResearchCodeArtifact
    visible_window: FrozenSandboxWindow
    immutable_model_state: FrozenSandboxArtifact
    resource_limits: SandboxResourceLimits
    seed: int

    def __post_init__(self) -> None:
        """Validate the exact code, window, immutable state, limits, and seed."""
        _validate_invocation_fields(self)
        if type(self.immutable_model_state) is not FrozenSandboxArtifact:
            raise _error("sandbox_model_state_invalid")

    @property
    def input_hash(self) -> ContentHash:
        """Return the complete score invocation identity."""
        return _invocation_hash(self, phase="score")


def _validate_invocation_fields(
    request: SandboxFitRequest | SandboxScoreRequest,
) -> None:
    if type(request.code_artifact) is not ResearchCodeArtifact:
        raise _error("sandbox_code_artifact_invalid")
    window = (
        request.training_stream
        if isinstance(request, SandboxFitRequest)
        else request.visible_window
    )
    if type(window) is not FrozenSandboxWindow:
        raise _error("sandbox_window_invalid")
    if type(request.resource_limits) is not SandboxResourceLimits:
        raise _error("sandbox_resource_limits_invalid")
    if type(request.seed) is not int or request.seed < 0:
        raise _error("sandbox_seed_invalid")


def _invocation_hash(
    request: SandboxFitRequest | SandboxScoreRequest,
    *,
    phase: str,
) -> ContentHash:
    window = (
        request.training_stream
        if isinstance(request, SandboxFitRequest)
        else request.visible_window
    )
    state_hash = (
        None
        if isinstance(request, SandboxFitRequest)
        else str(request.immutable_model_state.content_hash)
    )
    return canonical_payload(
        {
            "schema_id": "r5-sandbox-invocation",
            "schema_version": 1,
            "phase": phase,
            "code_artifact_hash": str(request.code_artifact.artifact_hash),
            "image_digest": str(request.code_artifact.image_digest),
            "window_identity_hash": str(window.identity_hash),
            "model_state_hash": state_hash,
            "seed": request.seed,
        }
    ).content_hash


@dataclass(frozen=True, slots=True)
class SandboxExecutionResult:
    """Raw sandbox output plus host-verifiable execution attestation."""

    output: FrozenSandboxArtifact
    manifest: SandboxExecutionManifest

    def __post_init__(self) -> None:
        """Require typed raw output and execution evidence."""
        if (
            type(self.output) is not FrozenSandboxArtifact
            or type(self.manifest) is not SandboxExecutionManifest
        ):
            raise _error("sandbox_execution_result_invalid")


class CandidateSandboxPort(Protocol):
    """Physical generated-code runner owned by the Application consumer."""

    def fit(self, request: SandboxFitRequest) -> SandboxExecutionResult:
        """Run fixed-contract fit without network or host state access."""
        ...

    def score(self, request: SandboxScoreRequest) -> SandboxExecutionResult:
        """Run fixed-contract score and return only raw attested bytes."""
        ...


@dataclass(frozen=True, slots=True)
class _SandboxAttestationFields:
    code_artifact_hash: ContentHash
    runtime_digest: ContentHash
    resource_limits: SandboxResourceLimits
    input_hash: ContentHash
    output_hash: ContentHash | None
    seed: int
    exit_status: SandboxExitStatus
    exit_code: int | None


def _attestation_payload(fields: _SandboxAttestationFields) -> dict[str, object]:
    return {
        "schema_id": "r5-sandbox-execution-attestation",
        "schema_version": 1,
        "code_artifact_hash": str(fields.code_artifact_hash),
        "runtime_digest": str(fields.runtime_digest),
        "resource_limits": {
            "cpu_count": fields.resource_limits.cpu_count,
            "memory_bytes": fields.resource_limits.memory_bytes,
            "process_limit": fields.resource_limits.process_limit,
            "temporary_storage_bytes": (fields.resource_limits.temporary_storage_bytes),
            "wall_time_seconds": fields.resource_limits.wall_time_seconds,
            "output_bytes": fields.resource_limits.output_bytes,
        },
        "input_hash": str(fields.input_hash),
        "output_hash": (
            None if fields.output_hash is None else str(fields.output_hash)
        ),
        "seed": fields.seed,
        "exit_status": fields.exit_status.value,
        "exit_code": fields.exit_code,
    }


def sandbox_manifest_attestation_hash(
    manifest: SandboxExecutionManifest,
) -> ContentHash:
    """Recompute the complete sandbox attestation identity."""
    return canonical_payload(
        _attestation_payload(
            _SandboxAttestationFields(
                code_artifact_hash=manifest.code_artifact_hash,
                runtime_digest=manifest.runtime_digest,
                resource_limits=manifest.resource_limits,
                input_hash=manifest.input_hash,
                output_hash=manifest.output_hash,
                seed=manifest.seed,
                exit_status=manifest.exit_status,
                exit_code=manifest.exit_code,
            )
        )
    ).content_hash


def build_successful_sandbox_result(
    request: SandboxFitRequest | SandboxScoreRequest,
    output: FrozenSandboxArtifact,
) -> SandboxExecutionResult:
    """Build one internally sealed successful execution result for adapters/fakes."""
    fields = _SandboxAttestationFields(
        code_artifact_hash=request.code_artifact.artifact_hash,
        runtime_digest=request.code_artifact.image_digest,
        resource_limits=request.resource_limits,
        input_hash=request.input_hash,
        output_hash=output.content_hash,
        seed=request.seed,
        exit_status=SandboxExitStatus.SUCCEEDED,
        exit_code=0,
    )
    manifest = SandboxExecutionManifest(
        code_artifact_hash=request.code_artifact.artifact_hash,
        runtime_digest=request.code_artifact.image_digest,
        resource_limits=request.resource_limits,
        input_hash=request.input_hash,
        output_hash=output.content_hash,
        seed=request.seed,
        exit_status=SandboxExitStatus.SUCCEEDED,
        exit_code=0,
        attestation_hash=canonical_payload(_attestation_payload(fields)).content_hash,
    )
    return SandboxExecutionResult(output=output, manifest=manifest)
