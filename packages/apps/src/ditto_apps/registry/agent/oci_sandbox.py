"""
Approval-gated OCI command contract for generated research candidates.

This module intentionally has no subprocess or daemon implementation while Approval A3
is pending. A physical command runner must be injected by the composition root.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Protocol, cast

import orjson
from ditto_analysis.experiments.generated_code import (
    ResearchCodeArtifact,
    SandboxExecutionManifest,
    SandboxExitStatus,
    SandboxResourceLimits,
)
from ditto_analysis.experiments.models import ContentHash
from ditto_analysis.experiments.persistence import canonical_payload
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.candidate_sandbox_port import (
    CandidateSandboxPort,
    FrozenSandboxArtifact,
    FrozenSandboxWindow,
    SandboxArtifactFormat,
    SandboxExecutionResult,
    SandboxFitRequest,
    SandboxScoreRequest,
    build_successful_sandbox_result,
    freeze_sandbox_artifact,
    sandbox_manifest_attestation_hash,
)

__all__ = [
    "HardenedOciSandbox",
    "OciSandboxApprovalVerifier",
    "OciSandboxCommand",
    "OciSandboxCommandRunner",
    "OciSandboxProcessResult",
    "OciSandboxRuntime",
    "OciSandboxSettings",
    "build_oci_sandbox",
]

_SANDBOX_UID = 65532
_ENVELOPE_OVERHEAD_BYTES = 4096
_ERROR_SCHEMA_HASH = ContentHash(
    hashlib.sha256(b"r5-oci-sandbox-host-error-v1").hexdigest()
)
_OUTPUT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "serialization",
        "schema_hash",
        "row_count",
        "payload_base64",
    }
)


def _normalized(value: str, *, field: str) -> str:
    if not value or value != value.strip() or "\x00" in value:
        raise ValueError(f"OCI sandbox {field} must be non-empty and normalized")
    return value


def _optional_normalized(value: str | None, *, field: str) -> str | None:
    return None if value is None else _normalized(value, field=field)


def _freeze_dependencies(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError("OCI sandbox approved dependencies must be a sequence")
    raw = tuple(cast("Sequence[object]", value))
    if not raw or any(
        type(item) is not str or item != item.strip() or "==" not in item or not item
        for item in raw
    ):
        raise ValueError("OCI sandbox approved dependencies must be exactly pinned")
    typed = cast("tuple[str, ...]", raw)
    if len(set(typed)) != len(typed):
        raise ValueError("OCI sandbox approved dependencies cannot contain duplicates")
    return tuple(sorted(typed))


class OciSandboxRuntime(StrEnum):
    """Approved host isolation profile, never inferred from the local daemon."""

    DOCKER_DESKTOP_VM = "docker_desktop_vm"
    ROOTLESS_DOCKER = "rootless_docker"
    GVISOR_RUNSC = "gvisor_runsc"


@dataclass(frozen=True, slots=True)
class OciSandboxSettings:
    """Apps-owned A3 evidence and immutable runtime profile selection."""

    sandbox_enabled: bool = False
    a3_approved: bool = False
    approval_id: str | None = None
    approval_scope_hash: ContentHash | None = None
    runtime: OciSandboxRuntime = OciSandboxRuntime.DOCKER_DESKTOP_VM
    runtime_version: str | None = None
    image_repository: str | None = None
    image_digest: ContentHash | None = None
    sbom_hash: ContentHash | None = None
    dependency_lock_hash: ContentHash | None = None
    approved_dependencies: Sequence[str] = ()
    seccomp_profile_path: str | None = None
    seccomp_profile_hash: ContentHash | None = None

    def __post_init__(self) -> None:
        """Normalize inert configuration without treating it as approval."""
        if type(self.sandbox_enabled) is not bool or type(self.a3_approved) is not bool:
            raise ValueError("OCI sandbox feature and approval flags must be boolean")
        if type(self.runtime) is not OciSandboxRuntime:
            raise ValueError("OCI sandbox runtime profile is invalid")
        for field in ("approval_scope_hash", "image_digest", "sbom_hash"):
            value = getattr(self, field)
            if value is not None and type(value) is not ContentHash:
                raise ValueError(f"OCI sandbox {field} must be ContentHash")
        for field in ("dependency_lock_hash", "seccomp_profile_hash"):
            value = getattr(self, field)
            if value is not None and type(value) is not ContentHash:
                raise ValueError(f"OCI sandbox {field} must be ContentHash")
        for field in (
            "approval_id",
            "runtime_version",
            "image_repository",
            "seccomp_profile_path",
        ):
            object.__setattr__(
                self,
                field,
                _optional_normalized(getattr(self, field), field=field),
            )
        dependencies = (
            ()
            if not self.approved_dependencies
            else _freeze_dependencies(cast("object", self.approved_dependencies))
        )
        object.__setattr__(self, "approved_dependencies", dependencies)

    @property
    def evidence_hash(self) -> ContentHash:
        """Bind every runtime, image, dependency, and security approval field."""
        profile = _approved_profile(self)
        return canonical_payload(
            {
                "schema_id": "r5-oci-sandbox-security-evidence",
                "schema_version": 1,
                "approval_id": profile.approval_id,
                "approval_scope_hash": str(profile.approval_scope_hash),
                "runtime": profile.runtime.value,
                "runtime_version": profile.runtime_version,
                "image_repository": profile.image_repository,
                "image_digest": str(profile.image_digest),
                "sbom_hash": str(profile.sbom_hash),
                "dependency_lock_hash": str(profile.dependency_lock_hash),
                "approved_dependencies": list(profile.approved_dependencies),
                "seccomp_profile_path": profile.seccomp_profile_path,
                "seccomp_profile_hash": str(profile.seccomp_profile_hash),
            }
        ).content_hash


@dataclass(frozen=True, slots=True)
class _ApprovedOciProfile:
    approval_id: str
    approval_scope_hash: ContentHash
    runtime: OciSandboxRuntime
    runtime_version: str
    image_repository: str
    image_digest: ContentHash
    sbom_hash: ContentHash
    dependency_lock_hash: ContentHash
    approved_dependencies: tuple[str, ...]
    seccomp_profile_path: str
    seccomp_profile_hash: ContentHash


def _required_text(value: str | None, *, field: str) -> str:
    if value is None:
        raise ValueError(f"OCI sandbox requires {field} in Approval A3 evidence")
    return value


def _required_hash(value: ContentHash | None, *, field: str) -> ContentHash:
    if value is None:
        raise ValueError(f"OCI sandbox requires {field} in Approval A3 evidence")
    return value


def _approved_profile(settings: OciSandboxSettings) -> _ApprovedOciProfile:
    if type(settings) is not OciSandboxSettings:
        raise ValueError("OCI sandbox settings are invalid")
    if not settings.sandbox_enabled:
        raise ValueError("OCI sandbox is disabled")
    if not settings.a3_approved:
        raise ValueError("OCI sandbox requires Approval A3 evidence")
    repository = _required_text(settings.image_repository, field="image_repository")
    leaf = repository.rsplit("/", maxsplit=1)[-1]
    if "@" in repository or ":" in leaf or repository.endswith("/"):
        raise ValueError("OCI sandbox image_repository cannot contain a tag or digest")
    seccomp_path = _required_text(
        settings.seccomp_profile_path, field="seccomp_profile_path"
    )
    if not PurePosixPath(seccomp_path).is_absolute():
        raise ValueError("OCI sandbox seccomp_profile_path must be absolute")
    dependencies = tuple(settings.approved_dependencies)
    if not dependencies:
        raise ValueError("OCI sandbox requires approved dependencies")
    return _ApprovedOciProfile(
        approval_id=_required_text(settings.approval_id, field="approval_id"),
        approval_scope_hash=_required_hash(
            settings.approval_scope_hash, field="approval_scope_hash"
        ),
        runtime=settings.runtime,
        runtime_version=_required_text(
            settings.runtime_version, field="runtime_version"
        ),
        image_repository=repository,
        image_digest=_required_hash(settings.image_digest, field="image_digest"),
        sbom_hash=_required_hash(settings.sbom_hash, field="sbom_hash"),
        dependency_lock_hash=_required_hash(
            settings.dependency_lock_hash, field="dependency_lock_hash"
        ),
        approved_dependencies=dependencies,
        seccomp_profile_path=seccomp_path,
        seccomp_profile_hash=_required_hash(
            settings.seccomp_profile_hash, field="seccomp_profile_hash"
        ),
    )


@dataclass(frozen=True, slots=True)
class OciSandboxCommand:
    """Shell-free command and bounded byte streams handed to a physical runner."""

    argv: Sequence[str]
    stdin: bytes
    environment: Sequence[tuple[str, str]]
    timeout_seconds: int
    stdout_limit_bytes: int
    stderr_limit_bytes: int
    security_evidence_hash: ContentHash

    def __post_init__(self) -> None:
        """Deep-freeze the command and forbid inherited environment state."""
        argv = tuple(self.argv)
        environment = tuple(self.environment)
        if not argv or any(type(item) is not str or not item for item in argv):
            raise ValueError("OCI sandbox argv is invalid")
        if environment:
            raise ValueError("OCI sandbox command cannot inherit environment variables")
        if not isinstance(cast("object", self.stdin), bytes):
            raise ValueError("OCI sandbox stdin must be bytes")
        for value in (
            self.timeout_seconds,
            self.stdout_limit_bytes,
            self.stderr_limit_bytes,
        ):
            if type(value) is not int or value <= 0:
                raise ValueError("OCI sandbox command limits must be positive integers")
        if type(self.security_evidence_hash) is not ContentHash:
            raise ValueError("OCI sandbox security evidence hash is invalid")
        object.__setattr__(self, "argv", argv)
        object.__setattr__(self, "stdin", bytes(self.stdin))
        object.__setattr__(self, "environment", environment)


@dataclass(frozen=True, slots=True)
class OciSandboxProcessResult:
    """Bounded result returned by an injected OCI process runner."""

    exit_code: int | None
    stdout: bytes | bytearray
    stderr: bytes | bytearray
    timed_out: bool = False
    resource_exhausted: bool = False
    policy_rejected: bool = False

    def __post_init__(self) -> None:
        """Copy streams and reject ambiguous process metadata."""
        if self.exit_code is not None and type(self.exit_code) is not int:
            raise ValueError("OCI sandbox exit_code must be int or None")
        if not isinstance(
            cast("object", self.stdout), (bytes, bytearray)
        ) or not isinstance(
            cast("object", self.stderr),
            (bytes, bytearray),
        ):
            raise ValueError("OCI sandbox process streams must be bytes")
        for value in (self.timed_out, self.resource_exhausted, self.policy_rejected):
            if type(value) is not bool:
                raise ValueError("OCI sandbox process flags must be boolean")
        object.__setattr__(self, "stdout", bytes(self.stdout))
        object.__setattr__(self, "stderr", bytes(self.stderr))


class OciSandboxCommandRunner(Protocol):
    """Injected physical boundary; no default daemon implementation exists."""

    def run(self, command: OciSandboxCommand) -> OciSandboxProcessResult:
        """Execute one already-hardened command without a shell."""
        ...


class OciSandboxApprovalVerifier(Protocol):
    """Trusted Apps seam that verifies one exact, current A3 approval record."""

    def verify(self, *, approval_id: str, evidence_hash: ContentHash) -> None:
        """Raise unless the exact security evidence is currently approved."""
        ...


def _artifact_payload(artifact: FrozenSandboxArtifact) -> dict[str, object]:
    return {
        "serialization": artifact.serialization.value,
        "content_hash": str(artifact.content_hash),
        "schema_hash": str(artifact.schema_hash),
        "row_count": artifact.row_count,
        "allow_pickle": artifact.allow_pickle,
        "payload_base64": base64.b64encode(artifact.payload).decode("ascii"),
    }


def _window_payload(window: FrozenSandboxWindow) -> dict[str, object]:
    return {
        "artifact": _artifact_payload(window.artifact),
        "snapshot_id": str(window.snapshot_id),
        "knowledge_cutoff_epoch_us": window.knowledge_cutoff_epoch_us,
        "score_keys": [
            {
                "entity_id": key.entity_id,
                "event_time_epoch_us": key.event_time_epoch_us,
                "known_at_epoch_us": key.known_at_epoch_us,
            }
            for key in window.score_keys
        ],
    }


def _code_payload(code: ResearchCodeArtifact) -> dict[str, object]:
    return {
        "source_code": code.source_code,
        "source_hash": str(code.source_hash),
        "canonical_ast_hash": str(code.canonical_ast_hash),
        "dependency_lock_hash": str(code.dependency_lock_hash),
        "dependencies": list(code.dependencies),
        "image_digest": str(code.image_digest),
        "input_schema_hash": str(code.input_schema_hash),
        "output_schema_hash": str(code.output_schema_hash),
    }


def _request_payload(
    request: SandboxFitRequest | SandboxScoreRequest,
    *,
    evidence_hash: ContentHash,
) -> bytes:
    if isinstance(request, SandboxFitRequest):
        phase = "fit"
        window = request.training_stream
        model_state = None
    else:
        phase = "score"
        window = request.visible_window
        model_state = _artifact_payload(request.immutable_model_state)
    payload: dict[str, object] = {
        "schema_id": "r5-oci-sandbox-input",
        "schema_version": 1,
        "phase": phase,
        "invocation_hash": str(request.input_hash),
        "security_evidence_hash": str(evidence_hash),
        "code_artifact": _code_payload(request.code_artifact),
        "window": _window_payload(window),
        "seed": request.seed,
    }
    if model_state is not None:
        payload["immutable_model_state"] = model_state
    return orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)


def _command_argv(
    profile: _ApprovedOciProfile,
    limits: SandboxResourceLimits,
    *,
    phase: str,
) -> tuple[str, ...]:
    argv = [
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--pull=never",
        "--network=none",
        "--ipc=none",
        f"--user={_SANDBOX_UID}:{_SANDBOX_UID}",
        "--read-only",
        f"--tmpfs=/tmp:rw,noexec,nosuid,nodev,size={limits.temporary_storage_bytes}",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges=true",
        f"--security-opt=seccomp={profile.seccomp_profile_path}",
        f"--pids-limit={limits.process_limit}",
        f"--memory={limits.memory_bytes}",
        f"--memory-swap={limits.memory_bytes}",
        f"--cpus={limits.cpu_count}",
        "--ulimit=nofile=64:64",
        "--stop-timeout=1",
        "--entrypoint=/opt/ditto/bin/candidate-runner",
    ]
    if profile.runtime is OciSandboxRuntime.GVISOR_RUNSC:
        argv.append("--runtime=runsc")
    argv.extend(
        [
            f"{profile.image_repository}@sha256:{profile.image_digest}",
            phase,
        ]
    )
    return tuple(argv)


def _failure_artifact(reason: str) -> FrozenSandboxArtifact:
    return freeze_sandbox_artifact(
        orjson.dumps(
            {
                "schema_id": "r5-oci-sandbox-host-error",
                "schema_version": 1,
                "reason": reason,
            },
            option=orjson.OPT_SORT_KEYS,
        ),
        serialization=SandboxArtifactFormat.JSON,
        schema_hash=_ERROR_SCHEMA_HASH,
        row_count=0,
    )


def _failed_result(
    request: SandboxFitRequest | SandboxScoreRequest,
    *,
    status: SandboxExitStatus,
    exit_code: int | None,
    reason: str,
) -> SandboxExecutionResult:
    normalized_exit_code = (
        exit_code
        if exit_code not in (None, 0)
        else {
            SandboxExitStatus.REJECTED: 126,
            SandboxExitStatus.FAILED: 125,
            SandboxExitStatus.TIMED_OUT: 124,
            SandboxExitStatus.RESOURCE_EXHAUSTED: 137,
        }[status]
    )
    output = _failure_artifact(reason)
    draft = SandboxExecutionManifest(
        code_artifact_hash=request.code_artifact.artifact_hash,
        runtime_digest=request.code_artifact.image_digest,
        resource_limits=request.resource_limits,
        input_hash=request.input_hash,
        output_hash=output.content_hash,
        seed=request.seed,
        exit_status=status,
        exit_code=normalized_exit_code,
        attestation_hash=ContentHash("0" * 64),
    )
    manifest = replace(
        draft,
        attestation_hash=sandbox_manifest_attestation_hash(draft),
    )
    return SandboxExecutionResult(output=output, manifest=manifest)


def _process_failure(
    request: SandboxFitRequest | SandboxScoreRequest,
    process: OciSandboxProcessResult,
) -> SandboxExecutionResult | None:
    if process.timed_out:
        return _failed_result(
            request,
            status=SandboxExitStatus.TIMED_OUT,
            exit_code=process.exit_code,
            reason="sandbox_wall_time_exceeded",
        )
    stdout_limit = _stdout_capture_limit(request.resource_limits.output_bytes)
    stderr_limit = min(request.resource_limits.output_bytes, 64 * 1024)
    if (
        process.resource_exhausted
        or len(process.stdout) > stdout_limit
        or len(process.stderr) > stderr_limit
    ):
        return _failed_result(
            request,
            status=SandboxExitStatus.RESOURCE_EXHAUSTED,
            exit_code=process.exit_code,
            reason="sandbox_resource_limit_exceeded",
        )
    if process.policy_rejected:
        return _failed_result(
            request,
            status=SandboxExitStatus.REJECTED,
            exit_code=process.exit_code,
            reason="sandbox_security_policy_rejected",
        )
    if process.exit_code != 0:
        return _failed_result(
            request,
            status=SandboxExitStatus.FAILED,
            exit_code=process.exit_code,
            reason="sandbox_process_failed",
        )
    return None


def _stdout_capture_limit(output_bytes: int) -> int:
    encoded_payload = 4 * ((output_bytes + 2) // 3)
    return encoded_payload + _ENVELOPE_OVERHEAD_BYTES


def _decode_output(payload: bytes, *, output_limit: int) -> FrozenSandboxArtifact:
    decoded: object = orjson.loads(payload)
    if not isinstance(decoded, Mapping):
        raise ValueError("OCI sandbox output envelope must be an object")
    mapping = cast("Mapping[str, object]", decoded)
    if frozenset(mapping) != _OUTPUT_FIELDS:
        raise ValueError("OCI sandbox output envelope fields are invalid")
    if (
        mapping["schema_id"] != "r5-oci-sandbox-output"
        or mapping["schema_version"] != 1
    ):
        raise ValueError("OCI sandbox output envelope schema is invalid")
    raw_serialization = mapping["serialization"]
    raw_schema_hash = mapping["schema_hash"]
    raw_row_count = mapping["row_count"]
    raw_base64 = mapping["payload_base64"]
    if (
        type(raw_serialization) is not str
        or type(raw_schema_hash) is not str
        or type(raw_row_count) is not int
        or type(raw_base64) is not str
    ):
        raise ValueError("OCI sandbox output envelope types are invalid")
    artifact_payload = base64.b64decode(raw_base64, validate=True)
    if len(artifact_payload) > output_limit:
        raise OverflowError("OCI sandbox decoded output exceeds its limit")
    return freeze_sandbox_artifact(
        artifact_payload,
        serialization=SandboxArtifactFormat(raw_serialization),
        schema_hash=ContentHash(raw_schema_hash),
        row_count=raw_row_count,
    )


def _result_from_process(
    request: SandboxFitRequest | SandboxScoreRequest,
    process: object,
) -> SandboxExecutionResult:
    if type(process) is not OciSandboxProcessResult:
        return _failed_result(
            request,
            status=SandboxExitStatus.FAILED,
            exit_code=125,
            reason="sandbox_runner_result_invalid",
        )
    failure = _process_failure(request, process)
    if failure is not None:
        return failure
    try:
        output = _decode_output(
            bytes(process.stdout),
            output_limit=request.resource_limits.output_bytes,
        )
    except OverflowError:
        return _failed_result(
            request,
            status=SandboxExitStatus.RESOURCE_EXHAUSTED,
            exit_code=137,
            reason="sandbox_output_size_exceeded",
        )
    except (AppProcessError, ValueError, TypeError, orjson.JSONDecodeError):
        return _failed_result(
            request,
            status=SandboxExitStatus.FAILED,
            exit_code=125,
            reason="sandbox_output_envelope_invalid",
        )
    return build_successful_sandbox_result(request, output)


class HardenedOciSandbox(CandidateSandboxPort):
    """Strict adapter over an injected runner and complete A3 evidence."""

    def __init__(
        self,
        *,
        profile: _ApprovedOciProfile,
        evidence_hash: ContentHash,
        approval_verifier: OciSandboxApprovalVerifier,
        runner: OciSandboxCommandRunner,
    ) -> None:
        self._profile = profile
        self._evidence_hash = evidence_hash
        self._approval_verifier = approval_verifier
        self._runner = runner

    def fit(self, request: SandboxFitRequest) -> SandboxExecutionResult:
        """Execute fixed-contract fit under the hardened profile."""
        if type(request) is not SandboxFitRequest:
            raise ValueError("OCI sandbox fit request is invalid")
        return self._execute(request)

    def score(self, request: SandboxScoreRequest) -> SandboxExecutionResult:
        """Execute fixed-contract score under the hardened profile."""
        if type(request) is not SandboxScoreRequest:
            raise ValueError("OCI sandbox score request is invalid")
        return self._execute(request)

    def _execute(
        self,
        request: SandboxFitRequest | SandboxScoreRequest,
    ) -> SandboxExecutionResult:
        self._validate_code(request.code_artifact)
        evidence_hash = self._evidence_hash
        self._approval_verifier.verify(
            approval_id=self._profile.approval_id,
            evidence_hash=evidence_hash,
        )
        stdin = _request_payload(request, evidence_hash=evidence_hash)
        if len(stdin) > request.resource_limits.temporary_storage_bytes:
            return _failed_result(
                request,
                status=SandboxExitStatus.RESOURCE_EXHAUSTED,
                exit_code=137,
                reason="sandbox_input_size_exceeded",
            )
        phase = "fit" if isinstance(request, SandboxFitRequest) else "score"
        command = OciSandboxCommand(
            argv=_command_argv(
                self._profile,
                request.resource_limits,
                phase=phase,
            ),
            stdin=stdin,
            environment=(),
            timeout_seconds=request.resource_limits.wall_time_seconds,
            stdout_limit_bytes=_stdout_capture_limit(
                request.resource_limits.output_bytes
            ),
            stderr_limit_bytes=min(request.resource_limits.output_bytes, 64 * 1024),
            security_evidence_hash=evidence_hash,
        )
        try:
            process = self._runner.run(command)
        except (OSError, RuntimeError) as exc:
            return _failed_result(
                request,
                status=SandboxExitStatus.FAILED,
                exit_code=125,
                reason=f"sandbox_runner_{type(exc).__name__}",
            )
        return _result_from_process(request, process)

    def _validate_code(self, code: ResearchCodeArtifact) -> None:
        if code.image_digest != self._profile.image_digest:
            raise ValueError("OCI sandbox image digest is outside Approval A3")
        if code.dependency_lock_hash != self._profile.dependency_lock_hash:
            raise ValueError("OCI sandbox dependency lock is outside Approval A3")
        if tuple(code.dependencies) != self._profile.approved_dependencies:
            raise ValueError("OCI sandbox approved dependencies do not match code")


def build_oci_sandbox(
    settings: OciSandboxSettings,
    *,
    runner: OciSandboxCommandRunner,
    approval_verifier: OciSandboxApprovalVerifier | None = None,
) -> HardenedOciSandbox:
    """Build no physical runner; validate A3 evidence before accepting injection."""
    profile = _approved_profile(settings)
    if approval_verifier is None:
        raise ValueError("OCI sandbox requires a trusted approval verifier")
    evidence_hash = settings.evidence_hash
    approval_verifier.verify(
        approval_id=profile.approval_id,
        evidence_hash=evidence_hash,
    )
    if not hasattr(runner, "run"):
        raise ValueError("OCI sandbox command runner is invalid")
    return HardenedOciSandbox(
        profile=profile,
        evidence_hash=evidence_hash,
        approval_verifier=approval_verifier,
        runner=runner,
    )
