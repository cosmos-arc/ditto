"""Deterministic R3 dual-golden engineering acceptance runner."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import orjson
from ditto_application.processes.experiments.r2_live_gate_evidence import (
    FileR2LiveGateEvidenceReader,
    VerifiedR2LiveGateEvidence,
)

from ditto_apps.r2_live_evidence_source import load_r2_live_gate_source

__all__ = [
    "CommandResult",
    "CommandSpec",
    "LiveAcceptanceRequest",
    "R3AcceptanceReport",
    "deterministic_commands",
    "live_commands",
    "load_r2_live_gate_source",
    "run_fixture_acceptance",
    "run_live_acceptance",
]

_REPO_ROOT = Path(__file__).resolve().parents[5]
_DEFAULT_OUTPUT = _REPO_ROOT / "artifacts" / "acceptance" / "r3-report.json"
_DEFAULT_MANIFEST = _REPO_ROOT / "docs" / "evidence" / "r3" / "manifest.json"
_OUTPUT_LIMIT = 12_000
_SCHEMA = "ditto.r3-research-acceptance"
_MANIFEST_SCHEMA = "ditto.r3-evidence-manifest"
_LIVE_OPT_IN = "DITTO_RUN_REAL_DATA_ACCEPTANCE"


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


@dataclass(frozen=True, slots=True)
class R3LiveAcceptanceReport:
    """Machine-readable live result that passes only on verified real evidence."""

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
    r2_evidence: Mapping[str, object] | None
    commands: tuple[CommandResult, ...]


@dataclass(frozen=True, slots=True)
class LiveAcceptanceRequest:
    """Explicit filesystem and release guards for one Task 18 run."""

    output: Path
    manifest: Path
    r2_evidence: Path
    r2_source_manifest: Path
    require_certified: bool
    require_both_golden_lanes: bool


CommandRunner = Callable[[str, Sequence[str], Path], CommandResult]


@contextmanager
def _live_evidence_environment(
    report_path: Path,
    source_manifest: Path,
):
    keys = {
        "DITTO_R2_LIVE_REPORT_PATH": str(report_path.resolve(strict=True)),
        "DITTO_R2_LIVE_SOURCE_MANIFEST_PATH": str(source_manifest.resolve(strict=True)),
    }
    previous = {key: os.environ.get(key) for key in keys}
    os.environ.update(keys)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


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


def live_commands() -> tuple[CommandSpec, ...]:
    """Return the frozen Task 18 live command set in release order."""
    target = "packages/apps/tests/e2e/test_r3_live_acceptance.py"
    return (
        CommandSpec(
            "stock-live-golden",
            _pytest(f"{target}::test_stock_live_golden_lane"),
        ),
        CommandSpec(
            "etf-live-golden",
            _pytest(f"{target}::test_etf_live_golden_lane"),
        ),
        CommandSpec(
            "governance-live-lifecycle",
            _pytest(f"{target}::test_live_publish_r1_and_reactivate"),
        ),
        CommandSpec(
            "isolated-live-backup-restore",
            _pytest(f"{target}::test_isolated_live_backup_restore"),
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
    mode: str = "deterministic_fixture",
) -> None:
    _write_json(
        manifest,
        {
            "entries": [
                {
                    "command": invocation,
                    "generated_at": generated_at,
                    "mode": mode,
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


def _verified_r2_evidence(
    *,
    report_path: Path,
    source_manifest: Path,
) -> VerifiedR2LiveGateEvidence | None:
    source = load_r2_live_gate_source(
        report_path=report_path,
        source_manifest=source_manifest,
    )
    if source is None:
        return None
    return FileR2LiveGateEvidenceReader(source).read_verified_live_gate()


def _live_report(
    *,
    generated_at: str,
    source_commit: str,
    failures: tuple[str, ...],
    r2_live_gate: str,
    r2_evidence: VerifiedR2LiveGateEvidence | None,
    results: tuple[CommandResult, ...],
) -> R3LiveAcceptanceReport:
    passed = not failures
    return R3LiveAcceptanceReport(
        schema=_SCHEMA,
        version=2,
        generated_at=generated_at,
        source_commit=source_commit,
        mode="real_data",
        passed=passed,
        release_status=(
            "RELEASE_ACCEPTANCE_PASSED" if passed else "RELEASE_ACCEPTANCE_BLOCKED"
        ),
        r2_live_gate=r2_live_gate,
        golden_lanes=("stock", "etf"),
        failures=failures,
        proves=(
            (
                "verified_r2_live_gate",
                "certified_stock_and_etf_live_golden_lanes",
                "live_96_month_research_governance_lifecycle",
                "live_publish_r1_reactivate",
                "isolated_live_backup_restore",
            )
            if passed
            else ()
        ),
        does_not_prove=(
            ()
            if passed
            else (
                "r3_live_release_acceptance",
                "real_browser_acceptance",
            )
        ),
        r2_evidence=(r2_evidence.gate_detail() if r2_evidence is not None else None),
        commands=results,
    )


def run_live_acceptance(
    *,
    request: LiveAcceptanceRequest,
    environment: Mapping[str, str] = os.environ,
    checked_at: datetime | None = None,
    source_commit: str | None = None,
    command_runner: CommandRunner = _subprocess_runner,
    invocation: str = (
        "DITTO_RUN_REAL_DATA_ACCEPTANCE=1 pixi run -e dev python -m "
        "ditto_apps.scripts.r3_research_acceptance --real-data "
        "--require-certified --require-both-golden-lanes "
        "--r2-evidence artifacts/acceptance/r2-report.json "
        "--output artifacts/acceptance/r3-report.json"
    ),
) -> R3LiveAcceptanceReport:
    """Run live acceptance only after exact opt-in and verified R2 evidence."""
    now = checked_at or datetime.now(UTC)
    generated_at = now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    commit = source_commit or _source_commit()
    failures: list[str] = []
    if environment.get(_LIVE_OPT_IN) != "1":
        failures.append("real_data_opt_in_missing")
    if not request.require_certified:
        failures.append("certified_data_requirement_missing")
    if not request.require_both_golden_lanes:
        failures.append("both_golden_lanes_requirement_missing")

    verified: VerifiedR2LiveGateEvidence | None = None
    r2_gate = "NOT_EVALUATED"
    if not failures:
        verified = _verified_r2_evidence(
            report_path=request.r2_evidence,
            source_manifest=request.r2_source_manifest,
        )
        if verified is None:
            failures.append("r2_live_evidence_unverified")
        elif verified.status != "ready":
            r2_gate = "FAIL"
            failures.append(f"r2_live_gate_{verified.status}")
        else:
            r2_gate = "PASS"

    results: tuple[CommandResult, ...] = ()
    if not failures:
        with _live_evidence_environment(
            request.r2_evidence,
            request.r2_source_manifest,
        ):
            results = tuple(
                _run_command(spec, command_runner=command_runner)
                for spec in live_commands()
            )
        failures.extend(result.name for result in results if not result.passed)
    report = _live_report(
        generated_at=generated_at,
        source_commit=commit,
        failures=tuple(failures),
        r2_live_gate=r2_gate,
        r2_evidence=verified,
        results=results,
    )
    _write_json(request.output, asdict(report))
    _write_manifest(
        manifest=request.manifest,
        output=request.output,
        generated_at=generated_at,
        source_commit=commit,
        invocation=invocation,
        mode="live",
    )
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixture", action="store_true")
    mode.add_argument("--real-data", action="store_true")
    parser.add_argument("--require-certified", action="store_true")
    parser.add_argument("--require-both-golden-lanes", action="store_true")
    parser.add_argument("--r2-evidence", type=Path)
    parser.add_argument("--r2-source-manifest", type=Path)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run fixture or explicitly authorized, content-verified live acceptance."""
    args = _parser().parse_args(argv)
    output = args.output
    manifest = args.manifest
    if not isinstance(output, Path) or not isinstance(manifest, Path):
        raise TypeError("acceptance output and manifest must be paths")
    if args.fixture:
        report: R3AcceptanceReport | R3LiveAcceptanceReport = run_fixture_acceptance(
            output=output,
            manifest=manifest,
        )
    else:
        if not isinstance(args.r2_evidence, Path):
            _parser().error("--r2-evidence is required with --real-data")
        source_manifest = args.r2_source_manifest
        if source_manifest is None:
            source_manifest = args.r2_evidence.with_name(
                f"{args.r2_evidence.stem}.manifest{args.r2_evidence.suffix}"
            )
        if not isinstance(source_manifest, Path):
            raise TypeError("R2 source manifest must be a path")
        report = run_live_acceptance(
            request=LiveAcceptanceRequest(
                output=output,
                manifest=manifest,
                r2_evidence=args.r2_evidence,
                r2_source_manifest=source_manifest,
                require_certified=bool(args.require_certified),
                require_both_golden_lanes=bool(args.require_both_golden_lanes),
            )
        )
    sys.stdout.write(_canonical_json(asdict(report)).decode())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
