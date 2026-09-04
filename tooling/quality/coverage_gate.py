"""Enforce truthful production, sensitive-package, and changed-code coverage."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_SENSITIVE_PACKAGES = ("risk", "execution", "portfolio", "backtest")
_BRANCH_PAIR_SIZE = 2
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@")


@dataclass(frozen=True)
class CoverageThresholds:
    """Required percentages for each independently enforced coverage scope."""

    global_lines: float = 90
    global_branches: float = 80
    sensitive_branches: float = 90
    changed_lines: float = 90
    changed_branches: float = 85


@dataclass(frozen=True)
class _Stats:
    covered_lines: int = 0
    total_lines: int = 0
    covered_branches: int = 0
    total_branches: int = 0

    def __add__(self, other: _Stats) -> _Stats:
        return _Stats(
            covered_lines=self.covered_lines + other.covered_lines,
            total_lines=self.total_lines + other.total_lines,
            covered_branches=self.covered_branches + other.covered_branches,
            total_branches=self.total_branches + other.total_branches,
        )


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return cast("dict[str, object]", value)


def _integer_set(value: object) -> set[int]:
    if not isinstance(value, list):
        return set()
    return {item for item in value if isinstance(item, int)}


def _branch_set(value: object) -> set[tuple[int, int]]:
    if not isinstance(value, list):
        return set()
    branches: set[tuple[int, int]] = set()
    for item in value:
        if (
            isinstance(item, list)
            and len(item) == _BRANCH_PAIR_SIZE
            and isinstance(item[0], int)
            and isinstance(item[1], int)
        ):
            branches.add((item[0], item[1]))
    return branches


def _is_production_path(path: str) -> bool:
    normalized = path.replace("\\", "/").removeprefix("./")
    return (
        (normalized.startswith("packages/") or normalized.startswith("apps/backend/"))
        and "/src/" in normalized
        and "/generated/" not in normalized
    )


def _stats(value: object, changed: set[int] | None = None) -> _Stats:
    details = _mapping(value)
    executed_lines = _integer_set(details.get("executed_lines"))
    missing_lines = _integer_set(details.get("missing_lines"))
    executed_branches = _branch_set(details.get("executed_branches"))
    missing_branches = _branch_set(details.get("missing_branches"))
    if changed is not None:
        executed_lines &= changed
        missing_lines &= changed
        executed_branches = {
            branch for branch in executed_branches if branch[0] in changed
        }
        missing_branches = {
            branch for branch in missing_branches if branch[0] in changed
        }
    return _Stats(
        covered_lines=len(executed_lines),
        total_lines=len(executed_lines | missing_lines),
        covered_branches=len(executed_branches),
        total_branches=len(executed_branches | missing_branches),
    )


def _percentage(covered: int, total: int) -> float | None:
    return None if total == 0 else covered * 100 / total


def _require(
    violations: list[str], *, label: str, actual: float | None, minimum: float
) -> None:
    if actual is not None and actual + 1e-9 < minimum:
        violations.append(f"{label} coverage {actual:.2f}% is below {minimum:.2f}%")


def evaluate_report(
    report: Mapping[str, object],
    *,
    thresholds: CoverageThresholds,
    changed_lines: dict[str, set[int]],
) -> list[str]:
    """Evaluate a coverage.py JSON report without trusting its aggregate totals."""
    files = _mapping(report.get("files"))
    production = {
        path.replace("\\", "/").removeprefix("./"): details
        for path, details in files.items()
        if _is_production_path(path)
    }
    if not production:
        return ["coverage report contains no production src files"]

    global_stats = sum((_stats(value) for value in production.values()), _Stats())
    violations: list[str] = []
    _require(
        violations,
        label="global line",
        actual=_percentage(global_stats.covered_lines, global_stats.total_lines),
        minimum=thresholds.global_lines,
    )
    _require(
        violations,
        label="global branch",
        actual=_percentage(global_stats.covered_branches, global_stats.total_branches),
        minimum=thresholds.global_branches,
    )

    for package in _SENSITIVE_PACKAGES:
        prefix = f"packages/{package}/src/"
        package_stats = sum(
            (
                _stats(value)
                for path, value in production.items()
                if path.startswith(prefix)
            ),
            _Stats(),
        )
        _require(
            violations,
            label=f"packages/{package} branch",
            actual=_percentage(
                package_stats.covered_branches, package_stats.total_branches
            ),
            minimum=thresholds.sensitive_branches,
        )

    changed_stats = sum(
        (
            _stats(value, changed_lines.get(path, set()))
            for path, value in production.items()
            if path in changed_lines
        ),
        _Stats(),
    )
    _require(
        violations,
        label="changed line",
        actual=_percentage(changed_stats.covered_lines, changed_stats.total_lines),
        minimum=thresholds.changed_lines,
    )
    _require(
        violations,
        label="changed branch",
        actual=_percentage(
            changed_stats.covered_branches, changed_stats.total_branches
        ),
        minimum=thresholds.changed_branches,
    )
    return sorted(violations)


def _run_git(root: Path, arguments: list[str]) -> str:
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("git executable not found")
    result = subprocess.run(  # noqa: S603 - fixed git executable and controlled args
        [executable, *arguments],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def changed_executable_lines(root: Path, base_ref: str) -> dict[str, set[int]]:
    """Return added/modified line numbers since the merge base with ``base_ref``."""
    merge_base = _run_git(root, ["merge-base", base_ref, "HEAD"]).strip()
    diff = _run_git(root, ["diff", "--unified=0", "--no-ext-diff", merge_base, "--"])
    changed: dict[str, set[int]] = {}
    current_path: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_path = line.removeprefix("+++ b/")
            continue
        match = _HUNK.match(line)
        if current_path is None or match is None:
            continue
        start = int(match.group("start"))
        count = int(match.group("count") or "1")
        changed.setdefault(current_path, set()).update(range(start, start + count))
    return changed


def _default_base_ref() -> str | None:
    explicit = os.environ.get("COVERAGE_BASE_REF")
    if explicit:
        return explicit
    github_base = os.environ.get("GITHUB_BASE_REF")
    if github_base:
        return f"origin/{github_base}"
    return None


def main(argv: list[str] | None = None) -> int:
    """Validate one JSON report and emit actionable threshold failures."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=Path("coverage.json"))
    parser.add_argument("--base-ref", default=_default_base_ref())
    args = parser.parse_args(argv)
    report = cast(
        "dict[str, object]", json.loads(args.report.read_text(encoding="utf-8"))
    )
    root = Path(__file__).resolve().parents[2]
    if args.base_ref:
        changed = changed_executable_lines(root, str(args.base_ref))
    elif os.environ.get("CI"):
        sys.stderr.write("coverage gate requires --base-ref in CI\n")
        return 2
    else:
        changed = {}
        sys.stdout.write(
            "No coverage base ref; changed-code threshold not evaluated.\n"
        )
    violations = evaluate_report(
        report,
        thresholds=CoverageThresholds(),
        changed_lines=changed,
    )
    if violations:
        sys.stderr.write("Coverage threshold violations:\n")
        sys.stderr.write("\n".join(f"- {item}" for item in violations) + "\n")
        return 1
    sys.stdout.write("Coverage thresholds satisfied.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
