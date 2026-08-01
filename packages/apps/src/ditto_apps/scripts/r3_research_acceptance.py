"""Deterministic R3 dual-golden engineering acceptance runner."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import orjson

__all__ = [
    "CommandResult",
    "CommandSpec",
    "R3AcceptanceReport",
    "deterministic_commands",
    "run_fixture_acceptance",
]

_REPO_ROOT = Path(__file__).resolve().parents[5]
_DEFAULT_OUTPUT = _REPO_ROOT / "artifacts" / "acceptance" / "r3-report.json"
_DEFAULT_MANIFEST = _REPO_ROOT / "docs" / "evidence" / "r3" / "manifest.json"
_OUTPUT_LIMIT = 12_000
_SCHEMA = "ditto.r3-research-acceptance"
_MANIFEST_SCHEMA = "ditto.r3-evidence-manifest"


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """One reproducible acceptance command and its durable file evidence."""

    name: str
    command: tuple[str, ...]
    artifact_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Bounded command transcript with hashes for every retained artifact."""

    name: str
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    passed: bool
    artifact_hashes: Mapping[str, str]

    @classmethod
    def from_capture(
        cls,
        *,
        name: str,
        command: tuple[str, ...],
        returncode: int,
        stdout: str,
        stderr: str,
    ) -> CommandResult:
        """Build a result whose transcript hash binds output and exit status."""
        bounded_stdout = stdout[-_OUTPUT_LIMIT:]
        bounded_stderr = stderr[-_OUTPUT_LIMIT:]
        transcript = orjson.dumps(
            {
                "command": command,
                "name": name,
                "returncode": returncode,
                "stderr": bounded_stderr,
                "stdout": bounded_stdout,
            },
            option=orjson.OPT_SORT_KEYS,
        )
        return cls(
            name=name,
            command=command,
            returncode=returncode,
            stdout=bounded_stdout,
            stderr=bounded_stderr,
            passed=returncode == 0,
            artifact_hashes={
                "command_transcript": hashlib.sha256(transcript).hexdigest()
            },
        )


@dataclass(frozen=True, slots=True)
class MutationGateEvidence:
    """Observed fail-closed mutation guarantees asserted by the E2E wrapper."""

    called: bool
    expected_error_code: str
    zero_write: bool
    active_pointer_unchanged: bool
    append_only_event_count_unchanged: bool


@dataclass(frozen=True, slots=True)
class GateEvidence:
    """Submit-review and publish/promotion hard-gate evidence."""

    publish_promotion: MutationGateEvidence
    submit_review: MutationGateEvidence


@dataclass(frozen=True, slots=True)
class R3AcceptanceReport:
    """Machine-readable engineering result that never upgrades live truth."""

    schema: str
    version: int
    generated_at: str
    source_commit: str
    mode: str
    passed: bool
    release_status: str
    r2_live_gate: str
    golden_lanes: tuple[str, ...]
    failures: tuple[str, ...]
    proves: tuple[str, ...]
    does_not_prove: tuple[str, ...]
    gate_evidence: GateEvidence
    commands: tuple[CommandResult, ...]


CommandRunner = Callable[[str, Sequence[str], Path], CommandResult]


def _pytest(*targets: str) -> tuple[str, ...]:
    return (
        "pixi",
        "run",
        "-e",
        "dev",
        "pytest",
        *targets,
        "-q",
        "--no-cov",
    )


def deterministic_commands() -> tuple[CommandSpec, ...]:
    """Return the frozen Task 17 deterministic acceptance command set."""
    governance_wrapper = "packages/apps/tests/e2e/test_r3_governance_recovery.py"
    backup_target = (
        f"{governance_wrapper}::test_fixture_backup_restore_preserves_domain_identity"
    )
    openapi_target = (
        "packages/apps/tests/unit/api/test_openapi_snapshot_unit.py::"
        + "test_static_openapi_matches_canonical_runtime_contract"
    )
    return (
        CommandSpec("backend-check", ("pixi", "run", "-e", "dev", "check")),
        CommandSpec(
            "stock-golden",
            _pytest("packages/apps/tests/e2e/test_r3_stock_selection_golden.py"),
        ),
        CommandSpec(
            "etf-golden",
            _pytest("packages/apps/tests/e2e/test_r3_etf_research_golden.py"),
        ),
        CommandSpec(
            "governance-recovery",
            _pytest(f"{governance_wrapper}::test_fixture_governance_recovery"),
        ),
        CommandSpec(
            "hard-gate-zero-write",
            _pytest(
                f"{governance_wrapper}::test_fixture_hard_gate_paths_are_zero_write"
            ),
        ),
        CommandSpec(
            "scheduler-literal-128",
            _pytest("packages/apps/tests/e2e/test_r3_scheduler_capacity.py"),
        ),
        CommandSpec(
            "isolated-backup-restore",
            _pytest(backup_target),
        ),
        CommandSpec(
            "openapi-zero-diff",
            _pytest(openapi_target),
            artifact_paths=("docs/openapi/v1.json",),
        ),
    )


def _subprocess_runner(
    name: str,
    command: Sequence[str],
    cwd: Path,
) -> CommandResult:
    completed = subprocess.run(  # noqa: S603 - frozen local command contract
        tuple(command),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    return CommandResult.from_capture(
        name=name,
        command=tuple(command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _run_command(
    spec: CommandSpec,
    *,
    command_runner: CommandRunner,
) -> CommandResult:
    result = command_runner(spec.name, spec.command, _REPO_ROOT)
    hashes = dict(result.artifact_hashes)
    for relative_path in spec.artifact_paths:
        artifact = _REPO_ROOT / relative_path
        if artifact.is_file():
            hashes[relative_path] = _hash_file(artifact)
    return replace(result, artifact_hashes=hashes)


def _source_commit() -> str:
    git_executable = shutil.which("git")
    if git_executable is None:
        raise RuntimeError("git executable is required for acceptance evidence")
    completed = subprocess.run(  # noqa: S603 - resolved git executable only
        (git_executable, "rev-parse", "HEAD"),
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _gate_evidence(results: Sequence[CommandResult]) -> GateEvidence:
    passed_by_name = {result.name: result.passed for result in results}
    verified = passed_by_name.get("hard-gate-zero-write", False)
    return GateEvidence(
        publish_promotion=MutationGateEvidence(
            called=verified,
            expected_error_code="hard_gate_blocked",
            zero_write=verified,
            active_pointer_unchanged=verified,
            append_only_event_count_unchanged=verified,
        ),
        submit_review=MutationGateEvidence(
            called=verified,
            expected_error_code="HARD_GATE_FAILED",
            zero_write=verified,
            active_pointer_unchanged=verified,
            append_only_event_count_unchanged=verified,
        ),
    )


def _canonical_json(value: object) -> bytes:
    options = orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS
    return orjson.dumps(value, option=options) + b"\n"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json(value))


def _relative_path(path: Path) -> str:
    return os.path.relpath(path.resolve(), start=_REPO_ROOT).replace(os.sep, "/")


def _write_manifest(
    *,
    manifest: Path,
    output: Path,
    generated_at: str,
    source_commit: str,
    invocation: str,
) -> None:
    _write_json(
        manifest,
        {
            "entries": [
                {
                    "command": invocation,
                    "generated_at": generated_at,
                    "mode": "deterministic_fixture",
                    "relative_path": _relative_path(output),
                    "sha256": _hash_file(output),
                    "source_commit": source_commit,
                }
            ],
            "schema": _MANIFEST_SCHEMA,
            "version": 1,
        },
    )


def run_fixture_acceptance(
    *,
    output: Path,
    manifest: Path,
    checked_at: datetime | None = None,
    source_commit: str | None = None,
    command_runner: CommandRunner = _subprocess_runner,
    invocation: str = (
        "pixi run -e dev python -m ditto_apps.scripts.r3_research_acceptance "
        "--fixture --output artifacts/acceptance/r3-report.json"
    ),
) -> R3AcceptanceReport:
    """Run deterministic seams and persist blocked release truth plus hashes."""
    now = checked_at or datetime.now(UTC)
    generated_at = now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    commit = source_commit or _source_commit()
    results = tuple(
        _run_command(spec, command_runner=command_runner)
        for spec in deterministic_commands()
    )
    failures = tuple(result.name for result in results if not result.passed)
    report = R3AcceptanceReport(
        schema=_SCHEMA,
        version=1,
        generated_at=generated_at,
        source_commit=commit,
        mode="deterministic_fixture",
        passed=not failures,
        release_status="RELEASE_ACCEPTANCE_BLOCKED",
        r2_live_gate="NOT_EVALUATED",
        golden_lanes=("stock", "etf"),
        failures=failures,
        proves=(
            "deterministic_stock_and_etf_evidence_closure",
            "submit_review_and_publish_promotion_fail_closed",
            "literal_128_candidate_scheduler_recovery",
            "isolated_metadata_research_artifact_backup_restore",
            "runtime_openapi_snapshot_zero_diff",
        ),
        does_not_prove=(
            "provider_entitlement",
            "certified_live_data",
            "live_96_month_history",
            "real_browser_acceptance",
            "production_recovery",
        ),
        gate_evidence=_gate_evidence(results),
        commands=results,
    )
    _write_json(output, asdict(report))
    _write_manifest(
        manifest=manifest,
        output=output,
        generated_at=generated_at,
        source_commit=commit,
        invocation=invocation,
    )
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", action="store_true", required=True)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run fixture engineering acceptance without upgrading live status."""
    args = _parser().parse_args(argv)
    output = args.output
    manifest = args.manifest
    if not isinstance(output, Path) or not isinstance(manifest, Path):
        raise TypeError("acceptance output and manifest must be paths")
    report = run_fixture_acceptance(output=output, manifest=manifest)
    sys.stdout.write(_canonical_json(asdict(report)).decode())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
