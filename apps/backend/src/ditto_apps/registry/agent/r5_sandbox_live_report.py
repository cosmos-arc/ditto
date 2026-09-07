"""Authenticate physical OCI sandbox acceptance reports for the R5 gate."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast

import orjson
from ditto_analysis.experiments.generated_code import (
    SandboxExecutionManifest,
    SandboxExitStatus,
    SandboxResourceLimits,
)
from ditto_analysis.experiments.models import ContentHash
from ditto_application.processes.experiments.candidate_sandbox_port import (
    sandbox_manifest_attestation_hash,
)

from ditto_apps.registry.agent.oci_sandbox import (
    OciSandboxRuntime,
    OciSandboxSettings,
)

__all__ = [
    "SandboxLiveReportContract",
    "canonical_bytes",
    "finalize_report",
    "sha256_digest",
    "validate_live_report",
    "verify_report",
]

_SHA256_HEX_LENGTH = 64


@dataclass(frozen=True, slots=True)
class SandboxLiveReportContract:
    """Exact approved facts required to authenticate one live report."""

    approval_id: str
    runtime: Mapping[str, object]
    runtime_version: str
    approved_dependencies: tuple[str, ...]
    controls: Mapping[str, object]
    attack_expectations: tuple[tuple[str, SandboxExitStatus, bool], ...]
    concurrency_case_count: int


def canonical_bytes(value: object) -> bytes:
    """Encode one report value using its canonical JSON representation."""
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS)


def sha256_digest(value: bytes) -> str:
    """Return the canonical lowercase digest for evidence bytes."""
    return hashlib.sha256(value).hexdigest()


def finalize_report(draft: Mapping[str, object]) -> dict[str, object]:
    """Return a canonical report whose hash excludes only the hash field itself."""
    report = dict(draft)
    report.pop("report_hash", None)
    report["report_hash"] = sha256_digest(canonical_bytes(report))
    return report


def verify_report(report: Mapping[str, object]) -> bool:
    """Verify the self-authenticating report hash without trusting field order."""
    expected = report.get("report_hash")
    if type(expected) is not str:
        return False
    unsigned = dict(report)
    unsigned.pop("report_hash", None)
    return expected == sha256_digest(canonical_bytes(unsigned))


def _typed_mapping(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    return cast("Mapping[str, object]", value)


def _typed_sequence(value: object) -> tuple[object, ...] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    return tuple(cast("Sequence[object]", value))


def _is_hash(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == _SHA256_HEX_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _validated_manifest(
    value: object,
    *,
    runtime_digest: str,
    expected_status: SandboxExitStatus | None = None,
) -> SandboxExecutionManifest | None:
    mapping = _typed_mapping(value)
    if mapping is None or set(mapping) != {
        "attestation_hash",
        "code_artifact_hash",
        "exit_code",
        "exit_status",
        "input_hash",
        "output_hash",
        "resource_limits",
        "runtime_digest",
        "seed",
    }:
        return None
    limits = _typed_mapping(mapping.get("resource_limits"))
    if limits is None or set(limits) != {
        "cpu_count",
        "memory_bytes",
        "output_bytes",
        "process_limit",
        "temporary_storage_bytes",
        "wall_time_seconds",
    }:
        return None
    try:
        status = SandboxExitStatus(cast(str, mapping["exit_status"]))
        manifest = SandboxExecutionManifest(
            code_artifact_hash=ContentHash(cast(str, mapping["code_artifact_hash"])),
            runtime_digest=ContentHash(cast(str, mapping["runtime_digest"])),
            resource_limits=SandboxResourceLimits(
                cpu_count=cast(int, limits["cpu_count"]),
                memory_bytes=cast(int, limits["memory_bytes"]),
                process_limit=cast(int, limits["process_limit"]),
                temporary_storage_bytes=cast(int, limits["temporary_storage_bytes"]),
                wall_time_seconds=cast(int, limits["wall_time_seconds"]),
                output_bytes=cast(int, limits["output_bytes"]),
            ),
            input_hash=ContentHash(cast(str, mapping["input_hash"])),
            output_hash=(
                None
                if mapping["output_hash"] is None
                else ContentHash(cast(str, mapping["output_hash"]))
            ),
            seed=cast(int, mapping["seed"]),
            exit_status=status,
            exit_code=cast(int | None, mapping["exit_code"]),
            attestation_hash=ContentHash(cast(str, mapping["attestation_hash"])),
        )
    except (KeyError, TypeError, ValueError):
        return None
    if (
        str(manifest.runtime_digest) != runtime_digest
        or manifest.attestation_hash != sandbox_manifest_attestation_hash(manifest)
        or (expected_status is not None and manifest.exit_status is not expected_status)
    ):
        return None
    return manifest


def _valid_attack_results(
    report: Mapping[str, object],
    *,
    digest: str,
    contract: SandboxLiveReportContract,
) -> bool:
    values = _typed_sequence(report.get("attack_results"))
    if values is None or len(values) != len(contract.attack_expectations):
        return False
    for value, (name, status, require_observation) in zip(
        values, contract.attack_expectations, strict=True
    ):
        case = _typed_mapping(value)
        if case is None or set(case) != {
            "expected_status",
            "manifest",
            "name",
            "observation",
            "passed",
        }:
            return False
        observation = _typed_mapping(case.get("observation"))
        if (
            case.get("name") != name
            or case.get("expected_status") != status.value
            or case.get("passed") is not True
            or _validated_manifest(
                case.get("manifest"),
                runtime_digest=digest,
                expected_status=status,
            )
            is None
            or (
                require_observation
                and (observation is None or observation.get("blocked") is not True)
            )
            or (not require_observation and case.get("observation") is not None)
        ):
            return False
    return True


def _valid_auxiliary_checks(
    report: Mapping[str, object],
    *,
    digest: str,
    contract: SandboxLiveReportContract,
) -> bool:
    fresh = _typed_mapping(report.get("fresh_container_check"))
    concurrency = _typed_mapping(report.get("concurrency_check"))
    fit_score = _typed_mapping(report.get("fit_score_check"))
    if fresh is None or concurrency is None or fit_score is None:
        return False
    second = _typed_mapping(fresh.get("second_observation"))
    concurrent_manifests = _typed_sequence(concurrency.get("manifests"))
    score_observation = _typed_mapping(fit_score.get("score_observation"))
    return (
        set(fresh)
        == {"first_manifest", "passed", "second_manifest", "second_observation"}
        and fresh.get("passed") is True
        and second is not None
        and second.get("blocked") is True
        and _validated_manifest(
            fresh.get("first_manifest"),
            runtime_digest=digest,
            expected_status=SandboxExitStatus.SUCCEEDED,
        )
        is not None
        and _validated_manifest(
            fresh.get("second_manifest"),
            runtime_digest=digest,
            expected_status=SandboxExitStatus.SUCCEEDED,
        )
        is not None
        and set(concurrency) == {"manifests", "passed"}
        and concurrency.get("passed") is True
        and concurrent_manifests is not None
        and len(concurrent_manifests) == contract.concurrency_case_count
        and all(
            _validated_manifest(
                manifest,
                runtime_digest=digest,
                expected_status=SandboxExitStatus.SUCCEEDED,
            )
            is not None
            for manifest in concurrent_manifests
        )
        and set(fit_score)
        == {"fit_manifest", "passed", "score_manifest", "score_observation"}
        and fit_score.get("passed") is True
        and score_observation is not None
        and score_observation.get("schema_id") == "r5-candidate-score-frame"
        and _validated_manifest(
            fit_score.get("fit_manifest"),
            runtime_digest=digest,
            expected_status=SandboxExitStatus.SUCCEEDED,
        )
        is not None
        and _validated_manifest(
            fit_score.get("score_manifest"),
            runtime_digest=digest,
            expected_status=SandboxExitStatus.SUCCEEDED,
        )
        is not None
    )


def _valid_security_evidence(
    report: Mapping[str, object], *, contract: SandboxLiveReportContract
) -> bool:
    try:
        settings = OciSandboxSettings(
            sandbox_enabled=True,
            a3_approved=True,
            approval_id=cast(str, report["approval_id"]),
            approval_scope_hash=ContentHash(cast(str, report["approval_scope_hash"])),
            runtime=OciSandboxRuntime.ORBSTACK_VM,
            runtime_version=cast(str, report["runtime_version"]),
            image_repository=cast(str, report["image_repository"]),
            image_digest=ContentHash(cast(str, report["image_digest"])),
            sbom_hash=ContentHash(cast(str, report["sbom_hash"])),
            dependency_lock_hash=ContentHash(cast(str, report["dependency_lock_hash"])),
            approved_dependencies=contract.approved_dependencies,
            seccomp_profile_path=cast(str, report["seccomp_profile_path"]),
            seccomp_profile_hash=ContentHash(cast(str, report["seccomp_profile_hash"])),
        )
    except (KeyError, TypeError, ValueError):
        return False
    return str(settings.evidence_hash) == report.get("security_evidence_hash")


def validate_live_report(
    report: Mapping[str, object], *, contract: SandboxLiveReportContract
) -> bool:
    """Recompute report, approval, and every execution attestation fail closed."""
    expected_fields = {
        "approval_id",
        "approval_scope",
        "approval_scope_hash",
        "attack_case_count",
        "attack_results",
        "captured_at",
        "concurrency_check",
        "containers_remaining",
        "dependency_lock_hash",
        "fit_score_check",
        "fresh_container_check",
        "image_digest",
        "image_manifest_hash",
        "image_repository",
        "profile",
        "provider",
        "release_gate_passed",
        "report_hash",
        "runtime",
        "runtime_version",
        "sbom_hash",
        "schema_id",
        "schema_version",
        "seccomp_profile_hash",
        "seccomp_profile_path",
        "security_evidence_hash",
        "status",
        "suite",
    }
    scope = _typed_mapping(report.get("approval_scope"))
    containers = _typed_sequence(report.get("containers_remaining"))
    digest = report.get("image_digest")
    try:
        captured = datetime.fromisoformat(cast(str, report.get("captured_at")))
    except (TypeError, ValueError):
        return False
    if (
        set(report) != expected_fields
        or not verify_report(report)
        or report.get("schema_id") != "r5-sandbox-live-acceptance"
        or report.get("schema_version") != 1
        or report.get("suite") != "sandbox_live"
        or report.get("provider") != "oci"
        or report.get("profile") != "orbstack_vm"
        or report.get("status") != "passed"
        or report.get("release_gate_passed") is not True
        or report.get("approval_id") != contract.approval_id
        or report.get("runtime") != contract.runtime
        or report.get("runtime_version") != contract.runtime_version
        or report.get("image_repository") != "127.0.0.1:55000/ditto/r5-research-sandbox"
        or type(digest) is not str
        or any(
            not _is_hash(report.get(field_name))
            for field_name in (
                "approval_scope_hash",
                "dependency_lock_hash",
                "image_digest",
                "image_manifest_hash",
                "sbom_hash",
                "seccomp_profile_hash",
                "security_evidence_hash",
            )
        )
        or captured.tzinfo is None
        or scope is None
        or report.get("approval_scope_hash") != sha256_digest(canonical_bytes(scope))
        or scope.get("approval_id") != contract.approval_id
        or scope.get("image_repository") != report.get("image_repository")
        or scope.get("approved_dependencies") != list(contract.approved_dependencies)
        or scope.get("runtime") != report.get("runtime")
        or scope.get("runtime_version") != report.get("runtime_version")
        or scope.get("image_digest") != digest
        or scope.get("sbom_hash") != report.get("sbom_hash")
        or scope.get("dependency_lock_hash") != report.get("dependency_lock_hash")
        or scope.get("seccomp_profile_hash") != report.get("seccomp_profile_hash")
        or scope.get("seccomp_profile_path") != report.get("seccomp_profile_path")
        or scope.get("controls") != contract.controls
        or scope.get("kubernetes") is not False
        or report.get("attack_case_count") != len(contract.attack_expectations)
        or containers != ()
        or not _valid_security_evidence(report, contract=contract)
    ):
        return False
    return _valid_attack_results(
        report, digest=digest, contract=contract
    ) and _valid_auxiliary_checks(report, digest=digest, contract=contract)
