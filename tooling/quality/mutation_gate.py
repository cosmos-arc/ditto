"""
Run and score mutation tests for Ditto's deterministic critical core.

Mutmut only places ``mutants/src`` on ``sys.path``. Ditto has one ``src`` root per
capability package, so this runner builds a temporary, byte-for-byte source forest
before invoking Mutmut. This keeps imports canonical and prevents the all-``no tests``
false positive produced by running Mutmut at the monorepo root.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
_PACKAGES: Final = ("data", "execution", "portfolio", "risk")
_IMPORT_PACKAGES: Final = {
    "data": "ditto_data",
    "execution": "ditto_execution",
    "portfolio": "ditto_portfolio",
    "risk": "ditto_risk",
}
_DEFAULT_REPORT: Final = _REPO_ROOT / "build/mutation/mutmut-cicd-stats.json"
_PERCENT_MAX: Final = 100.0
_STAGING_PYPROJECT: Final = """
[tool.mutmut]
source_paths = ["src"]
only_mutate = [
    "src/ditto_data/query/service.py",
    "src/ditto_execution/orders/fsm.py",
    "src/ditto_portfolio/accounting/account.py",
    "src/ditto_portfolio/accounting/buying_power.py",
    "src/ditto_portfolio/accounting/cash.py",
    "src/ditto_portfolio/accounting/position.py",
    "src/ditto_risk/constraints/checks.py",
]
pytest_add_cli_args_test_selection = [
    "packages/data/tests/unit/query/test_pit_query_service_unit.py",
    "packages/execution/tests/unit/orders",
    "packages/portfolio/tests/unit/accounting",
    "packages/risk/tests/unit",
]
pytest_add_cli_args = ["-q", "-n0", "--no-cov", "--disable-warnings"]
also_copy = ["packages"]
max_stack_depth = 12
use_setproctitle = false
on_dependency_change = "rerun"
timeout_multiplier = 5.0
timeout_constant = 0.5

[tool.pytest.ini_options]
asyncio_mode = "strict"
""".lstrip()


class MutationGateError(RuntimeError):
    """Raised when mutation evidence is absent, incomplete, or too weak."""


@dataclass(frozen=True)
class MutationStats:
    """Terminal Mutmut status counts."""

    killed: int
    survived: int
    no_tests: int
    suspicious: int
    timeout: int
    interrupted: int
    segfault: int
    skipped: int
    total: int

    @property
    def denominator(self) -> int:
        """Return all non-skipped mutants that must be killed."""
        return self.total - self.skipped

    @property
    def terminal_non_skipped(self) -> int:
        """Return reported terminal outcomes excluding explicit skips."""
        return (
            self.killed
            + self.survived
            + self.no_tests
            + self.suspicious
            + self.timeout
            + self.interrupted
            + self.segfault
        )


@dataclass(frozen=True)
class MutationResult:
    """Validated mutation score."""

    score: float
    denominator: int


def _required_int(payload: object, key: str) -> int:
    if not isinstance(payload, dict):
        raise MutationGateError("mutation report must be a JSON object")
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MutationGateError(f"mutation report missing integer field: {key}")
    return value


def load_stats(path: Path) -> MutationStats:
    """Load the stable subset of Mutmut's CI/CD JSON schema."""
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MutationGateError(
            f"cannot read mutation report {path}: {error}"
        ) from error
    return MutationStats(
        killed=_required_int(payload, "killed"),
        survived=_required_int(payload, "survived"),
        no_tests=_required_int(payload, "no_tests"),
        suspicious=_required_int(payload, "suspicious"),
        timeout=_required_int(payload, "timeout"),
        interrupted=_required_int(payload, "check_was_interrupted_by_user"),
        segfault=_required_int(payload, "segfault"),
        skipped=_required_int(payload, "skipped"),
        total=_required_int(payload, "total"),
    )


def evaluate_stats(stats: MutationStats, *, threshold: float) -> MutationResult:
    """Fail closed on partial runs and enforce the requested mutation score."""
    if not 0.0 <= threshold <= _PERCENT_MAX:
        raise MutationGateError("mutation threshold must be between 0 and 100")
    if stats.denominator <= 0:
        raise MutationGateError("mutation run has no non-skipped mutants")
    if stats.terminal_non_skipped != stats.denominator:
        progress = f"{stats.terminal_non_skipped}/{stats.denominator}"
        message = " ".join(
            (
                f"mutation report is incomplete: {progress} non-skipped mutants",
                "have terminal outcomes",
            )
        )
        raise MutationGateError(message)
    # Mutmut's score treats a timeout as detected: the mutant cannot complete the
    # relevant tests. Other non-success outcomes stay in the denominator.
    detected = stats.killed + stats.timeout
    score = detected * _PERCENT_MAX / stats.denominator
    if score < threshold:
        raise MutationGateError(
            f"mutation score {score:.2f}% is below required {threshold:.2f}%"
        )
    return MutationResult(score=score, denominator=stats.denominator)


def _copy_workspace(destination: Path) -> None:
    """Build one conventional source root without changing source bytes."""
    source_root = destination / "src"
    source_root.mkdir(parents=True)
    for package in _PACKAGES:
        import_package = _IMPORT_PACKAGES[package]
        shutil.copytree(
            _REPO_ROOT / "packages" / package / "src" / import_package,
            source_root / import_package,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copytree(
            _REPO_ROOT / "packages" / package / "tests",
            destination / "packages" / package / "tests",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
        )
    (destination / "pyproject.toml").write_text(
        _STAGING_PYPROJECT,
        encoding="utf-8",
    )


def _run(command: list[str], *, cwd: Path) -> None:
    # Every argv element is constructed above from a resolved executable and numbers.
    completed = subprocess.run(command, cwd=cwd, check=False)  # noqa: S603
    if completed.returncode != 0:
        rendered_command = " ".join(command)
        message = " ".join(
            (
                f"mutation command failed with exit code {completed.returncode}:",
                rendered_command,
            )
        )
        raise MutationGateError(message)


def _run_capture(command: list[str], *, cwd: Path) -> str:
    """Run a trusted diagnostic command and return its complete text output."""
    completed = subprocess.run(  # noqa: S603
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        rendered_command = " ".join(command)
        raise MutationGateError(
            f"mutation diagnostic failed ({completed.returncode}): {rendered_command}"
        )
    return completed.stdout


def run_gate(
    *, threshold: float, max_children: int, report_path: Path
) -> MutationResult:
    """Execute Mutmut in an isolated conventional source tree and score it."""
    mutmut = shutil.which("mutmut")
    if mutmut is None:
        raise MutationGateError(
            "mutmut executable is not available in the prepared uv environment"
        )
    if max_children < 1:
        raise MutationGateError("max children must be positive")

    with tempfile.TemporaryDirectory(prefix="ditto-mutation-") as directory:
        workspace = Path(directory)
        _copy_workspace(workspace)
        _run([mutmut, "run", "--max-children", str(max_children)], cwd=workspace)
        _run([mutmut, "export-cicd-stats"], cwd=workspace)
        generated_report = workspace / "mutants/mutmut-cicd-stats.json"
        stats = load_stats(generated_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(generated_report, report_path)
        details = _run_capture([mutmut, "results"], cwd=workspace)
        report_path.with_name("mutmut-results.txt").write_text(
            details,
            encoding="utf-8",
        )
        result = evaluate_stats(stats, threshold=threshold)
        return result


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=float, default=80.0)
    parser.add_argument("--max-children", type=int, default=4)
    parser.add_argument("--report", type=Path, default=_DEFAULT_REPORT)
    args = parser.parse_args()
    try:
        result = run_gate(
            threshold=args.threshold,
            max_children=args.max_children,
            report_path=args.report,
        )
    except MutationGateError as error:
        print(f"mutation gate failed: {error}", file=sys.stderr)
        return 1
    outcome = f"{result.score:.2f}% ({result.denominator} non-skipped mutants)"
    print(f"mutation gate passed: {outcome}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
