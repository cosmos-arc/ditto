"""Pure generated research-code and sandbox attestation contracts."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.models import ContentHash
from ditto_analysis.experiments.persistence import canonical_payload

__all__ = [
    "ResearchCodeArtifact",
    "SandboxExecutionManifest",
    "SandboxExitStatus",
    "SandboxResourceLimits",
]


def _code_error(
    message: str,
    reason_code: str,
    **details: object,
) -> ExperimentSpecError:
    return ExperimentSpecError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _positive_int(value: object, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise _code_error(
            f"{field} must be a positive integer",
            "invalid_sandbox_resource_limit",
            field=field,
        )
    return value


def _freeze_dependencies(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _code_error(
            "dependencies must be an ordered sequence",
            "invalid_research_code_dependencies",
        )
    raw = tuple(cast("Sequence[object]", value))
    if not raw or any(
        type(item) is not str or not item.strip() or item != item.strip()
        for item in raw
    ):
        raise _code_error(
            "dependencies must contain pinned non-empty declarations",
            "invalid_research_code_dependencies",
        )
    typed = cast("tuple[str, ...]", raw)
    if len(set(typed)) != len(typed):
        raise _code_error(
            "dependencies cannot contain duplicates",
            "invalid_research_code_dependencies",
        )
    return tuple(sorted(typed))


@dataclass(frozen=True, slots=True)
class ResearchCodeArtifact:
    """Content-addressed generated code without trusted evaluation fields."""

    source_code: str
    source_hash: ContentHash
    canonical_ast_hash: ContentHash
    dependency_lock_hash: ContentHash
    dependencies: Sequence[str]
    image_digest: ContentHash
    input_schema_hash: ContentHash
    output_schema_hash: ContentHash

    def __post_init__(self) -> None:
        """Verify source content and freeze the dependency declaration."""
        if type(self.source_code) is not str or not self.source_code.strip():
            raise _code_error(
                "source_code must be non-empty",
                "invalid_research_code_source",
            )
        for value, field in (
            (self.source_hash, "source_hash"),
            (self.canonical_ast_hash, "canonical_ast_hash"),
            (self.dependency_lock_hash, "dependency_lock_hash"),
            (self.image_digest, "image_digest"),
            (self.input_schema_hash, "input_schema_hash"),
            (self.output_schema_hash, "output_schema_hash"),
        ):
            if type(value) is not ContentHash:
                raise _code_error(
                    f"{field} must be ContentHash",
                    "invalid_research_code_artifact",
                    field=field,
                )
        actual_source_hash = ContentHash(
            hashlib.sha256(self.source_code.encode("utf-8")).hexdigest()
        )
        if actual_source_hash != self.source_hash:
            raise _code_error(
                "source_hash does not match source_code",
                "research_code_hash_mismatch",
            )
        object.__setattr__(
            self, "dependencies", _freeze_dependencies(self.dependencies)
        )

    @property
    def artifact_hash(self) -> ContentHash:
        """Return the stable identity of code, schemas, image, and dependencies."""
        return canonical_payload(
            {
                "schema_id": "r5-research-code-artifact",
                "schema_version": 1,
                "source_hash": str(self.source_hash),
                "canonical_ast_hash": str(self.canonical_ast_hash),
                "dependency_lock_hash": str(self.dependency_lock_hash),
                "dependencies": list(self.dependencies),
                "image_digest": str(self.image_digest),
                "input_schema_hash": str(self.input_schema_hash),
                "output_schema_hash": str(self.output_schema_hash),
            }
        ).content_hash


class SandboxExitStatus(StrEnum):
    """Stable untrusted-code execution outcome."""

    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    RESOURCE_EXHAUSTED = "resource_exhausted"


@dataclass(frozen=True, slots=True)
class SandboxResourceLimits:
    """Immutable upper bounds for one isolated execution."""

    cpu_count: int = 2
    memory_bytes: int = 4 * 1024**3
    process_limit: int = 64
    temporary_storage_bytes: int = 1024**3
    wall_time_seconds: int = 600
    output_bytes: int = 10 * 1024**2

    def __post_init__(self) -> None:
        """Reject absent or non-positive resource limits."""
        for field in (
            "cpu_count",
            "memory_bytes",
            "process_limit",
            "temporary_storage_bytes",
            "wall_time_seconds",
            "output_bytes",
        ):
            _positive_int(getattr(self, field), field)


@dataclass(frozen=True, slots=True)
class SandboxExecutionManifest:
    """Attested I/O and outcome of one sandbox execution."""

    code_artifact_hash: ContentHash
    runtime_digest: ContentHash
    resource_limits: SandboxResourceLimits
    input_hash: ContentHash
    output_hash: ContentHash | None
    seed: int
    exit_status: SandboxExitStatus
    exit_code: int | None
    attestation_hash: ContentHash

    def __post_init__(self) -> None:
        """Require typed, internally consistent execution evidence."""
        for value, expected, field in (
            (self.code_artifact_hash, ContentHash, "code_artifact_hash"),
            (self.runtime_digest, ContentHash, "runtime_digest"),
            (self.resource_limits, SandboxResourceLimits, "resource_limits"),
            (self.input_hash, ContentHash, "input_hash"),
            (self.exit_status, SandboxExitStatus, "exit_status"),
            (self.attestation_hash, ContentHash, "attestation_hash"),
        ):
            if type(value) is not expected:
                raise _code_error(
                    f"{field} must be {expected.__name__}",
                    "invalid_sandbox_execution_manifest",
                    field=field,
                )
        if self.output_hash is not None and type(self.output_hash) is not ContentHash:
            raise _code_error(
                "output_hash must be ContentHash when present",
                "invalid_sandbox_execution_manifest",
                field="output_hash",
            )
        if type(self.seed) is not int or self.seed < 0:
            raise _code_error(
                "seed must be a non-negative integer",
                "invalid_sandbox_execution_manifest",
                field="seed",
            )
        if self.exit_code is not None and type(self.exit_code) is not int:
            raise _code_error(
                "exit_code must be int when present",
                "invalid_sandbox_execution_manifest",
                field="exit_code",
            )
        if self.exit_status is SandboxExitStatus.SUCCEEDED and (
            self.output_hash is None or self.exit_code != 0
        ):
            raise _code_error(
                "successful execution requires output_hash and zero exit_code",
                "invalid_sandbox_success_manifest",
            )
        if self.exit_status is not SandboxExitStatus.SUCCEEDED and self.exit_code == 0:
            raise _code_error(
                "non-success execution cannot have a zero exit_code",
                "invalid_sandbox_execution_manifest",
                field="exit_code",
            )
