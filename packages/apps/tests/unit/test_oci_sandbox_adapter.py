"""Offline contract tests for the hardened OCI candidate sandbox adapter."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import replace
from typing import cast

import orjson
import pytest
from ditto_analysis.experiments.generated_code import (
    ResearchCodeArtifact,
    SandboxExitStatus,
    SandboxResourceLimits,
    canonical_research_ast_hash,
)
from ditto_analysis.experiments.models import ContentHash, SnapshotId
from ditto_application.processes.experiments.candidate_sandbox_port import (
    FrozenSandboxArtifact,
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
    HardenedOciSandbox,
    OciSandboxApprovalVerifier,
    OciSandboxCommand,
    OciSandboxCommandRunner,
    OciSandboxProcessResult,
    OciSandboxRuntime,
    OciSandboxSettings,
    build_oci_sandbox,
)

IMAGE_DIGEST = ContentHash("1" * 64)
SBOM_HASH = ContentHash("2" * 64)
LOCK_HASH = ContentHash("3" * 64)
SECCOMP_HASH = ContentHash("4" * 64)
INPUT_SCHEMA_HASH = ContentHash("5" * 64)
OUTPUT_SCHEMA_HASH = ContentHash("6" * 64)
STATE_SCHEMA_HASH = ContentHash("7" * 64)
SOURCE = (
    "def fit(training_stream):\n"
    "    return {'mean': 0.0}\n"
    "def score(visible_window, immutable_model_state):\n"
    "    return []\n"
)


def _hash(value: bytes | str) -> ContentHash:
    raw = value.encode() if isinstance(value, str) else value
    return ContentHash(hashlib.sha256(raw).hexdigest())


def _code() -> ResearchCodeArtifact:
    return ResearchCodeArtifact(
        source_code=SOURCE,
        source_hash=_hash(SOURCE),
        canonical_ast_hash=canonical_research_ast_hash(SOURCE),
        dependency_lock_hash=LOCK_HASH,
        dependencies=("numpy==2.3.2", "polars==1.32.2"),
        image_digest=IMAGE_DIGEST,
        input_schema_hash=INPUT_SCHEMA_HASH,
        output_schema_hash=OUTPUT_SCHEMA_HASH,
    )


def _artifact(
    value: object,
    *,
    schema_hash: ContentHash,
    row_count: int,
) -> FrozenSandboxArtifact:
    return freeze_sandbox_artifact(
        orjson.dumps(value, option=orjson.OPT_SORT_KEYS),
        serialization=SandboxArtifactFormat.JSON,
        schema_hash=schema_hash,
        row_count=row_count,
    )


def _window() -> FrozenSandboxWindow:
    return FrozenSandboxWindow(
        artifact=_artifact(
            {
                "schema_id": "r5-visible-window",
                "schema_version": 1,
                "rows": [{"entity_id": "510300.SH", "value": 1.0}],
            },
            schema_hash=INPUT_SCHEMA_HASH,
            row_count=1,
        ),
        snapshot_id=SnapshotId("snapshot-r5-oci"),
        decision_time_epoch_us=1_700_000_000_000_000,
        knowledge_cutoff_epoch_us=1_700_000_000_000_000,
        publication_cutoff_epoch_us=1_699_999_000_000_000,
        score_keys=(
            SandboxScoreKey(
                entity_id="510300.SH",
                event_time_epoch_us=1_700_000_000_000_000,
                known_at_epoch_us=1_699_999_000_000_000,
                publication_time_epoch_us=1_699_998_000_000_000,
                execution_eligible_at_epoch_us=1_700_001_000_000_000,
            ),
        ),
    )


def _fit_request() -> SandboxFitRequest:
    return SandboxFitRequest(
        code_artifact=_code(),
        training_stream=_window(),
        resource_limits=SandboxResourceLimits(
            cpu_count=2,
            memory_bytes=512 * 1024**2,
            process_limit=32,
            temporary_storage_bytes=64 * 1024**2,
            wall_time_seconds=20,
            output_bytes=64 * 1024,
        ),
        seed=41,
    )


def _score_request() -> SandboxScoreRequest:
    fit = _fit_request()
    return SandboxScoreRequest(
        code_artifact=fit.code_artifact,
        visible_window=fit.training_stream,
        immutable_model_state=_artifact(
            {"schema_id": "r5-model-state", "mean": 0.0},
            schema_hash=STATE_SCHEMA_HASH,
            row_count=1,
        ),
        resource_limits=fit.resource_limits,
        seed=fit.seed,
    )


def _settings(**changes: object) -> OciSandboxSettings:
    settings = OciSandboxSettings(
        sandbox_enabled=True,
        a3_approved=True,
        approval_id="approval-a3-test-only",
        approval_scope_hash=ContentHash("8" * 64),
        runtime=OciSandboxRuntime.DOCKER_DESKTOP_VM,
        runtime_version="docker-29.4.0",
        image_repository="registry.invalid/ditto/research-sandbox",
        image_digest=IMAGE_DIGEST,
        sbom_hash=SBOM_HASH,
        dependency_lock_hash=LOCK_HASH,
        approved_dependencies=("numpy==2.3.2", "polars==1.32.2"),
        seccomp_profile_path="/etc/ditto/seccomp-r5.json",
        seccomp_profile_hash=SECCOMP_HASH,
    )
    return replace(settings, **changes)


def _output_envelope(artifact: FrozenSandboxArtifact) -> bytes:
    return orjson.dumps(
        {
            "schema_id": "r5-oci-sandbox-output",
            "schema_version": 1,
            "serialization": artifact.serialization.value,
            "schema_hash": str(artifact.schema_hash),
            "row_count": artifact.row_count,
            "payload_base64": base64.b64encode(artifact.payload).decode("ascii"),
        },
        option=orjson.OPT_SORT_KEYS,
    )


class _RecordingRunner(OciSandboxCommandRunner):
    def __init__(self, *results: OciSandboxProcessResult) -> None:
        self.results = list(results)
        self.commands: list[OciSandboxCommand] = []

    def run(self, command: OciSandboxCommand) -> OciSandboxProcessResult:
        self.commands.append(command)
        if not self.results:
            raise AssertionError("fake OCI runner script exhausted")
        return self.results.pop(0)


class _ApprovalVerifier(OciSandboxApprovalVerifier):
    def __init__(self, *, accepted: bool = True) -> None:
        self.accepted = accepted
        self.calls: list[tuple[str, ContentHash]] = []

    def verify(self, *, approval_id: str, evidence_hash: ContentHash) -> None:
        self.calls.append((approval_id, evidence_hash))
        if not self.accepted:
            raise ValueError("Approval A3 evidence is not currently valid")


def _build(
    settings: OciSandboxSettings,
    *,
    runner: OciSandboxCommandRunner,
    verifier: OciSandboxApprovalVerifier | None = None,
) -> HardenedOciSandbox:
    return build_oci_sandbox(
        settings,
        runner=runner,
        approval_verifier=verifier or _ApprovalVerifier(),
    )


def _successful_process(artifact: FrozenSandboxArtifact) -> OciSandboxProcessResult:
    return OciSandboxProcessResult(
        exit_code=0,
        stdout=_output_envelope(artifact),
        stderr=b"",
    )


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        (OciSandboxSettings(), "disabled"),
        (replace(_settings(), a3_approved=False), "Approval A3"),
        (replace(_settings(), approval_id=None), "approval_id"),
        (replace(_settings(), sbom_hash=None), "sbom_hash"),
        (replace(_settings(), seccomp_profile_hash=None), "seccomp_profile_hash"),
    ],
)
def test_oci_provider_fails_before_runner_without_complete_a3_evidence(
    settings: OciSandboxSettings,
    message: str,
) -> None:
    runner = _RecordingRunner()

    with pytest.raises(ValueError, match=message):
        build_oci_sandbox(settings, runner=runner)

    assert runner.commands == []


def test_complete_settings_still_require_trusted_a3_verifier_before_runner() -> None:
    runner = _RecordingRunner()

    with pytest.raises(ValueError, match="approval verifier"):
        build_oci_sandbox(_settings(), runner=runner)

    verifier = _ApprovalVerifier(accepted=False)
    with pytest.raises(ValueError, match="not currently valid"):
        build_oci_sandbox(
            _settings(),
            runner=runner,
            approval_verifier=verifier,
        )

    assert verifier.calls == [
        ("approval-a3-test-only", _settings().evidence_hash),
    ]
    assert runner.commands == []


def test_a3_revocation_is_rechecked_immediately_before_each_runner_call() -> None:
    runner = _RecordingRunner()
    verifier = _ApprovalVerifier()
    sandbox = _build(_settings(), runner=runner, verifier=verifier)
    verifier.accepted = False

    with pytest.raises(ValueError, match="not currently valid"):
        sandbox.fit(_fit_request())

    assert verifier.calls == [
        ("approval-a3-test-only", _settings().evidence_hash),
        ("approval-a3-test-only", _settings().evidence_hash),
    ]
    assert runner.commands == []


def test_hardened_command_has_exact_denials_and_no_host_or_secret_surface() -> None:
    output = _artifact(
        {"schema_id": "r5-model-state", "mean": 0.0},
        schema_hash=STATE_SCHEMA_HASH,
        row_count=1,
    )
    runner = _RecordingRunner(_successful_process(output))
    sandbox = _build(_settings(), runner=runner)

    result = sandbox.fit(_fit_request())

    assert result.output == output
    command = runner.commands[0]
    assert command.environment == ()
    assert command.timeout_seconds == 20
    assert command.stdout_limit_bytes > 64 * 1024
    assert command.stderr_limit_bytes <= 64 * 1024
    assert "--pull=never" in command.argv
    assert "--network=none" in command.argv
    assert "--user=65532:65532" in command.argv
    assert "--read-only" in command.argv
    assert "--cap-drop=ALL" in command.argv
    assert "--security-opt=no-new-privileges=true" in command.argv
    assert "--security-opt=seccomp=/etc/ditto/seccomp-r5.json" in command.argv
    assert "--pids-limit=32" in command.argv
    assert "--memory=536870912" in command.argv
    assert "--cpus=2" in command.argv
    assert "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=67108864" in command.argv
    joined = " ".join(command.argv)
    assert "@sha256:" + str(IMAGE_DIGEST) in joined
    assert "latest" not in joined
    assert "--volume" not in command.argv
    assert "--mount" not in command.argv
    assert "--env" not in command.argv
    assert "--env-file" not in command.argv
    assert "/var/run/docker.sock" not in joined
    assert "/Users/chevy/Desktop/code/ditto" not in joined
    assert "pip install" not in joined


@pytest.mark.parametrize(
    "runtime",
    [OciSandboxRuntime.ROOTLESS_DOCKER, OciSandboxRuntime.GVISOR_RUNSC],
)
def test_linux_runtime_profile_is_explicit_and_gvisor_selects_runsc(
    runtime: OciSandboxRuntime,
) -> None:
    output = _artifact(
        {"schema_id": "r5-model-state"},
        schema_hash=STATE_SCHEMA_HASH,
        row_count=1,
    )
    runner = _RecordingRunner(_successful_process(output))
    sandbox = _build(_settings(runtime=runtime), runner=runner)

    sandbox.fit(_fit_request())

    argv = runner.commands[0].argv
    assert ("--runtime=runsc" in argv) is (runtime is OciSandboxRuntime.GVISOR_RUNSC)


@pytest.mark.parametrize(
    ("candidate_request", "settings", "message"),
    [
        (
            _fit_request(),
            _settings(image_digest=ContentHash("9" * 64)),
            "image digest",
        ),
        (
            _fit_request(),
            _settings(dependency_lock_hash=ContentHash("a" * 64)),
            "dependency lock",
        ),
        (
            _fit_request(),
            _settings(approved_dependencies=("numpy==2.3.2",)),
            "approved dependencies",
        ),
    ],
)
def test_unapproved_image_or_dependency_drift_fails_before_runner(
    candidate_request: SandboxFitRequest,
    settings: OciSandboxSettings,
    message: str,
) -> None:
    runner = _RecordingRunner()
    sandbox = _build(settings, runner=runner)

    with pytest.raises(ValueError, match=message):
        sandbox.fit(candidate_request)

    assert runner.commands == []


def test_fit_and_score_encode_distinct_fixed_contract_phases() -> None:
    state = _artifact(
        {"schema_id": "r5-model-state", "mean": 0.0},
        schema_hash=STATE_SCHEMA_HASH,
        row_count=1,
    )
    score = _artifact(
        {
            "schema_id": "r5-candidate-score-frame",
            "schema_version": 1,
            "rows": [
                {
                    "entity_id": "510300.SH",
                    "event_time_epoch_us": 1_700_000_000_000_000,
                    "score": 0.5,
                }
            ],
        },
        schema_hash=OUTPUT_SCHEMA_HASH,
        row_count=1,
    )
    runner = _RecordingRunner(_successful_process(state), _successful_process(score))
    sandbox = _build(_settings(), runner=runner)

    fit_result = sandbox.fit(_fit_request())
    score_result = sandbox.score(_score_request())

    assert fit_result.manifest.exit_status is SandboxExitStatus.SUCCEEDED
    assert score_result.manifest.exit_status is SandboxExitStatus.SUCCEEDED
    fit_input = orjson.loads(runner.commands[0].stdin)
    score_input = orjson.loads(runner.commands[1].stdin)
    assert fit_input["phase"] == "fit"
    assert score_input["phase"] == "score"
    assert "immutable_model_state" not in fit_input
    assert score_input["immutable_model_state"]["content_hash"] == str(
        _score_request().immutable_model_state.content_hash
    )
    assert fit_input["security_evidence_hash"] == str(_settings().evidence_hash)


@pytest.mark.parametrize(
    ("attack", "process", "expected_status"),
    [
        (
            "network",
            OciSandboxProcessResult(
                exit_code=126,
                stdout=b"",
                stderr=b"network denied",
                policy_rejected=True,
            ),
            SandboxExitStatus.REJECTED,
        ),
        (
            "socket",
            OciSandboxProcessResult(
                exit_code=126, stdout=b"", stderr=b"socket denied", policy_rejected=True
            ),
            SandboxExitStatus.REJECTED,
        ),
        (
            "docker_socket",
            OciSandboxProcessResult(
                exit_code=126, stdout=b"", stderr=b"mount absent", policy_rejected=True
            ),
            SandboxExitStatus.REJECTED,
        ),
        (
            "host_mount",
            OciSandboxProcessResult(
                exit_code=126, stdout=b"", stderr=b"mount absent", policy_rejected=True
            ),
            SandboxExitStatus.REJECTED,
        ),
        (
            "secret",
            OciSandboxProcessResult(
                exit_code=126, stdout=b"", stderr=b"env absent", policy_rejected=True
            ),
            SandboxExitStatus.REJECTED,
        ),
        (
            "root",
            OciSandboxProcessResult(
                exit_code=126, stdout=b"", stderr=b"non-root", policy_rejected=True
            ),
            SandboxExitStatus.REJECTED,
        ),
        (
            "write_rootfs",
            OciSandboxProcessResult(
                exit_code=126, stdout=b"", stderr=b"read-only", policy_rejected=True
            ),
            SandboxExitStatus.REJECTED,
        ),
        (
            "fork_bomb",
            OciSandboxProcessResult(
                exit_code=137,
                stdout=b"",
                stderr=b"pid limit",
                resource_exhausted=True,
            ),
            SandboxExitStatus.RESOURCE_EXHAUSTED,
        ),
        (
            "oom",
            OciSandboxProcessResult(
                exit_code=137,
                stdout=b"",
                stderr=b"memory limit",
                resource_exhausted=True,
            ),
            SandboxExitStatus.RESOURCE_EXHAUSTED,
        ),
        (
            "timeout",
            OciSandboxProcessResult(
                exit_code=124, stdout=b"", stderr=b"timeout", timed_out=True
            ),
            SandboxExitStatus.TIMED_OUT,
        ),
    ],
)
def test_fake_attack_harness_records_failed_attested_manifest(
    attack: str,
    process: OciSandboxProcessResult,
    expected_status: SandboxExitStatus,
) -> None:
    runner = _RecordingRunner(process)
    sandbox = _build(_settings(), runner=runner)

    result = sandbox.fit(_fit_request())

    assert isinstance(sandbox, HardenedOciSandbox)
    assert result.manifest.exit_status is expected_status, attack
    assert result.manifest.exit_code != 0
    assert result.manifest.attestation_hash == sandbox_manifest_attestation_hash(
        result.manifest
    )
    assert result.output.row_count == 0


def test_oversize_decoded_output_is_resource_exhausted() -> None:
    candidate_request = _fit_request()
    output = freeze_sandbox_artifact(
        b"x" * (candidate_request.resource_limits.output_bytes + 1),
        serialization=SandboxArtifactFormat.JSON,
        schema_hash=STATE_SCHEMA_HASH,
        row_count=1,
    )
    runner = _RecordingRunner(_successful_process(output))

    result = _build(_settings(), runner=runner).fit(candidate_request)

    assert result.manifest.exit_status is SandboxExitStatus.RESOURCE_EXHAUSTED
    assert result.manifest.exit_code != 0


def test_output_limit_applies_to_decoded_artifact_not_base64_envelope() -> None:
    candidate_request = _fit_request()
    output = freeze_sandbox_artifact(
        b"x" * candidate_request.resource_limits.output_bytes,
        serialization=SandboxArtifactFormat.JSON,
        schema_hash=STATE_SCHEMA_HASH,
        row_count=1,
    )
    runner = _RecordingRunner(_successful_process(output))

    result = _build(_settings(), runner=runner).fit(candidate_request)

    assert result.manifest.exit_status is SandboxExitStatus.SUCCEEDED
    assert result.output == output
    assert runner.commands[0].stdout_limit_bytes > len(output.payload)


def test_malformed_success_output_is_failed_with_manifest_not_trusted_bytes() -> None:
    runner = _RecordingRunner(
        OciSandboxProcessResult(exit_code=0, stdout=b"not-json", stderr=b"")
    )

    result = _build(_settings(), runner=runner).fit(_fit_request())

    assert isinstance(result, SandboxExecutionResult)
    assert result.manifest.exit_status is SandboxExitStatus.FAILED
    assert result.output.row_count == 0
    assert result.manifest.attestation_hash == sandbox_manifest_attestation_hash(
        result.manifest
    )


def test_invalid_runner_result_type_is_failed_with_manifest() -> None:
    class _InvalidRunner(OciSandboxCommandRunner):
        def run(self, command: OciSandboxCommand) -> OciSandboxProcessResult:
            del command
            return cast(OciSandboxProcessResult, object())

    result = _build(_settings(), runner=_InvalidRunner()).fit(_fit_request())

    assert result.manifest.exit_status is SandboxExitStatus.FAILED
    assert result.output.row_count == 0


def test_invalid_artifact_metadata_is_failed_with_manifest() -> None:
    output = _artifact(
        {"schema_id": "r5-model-state"},
        schema_hash=STATE_SCHEMA_HASH,
        row_count=1,
    )
    envelope = cast("dict[str, object]", orjson.loads(_output_envelope(output)))
    envelope["row_count"] = -1
    runner = _RecordingRunner(
        OciSandboxProcessResult(
            exit_code=0,
            stdout=orjson.dumps(envelope, option=orjson.OPT_SORT_KEYS),
            stderr=b"",
        )
    )

    result = _build(_settings(), runner=runner).fit(_fit_request())

    assert result.manifest.exit_status is SandboxExitStatus.FAILED
    assert result.output.row_count == 0


def test_runner_result_and_settings_are_deeply_frozen() -> None:
    settings = _settings(approved_dependencies=["numpy==2.3.2", "polars==1.32.2"])
    process = OciSandboxProcessResult(exit_code=0, stdout=bytearray(b"{}"), stderr=b"")

    assert settings.approved_dependencies == ("numpy==2.3.2", "polars==1.32.2")
    assert isinstance(process.stdout, bytes)
    assert cast(bytes, process.stdout) == b"{}"
