"""Run and authenticate the Approval A3 OrbStack sandbox acceptance suite."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import textwrap
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import orjson
from ditto_analysis.experiments.generated_code import (
    ResearchCodeArtifact,
    SandboxExecutionManifest,
    SandboxExitStatus,
    SandboxResourceLimits,
    canonical_research_ast_hash,
    validate_research_code_contract,
)
from ditto_analysis.experiments.models import ContentHash, SnapshotId
from ditto_application.processes.experiments.candidate_sandbox_port import (
    CandidateSandboxPort,
    FrozenSandboxWindow,
    SandboxArtifactFormat,
    SandboxExecutionResult,
    SandboxFitRequest,
    SandboxScoreKey,
    SandboxScoreRequest,
    freeze_sandbox_artifact,
    sandbox_manifest_attestation_hash,
)

from ditto_apps.registry.agent.oci_sandbox import (
    OciSandboxApprovalVerifier,
    OciSandboxRuntime,
    OciSandboxSettings,
    build_oci_sandbox,
)
from ditto_apps.registry.agent.oci_sandbox_runner import (
    DockerCliOciCommandRunner,
    DockerRuntimeProfile,
)
from ditto_apps.registry.agent.r5_sandbox_live_report import (
    SandboxLiveReportContract,
    finalize_report,
    verify_report,
)
from ditto_apps.registry.agent.r5_sandbox_live_report import (
    canonical_bytes as _canonical,
)
from ditto_apps.registry.agent.r5_sandbox_live_report import (
    sha256_digest as _sha256,
)
from ditto_apps.registry.agent.r5_sandbox_live_report import (
    validate_live_report as _validate_live_report,
)
from ditto_apps.scripts.r5_sandbox_supply_chain import verify_image_manifest

__all__ = [
    "finalize_report",
    "main",
    "run_live_acceptance",
    "validate_live_report",
    "verify_report",
]

_APPROVAL_ID = "A3-2026-08-17-orbstack-2.2.1-arm64-v2"
_SHA256_HEX_LENGTH = 64
_CONCURRENCY_CASE_COUNT = 2
_DEPENDENCIES = ("numpy==2.3.2", "polars==1.32.2")
_INPUT_SCHEMA_HASH = ContentHash(hashlib.sha256(b"r5-a3-live-input-v1").hexdigest())
_OUTPUT_SCHEMA_HASH = ContentHash(hashlib.sha256(b"r5-a3-live-output-v1").hexdigest())
_RUNTIME = DockerRuntimeProfile(
    context="orbstack",
    server_version="29.4.0",
    operating_system="OrbStack",
    architecture="aarch64",
    kernel_version="7.0.14-orbstack-00380-ga7e0a2dc9535",
    cgroup_driver="cgroupfs",
    security_options=("name=seccomp,profile=builtin", "name=cgroupns"),
    runtimes=("io.containerd.runc.v2", "runc"),
)
_RUNTIME_VERSION = (
    "orbstack=2.2.1;docker-server=29.4.0;runc=1.5.1;"
    "kernel=7.0.14-orbstack-00380-ga7e0a2dc9535"
)
_DEFAULT_LIMITS = SandboxResourceLimits(
    cpu_count=1,
    memory_bytes=128 * 1024**2,
    process_limit=16,
    temporary_storage_bytes=16 * 1024**2,
    wall_time_seconds=5,
    output_bytes=16 * 1024,
)
_ATTACK_EXPECTATIONS = (
    ("network", SandboxExitStatus.SUCCEEDED, True),
    ("socket", SandboxExitStatus.SUCCEEDED, True),
    ("docker_socket", SandboxExitStatus.SUCCEEDED, True),
    ("host_mount", SandboxExitStatus.SUCCEEDED, True),
    ("secret", SandboxExitStatus.SUCCEEDED, True),
    ("root", SandboxExitStatus.SUCCEEDED, True),
    ("write_rootfs", SandboxExitStatus.SUCCEEDED, True),
    ("fork_bomb", SandboxExitStatus.SUCCEEDED, True),
    ("oom", SandboxExitStatus.RESOURCE_EXHAUSTED, False),
    ("timeout", SandboxExitStatus.TIMED_OUT, False),
    ("oversize_output", SandboxExitStatus.RESOURCE_EXHAUSTED, False),
)
_CONTROLS = {
    "network": "none",
    "ipc": "none",
    "uid_gid": "65532:65532",
    "rootfs": "read-only",
    "tmpfs": "rw,noexec,nosuid,nodev,bounded",
    "capabilities": "drop-all",
    "no_new_privileges": True,
    "seccomp": "default-deny-custom-aarch64",
    "pull": "never",
    "mounts": "none",
    "environment": "none-from-host",
    "resources": "per-invocation-cpu-memory-pids-tmpfs-wall-output",
}
_REPORT_CONTRACT = SandboxLiveReportContract(
    approval_id=_APPROVAL_ID,
    runtime=_RUNTIME.to_payload(),
    runtime_version=_RUNTIME_VERSION,
    approved_dependencies=_DEPENDENCIES,
    controls=_CONTROLS,
    attack_expectations=_ATTACK_EXPECTATIONS,
    concurrency_case_count=_CONCURRENCY_CASE_COUNT,
)


def validate_live_report(report: Mapping[str, object]) -> bool:
    """Authenticate one live report against the exact approved A3 contract."""
    return _validate_live_report(report, contract=_REPORT_CONTRACT)


@dataclass(frozen=True, slots=True)
class _AttackCase:
    name: str
    source: str
    limits: SandboxResourceLimits = _DEFAULT_LIMITS
    expected_status: SandboxExitStatus = SandboxExitStatus.SUCCEEDED
    require_blocked_observation: bool = True


class _ExactApprovalVerifier(OciSandboxApprovalVerifier):
    def __init__(self, *, approval_id: str, evidence_hash: ContentHash) -> None:
        self._approval_id = approval_id
        self._evidence_hash = evidence_hash

    def verify(self, *, approval_id: str, evidence_hash: ContentHash) -> None:
        if approval_id != self._approval_id or evidence_hash != self._evidence_hash:
            raise ValueError("Approval A3 evidence does not match the accepted scope")


def _approval_scope(
    *, manifest: Mapping[str, object], seccomp_path: Path
) -> dict[str, object]:
    return {
        "schema_id": "r5-oci-sandbox-a3-scope",
        "schema_version": 1,
        "approval_id": _APPROVAL_ID,
        "approval_basis": "workspace-user-explicit-start-and-acceptance-authorization",
        "runtime": _RUNTIME.to_payload(),
        "runtime_version": _RUNTIME_VERSION,
        "image_repository": manifest["image_repository"],
        "image_digest": manifest["image_digest"],
        "sbom_hash": manifest["sbom_hash"],
        "dependency_lock_hash": cast("Mapping[str, object]", manifest["artifacts"])[
            "requirements.lock"
        ],
        "approved_dependencies": list(_DEPENDENCIES),
        "seccomp_profile_path": str(seccomp_path),
        "seccomp_profile_hash": _sha256(seccomp_path.read_bytes()),
        "controls": _CONTROLS,
        "kubernetes": False,
        "gvisor": False,
        "gvisor_reason": "runsc is unavailable on the approved macOS runtime",
    }


def _settings(
    *, manifest: Mapping[str, object], seccomp_path: Path, scope_hash: ContentHash
) -> OciSandboxSettings:
    artifacts = cast("Mapping[str, object]", manifest["artifacts"])
    return OciSandboxSettings(
        sandbox_enabled=True,
        a3_approved=True,
        approval_id=_APPROVAL_ID,
        approval_scope_hash=scope_hash,
        runtime=OciSandboxRuntime.ORBSTACK_VM,
        runtime_version=_RUNTIME_VERSION,
        image_repository=cast(str, manifest["image_repository"]),
        image_digest=ContentHash(cast(str, manifest["image_digest"])),
        sbom_hash=ContentHash(cast(str, manifest["sbom_hash"])),
        dependency_lock_hash=ContentHash(cast(str, artifacts["requirements.lock"])),
        approved_dependencies=_DEPENDENCIES,
        seccomp_profile_path=str(seccomp_path),
        seccomp_profile_hash=ContentHash(_sha256(seccomp_path.read_bytes())),
    )


def _window() -> FrozenSandboxWindow:
    artifact = freeze_sandbox_artifact(
        _canonical(
            {
                "schema_id": "r5-a3-visible-window",
                "schema_version": 1,
                "rows": [{"entity_id": "510300.SH", "value": 1.0}],
            }
        ),
        serialization=SandboxArtifactFormat.JSON,
        schema_hash=_INPUT_SCHEMA_HASH,
        row_count=1,
    )
    return FrozenSandboxWindow(
        artifact=artifact,
        snapshot_id=SnapshotId("snapshot-r5-a3-live"),
        decision_time_epoch_us=1_700_000_000_000_000,
        knowledge_cutoff_epoch_us=1_699_999_000_000_000,
        publication_cutoff_epoch_us=1_699_998_000_000_000,
        score_keys=(
            SandboxScoreKey(
                entity_id="510300.SH",
                event_time_epoch_us=1_699_997_000_000_000,
                known_at_epoch_us=1_699_998_000_000_000,
                publication_time_epoch_us=1_699_997_000_000_000,
                execution_eligible_at_epoch_us=1_700_001_000_000_000,
            ),
        ),
    )


def _code(source: str, *, settings: OciSandboxSettings) -> ResearchCodeArtifact:
    if settings.image_digest is None or settings.dependency_lock_hash is None:
        raise ValueError("sandbox code requires an approved immutable image and lock")
    artifact = ResearchCodeArtifact(
        source_code=source,
        source_hash=ContentHash(_sha256(source.encode("utf-8"))),
        canonical_ast_hash=canonical_research_ast_hash(source),
        dependency_lock_hash=settings.dependency_lock_hash,
        dependencies=_DEPENDENCIES,
        image_digest=settings.image_digest,
        input_schema_hash=_INPUT_SCHEMA_HASH,
        output_schema_hash=_OUTPUT_SCHEMA_HASH,
    )
    validate_research_code_contract(artifact)
    return artifact


def _fit_request(
    source: str,
    *,
    settings: OciSandboxSettings,
    limits: SandboxResourceLimits = _DEFAULT_LIMITS,
    seed: int = 41,
) -> SandboxFitRequest:
    return SandboxFitRequest(
        code_artifact=_code(source, settings=settings),
        training_stream=_window(),
        resource_limits=limits,
        seed=seed,
    )


def _manifest_payload(manifest: SandboxExecutionManifest) -> dict[str, object]:
    return {
        "code_artifact_hash": str(manifest.code_artifact_hash),
        "runtime_digest": str(manifest.runtime_digest),
        "resource_limits": asdict(manifest.resource_limits),
        "input_hash": str(manifest.input_hash),
        "output_hash": (
            None if manifest.output_hash is None else str(manifest.output_hash)
        ),
        "seed": manifest.seed,
        "exit_status": manifest.exit_status.value,
        "exit_code": manifest.exit_code,
        "attestation_hash": str(manifest.attestation_hash),
    }


def _observation(result: SandboxExecutionResult) -> object:
    if result.manifest.exit_status is not SandboxExitStatus.SUCCEEDED:
        return None
    return orjson.loads(result.output.payload)


def _attack_result(
    case: _AttackCase,
    result: SandboxExecutionResult,
) -> dict[str, object]:
    observed = _observation(result)
    attested = result.manifest.attestation_hash == sandbox_manifest_attestation_hash(
        result.manifest
    )
    observation_passed = True
    if case.require_blocked_observation:
        mapping = (
            cast("Mapping[str, object]", observed)
            if isinstance(observed, Mapping)
            else None
        )
        observation_passed = mapping is not None and mapping.get("blocked") is True
    passed = (
        result.manifest.exit_status is case.expected_status
        and attested
        and observation_passed
    )
    return {
        "name": case.name,
        "passed": passed,
        "expected_status": case.expected_status.value,
        "observation": observed,
        "manifest": _manifest_payload(result.manifest),
    }


def _attack_cases() -> tuple[_AttackCase, ...]:
    return (
        _AttackCase(
            "network",
            textwrap.dedent("""
                import socket
                def fit(training_stream):
                    try:
                        socket.create_connection(('1.1.1.1', 53), timeout=0.2)
                    except OSError as exc:
                        return {'blocked': True, 'error': type(exc).__name__}
                    return {'blocked': False}
                def score(visible_window, immutable_model_state):
                    return []
                """).lstrip(),
        ),
        _AttackCase(
            "socket",
            textwrap.dedent("""
                import socket
                def fit(training_stream):
                    try:
                        handle = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    except OSError as exc:
                        return {'blocked': True, 'error': type(exc).__name__}
                    handle.close()
                    return {'blocked': False}
                def score(visible_window, immutable_model_state):
                    return []
                """).lstrip(),
        ),
        _AttackCase(
            "docker_socket",
            textwrap.dedent("""
                import os
                def fit(training_stream):
                    paths = ('/var/run/docker.sock', '/run/docker.sock')
                    return {'blocked': not any(os.path.exists(path) for path in paths)}
                def score(visible_window, immutable_model_state):
                    return []
                """).lstrip(),
        ),
        _AttackCase(
            "host_mount",
            textwrap.dedent("""
                import os
                def fit(training_stream):
                    paths = ('/workspace', '/repo', '/host', '/mnt/host')
                    return {'blocked': not any(os.path.exists(path) for path in paths)}
                def score(visible_window, immutable_model_state):
                    return []
                """).lstrip(),
        ),
        _AttackCase(
            "secret",
            textwrap.dedent("""
                import os
                def fit(training_stream):
                    names = (
                        'OPENAI_API_KEY',
                        'ZHIPUAI_API_KEY',
                        'DITTO_AGENT_GLM_VALIDATION_API_KEY',
                    )
                    leaked = [name for name in names if name in os.environ]
                    return {'blocked': not leaked, 'leaked_names': leaked}
                def score(visible_window, immutable_model_state):
                    return []
                """).lstrip(),
        ),
        _AttackCase(
            "root",
            textwrap.dedent("""
                import os
                def fit(training_stream):
                    return {
                        'blocked': os.getuid() == 65532 and os.getgid() == 65532,
                        'uid': os.getuid(),
                        'gid': os.getgid(),
                    }
                def score(visible_window, immutable_model_state):
                    return []
                """).lstrip(),
        ),
        _AttackCase(
            "write_rootfs",
            textwrap.dedent("""
                def fit(training_stream):
                    try:
                        with open('/opt/ditto/a3-write-probe', 'wb') as stream:
                            stream.write(b'x')
                    except OSError as exc:
                        return {'blocked': True, 'error': type(exc).__name__}
                    return {'blocked': False}
                def score(visible_window, immutable_model_state):
                    return []
                """).lstrip(),
        ),
        _AttackCase(
            "fork_bomb",
            textwrap.dedent("""
                import subprocess
                import sys
                def fit(training_stream):
                    children = []
                    blocked = False
                    try:
                        for _ in range(64):
                            child = subprocess.Popen([
                                sys.executable,
                                '-c',
                                'import time;time.sleep(10)',
                            ])
                            children.append(child)
                    except OSError:
                        blocked = True
                    finally:
                        for child in children:
                            child.terminate()
                        for child in children:
                            child.wait(timeout=2)
                    return {
                        'blocked': blocked and len(children) < 16,
                        'created': len(children),
                    }
                def score(visible_window, immutable_model_state):
                    return []
                """).lstrip(),
        ),
        _AttackCase(
            "oom",
            textwrap.dedent("""
                def fit(training_stream):
                    chunks = []
                    while True:
                        chunks.append(bytearray(8 * 1024 * 1024))
                def score(visible_window, immutable_model_state):
                    return []
                """).lstrip(),
            limits=SandboxResourceLimits(
                cpu_count=1,
                memory_bytes=64 * 1024**2,
                process_limit=16,
                temporary_storage_bytes=16 * 1024**2,
                wall_time_seconds=8,
                output_bytes=16 * 1024,
            ),
            expected_status=SandboxExitStatus.RESOURCE_EXHAUSTED,
            require_blocked_observation=False,
        ),
        _AttackCase(
            "timeout",
            textwrap.dedent("""
                def fit(training_stream):
                    while True:
                        pass
                def score(visible_window, immutable_model_state):
                    return []
                """).lstrip(),
            limits=SandboxResourceLimits(
                cpu_count=1,
                memory_bytes=128 * 1024**2,
                process_limit=16,
                temporary_storage_bytes=16 * 1024**2,
                wall_time_seconds=2,
                output_bytes=16 * 1024,
            ),
            expected_status=SandboxExitStatus.TIMED_OUT,
            require_blocked_observation=False,
        ),
        _AttackCase(
            "oversize_output",
            textwrap.dedent("""
                def fit(training_stream):
                    return {'blob': 'x' * (128 * 1024)}
                def score(visible_window, immutable_model_state):
                    return []
                """).lstrip(),
            limits=SandboxResourceLimits(
                cpu_count=1,
                memory_bytes=128 * 1024**2,
                process_limit=16,
                temporary_storage_bytes=16 * 1024**2,
                wall_time_seconds=5,
                output_bytes=8 * 1024,
            ),
            expected_status=SandboxExitStatus.RESOURCE_EXHAUSTED,
            require_blocked_observation=False,
        ),
    )


def _docker_containers(
    *, docker_binary: Path, image_reference: str, home: Path
) -> list[str]:
    process = subprocess.run(  # noqa: S603 - exact trusted binary, no shell.
        (
            str(docker_binary),
            "--context=orbstack",
            "ps",
            "--all",
            f"--filter=ancestor={image_reference}",
            "--format={{.ID}}",
        ),
        capture_output=True,
        env={
            "DOCKER_CONFIG": str(home / ".docker"),
            "HOME": str(home),
            "LANG": "C",
            "LC_ALL": "C",
        },
        timeout=10,
        check=False,
    )
    if process.returncode != 0 or len(process.stdout) > 64 * 1024:
        raise RuntimeError("Docker cleanup inventory is unavailable")
    return sorted(filter(None, process.stdout.decode("ascii").splitlines()))


def _fresh_container_check(
    *, sandbox: CandidateSandboxPort, settings: OciSandboxSettings
) -> dict[str, object]:
    writer = textwrap.dedent("""
        def fit(training_stream):
            with open(
                '/tmp/ditto-a3-fresh-marker',
                'w',
                encoding='ascii',
            ) as stream:
                stream.write('first')
            return {'marker_written': True}
        def score(visible_window, immutable_model_state):
            return []
        """).lstrip()
    reader = textwrap.dedent("""
        import os
        def fit(training_stream):
            return {
                'blocked': not os.path.exists('/tmp/ditto-a3-fresh-marker'),
            }
        def score(visible_window, immutable_model_state):
            return []
        """).lstrip()
    first = sandbox.fit(_fit_request(writer, settings=settings, seed=51))
    second = sandbox.fit(_fit_request(reader, settings=settings, seed=52))
    observation = _observation(second)
    observation_mapping = (
        cast("Mapping[str, object]", observation)
        if isinstance(observation, Mapping)
        else None
    )
    passed = (
        first.manifest.exit_status is SandboxExitStatus.SUCCEEDED
        and second.manifest.exit_status is SandboxExitStatus.SUCCEEDED
        and observation_mapping is not None
        and observation_mapping.get("blocked") is True
    )
    return {
        "passed": passed,
        "first_manifest": _manifest_payload(first.manifest),
        "second_manifest": _manifest_payload(second.manifest),
        "second_observation": observation,
    }


def _concurrency_check(
    *, sandbox: CandidateSandboxPort, settings: OciSandboxSettings
) -> dict[str, object]:
    source = textwrap.dedent("""
        def fit(training_stream):
            return {'blocked': True, 'rows': len(training_stream)}
        def score(visible_window, immutable_model_state):
            return []
        """).lstrip()
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                sandbox.fit,
                _fit_request(source, settings=settings, seed=seed),
            )
            for seed in (61, 62)
        ]
        results = [future.result(timeout=15) for future in futures]
    passed = all(
        result.manifest.exit_status is SandboxExitStatus.SUCCEEDED
        and result.manifest.attestation_hash
        == sandbox_manifest_attestation_hash(result.manifest)
        for result in results
    )
    return {
        "passed": passed,
        "manifests": [_manifest_payload(result.manifest) for result in results],
    }


def _fit_score_check(
    *, sandbox: CandidateSandboxPort, settings: OciSandboxSettings
) -> dict[str, object]:
    source = textwrap.dedent("""
        def fit(training_stream):
            return {'schema_id': 'r5-a3-state', 'mean': 1.0}
        def score(visible_window, immutable_model_state):
            return [
                {
                    'entity_id': row['entity_id'],
                    'score': immutable_model_state['mean'],
                }
                for row in visible_window
            ]
        """).lstrip()
    fit_request = _fit_request(source, settings=settings, seed=71)
    fit = sandbox.fit(fit_request)
    score_request = SandboxScoreRequest(
        code_artifact=fit_request.code_artifact,
        visible_window=fit_request.training_stream,
        immutable_model_state=fit.output,
        resource_limits=fit_request.resource_limits,
        seed=fit_request.seed,
    )
    score = sandbox.score(score_request)
    score_observation = _observation(score)
    score_mapping = (
        cast("Mapping[str, object]", score_observation)
        if isinstance(score_observation, Mapping)
        else None
    )
    passed = (
        fit.manifest.exit_status is SandboxExitStatus.SUCCEEDED
        and score.manifest.exit_status is SandboxExitStatus.SUCCEEDED
        and score_mapping is not None
        and score_mapping.get("schema_id") == "r5-candidate-score-frame"
    )
    return {
        "passed": passed,
        "fit_manifest": _manifest_payload(fit.manifest),
        "score_manifest": _manifest_payload(score.manifest),
        "score_observation": score_observation,
    }


def run_live_acceptance(*, repo_root: Path) -> dict[str, object]:
    """Run the exact approved image/profile against every physical attack case."""
    root = repo_root.resolve(strict=True)
    image_root = root / "deploy" / "agent-sandbox"
    manifest = verify_image_manifest(
        repo_root=root,
        approved_dependencies=_DEPENDENCIES,
    )
    seccomp_path = (image_root / "seccomp.json").resolve(strict=True)
    scope = _approval_scope(manifest=manifest, seccomp_path=seccomp_path)
    scope_hash = ContentHash(_sha256(_canonical(scope)))
    settings = _settings(
        manifest=manifest,
        seccomp_path=seccomp_path,
        scope_hash=scope_hash,
    )
    verifier = _ExactApprovalVerifier(
        approval_id=_APPROVAL_ID,
        evidence_hash=settings.evidence_hash,
    )
    docker_binary = Path(
        os.path.abspath(  # noqa: PTH100 - preserve approved OrbStack symlink path.
            "/usr/local/bin/docker"
        )
    )
    home = Path.home().resolve(strict=True)
    runner = DockerCliOciCommandRunner(
        docker_binary=docker_binary,
        runtime_profile=_RUNTIME,
        home_directory=home,
        seccomp_profile_path=seccomp_path,
        seccomp_profile_hash=ContentHash(_sha256(seccomp_path.read_bytes())),
    )
    sandbox = build_oci_sandbox(
        settings,
        runner=runner,
        approval_verifier=verifier,
    )
    attack_results = [
        _attack_result(
            case,
            sandbox.fit(
                _fit_request(
                    case.source,
                    settings=settings,
                    limits=case.limits,
                    seed=100 + index,
                )
            ),
        )
        for index, case in enumerate(_attack_cases())
    ]
    fresh = _fresh_container_check(sandbox=sandbox, settings=settings)
    concurrency = _concurrency_check(sandbox=sandbox, settings=settings)
    fit_score = _fit_score_check(sandbox=sandbox, settings=settings)
    image_reference = (
        f"{manifest['image_repository']}@sha256:{manifest['image_digest']}"
    )
    containers = _docker_containers(
        docker_binary=docker_binary,
        image_reference=image_reference,
        home=home,
    )
    passed = (
        all(result["passed"] is True for result in attack_results)
        and fresh["passed"] is True
        and concurrency["passed"] is True
        and fit_score["passed"] is True
        and not containers
    )
    draft: dict[str, object] = {
        "schema_id": "r5-sandbox-live-acceptance",
        "schema_version": 1,
        "captured_at": datetime.now(UTC).isoformat(),
        "suite": "sandbox_live",
        "provider": "oci",
        "profile": "orbstack_vm",
        "approval_id": _APPROVAL_ID,
        "approval_scope": scope,
        "approval_scope_hash": str(scope_hash),
        "security_evidence_hash": str(settings.evidence_hash),
        "runtime": _RUNTIME.to_payload(),
        "runtime_version": _RUNTIME_VERSION,
        "image_repository": manifest["image_repository"],
        "image_digest": manifest["image_digest"],
        "image_manifest_hash": _sha256(
            (image_root / "image-manifest.json").read_bytes()
        ),
        "sbom_hash": manifest["sbom_hash"],
        "dependency_lock_hash": cast("Mapping[str, object]", manifest["artifacts"])[
            "requirements.lock"
        ],
        "seccomp_profile_path": str(seccomp_path),
        "seccomp_profile_hash": _sha256(seccomp_path.read_bytes()),
        "attack_case_count": len(attack_results),
        "attack_results": attack_results,
        "fresh_container_check": fresh,
        "concurrency_check": concurrency,
        "fit_score_check": fit_score,
        "containers_remaining": containers,
        "status": "passed" if passed else "failed",
        "release_gate_passed": passed,
    }
    return finalize_report(draft)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the suite and atomically replace the requested evidence file."""
    args = _parser().parse_args(argv)
    report = run_live_acceptance(repo_root=args.repo_root)
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_bytes(
        orjson.dumps(
            report,
            option=orjson.OPT_SORT_KEYS | orjson.OPT_APPEND_NEWLINE,
        )
    )
    temporary.replace(output)
    return 0 if report["release_gate_passed"] is True else 5


if __name__ == "__main__":
    raise SystemExit(main())
