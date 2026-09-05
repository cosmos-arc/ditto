"""Enforce truthful production, sensitive-package, and changed-code coverage."""

from __future__ import annotations

import argparse
import ast
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
    normalized = _normalize_path(path)
    return (
        (normalized.startswith("packages/") or normalized.startswith("apps/backend/"))
        and "/src/" in normalized
        and "/generated/" not in normalized
    )


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").removeprefix("./")


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


def _require_measured_metric(
    violations: list[str],
    *,
    label: str,
    covered: int,
    total: int,
    minimum: float,
    unmeasured: str,
) -> None:
    if total == 0:
        violations.append(unmeasured)
        return
    _require(
        violations,
        label=label,
        actual=_percentage(covered, total),
        minimum=minimum,
    )


def _sensitive_package_violations(
    production: Mapping[str, object], thresholds: CoverageThresholds
) -> list[str]:
    violations: list[str] = []
    for package in _SENSITIVE_PACKAGES:
        prefix = f"packages/{package}/src/"
        package_files = tuple(
            value for path, value in production.items() if path.startswith(prefix)
        )
        if not package_files:
            violations.append(
                "coverage report contains no source files for sensitive package "
                + f"packages/{package}"
            )
            continue
        package_stats = sum((_stats(value) for value in package_files), _Stats())
        _require_measured_metric(
            violations,
            label=f"packages/{package} branch",
            covered=package_stats.covered_branches,
            total=package_stats.total_branches,
            minimum=thresholds.sensitive_branches,
            unmeasured=(
                "coverage report contains no measured branches for sensitive package "
                + f"packages/{package}"
            ),
        )
    return violations


def _production_changed_lines(
    changed_lines: Mapping[str, set[int]],
) -> dict[str, set[int]]:
    production_changed: dict[str, set[int]] = {}
    for path, lines in changed_lines.items():
        normalized = _normalize_path(path)
        if lines and _is_production_path(normalized):
            production_changed.setdefault(normalized, set()).update(lines)
    return production_changed


def _changed_coverage_violations(
    production: Mapping[str, object],
    changed_lines: Mapping[str, set[int]],
    thresholds: CoverageThresholds,
) -> list[str]:
    violations: list[str] = []
    production_changed = _production_changed_lines(changed_lines)
    for path in sorted(set(production_changed) - set(production)):
        violations.append(
            f"changed production path is absent from coverage report: {path}"
        )

    for path in sorted(set(production_changed) & set(production)):
        details = _mapping(production[path])
        excluded = (
            _integer_set(details.get("excluded_lines")) & production_changed[path]
        )
        if excluded:
            rendered_lines = ",".join(str(line) for line in sorted(excluded))
            violations.append(
                "changed production lines are excluded from coverage: "
                + f"{path}:{rendered_lines}"
            )

    changed_stats = sum(
        (
            _stats(value, production_changed[path])
            for path, value in production.items()
            if path in production_changed
        ),
        _Stats(),
    )
    # A present coverage record proves the file was instrumented. If its changed
    # lines intersect no measured or excluded statement, coverage.py has classified
    # the edit as non-executable (for example a comment); changed coverage is N/A.
    if changed_stats.total_lines > 0:
        _require(
            violations,
            label="changed line",
            actual=_percentage(changed_stats.covered_lines, changed_stats.total_lines),
            minimum=thresholds.changed_lines,
        )
    # Linear executable changes still have a line denominator but legitimately no
    # branch denominator. Enforce the branch threshold only when branches exist.
    if changed_stats.total_branches > 0:
        _require(
            violations,
            label="changed branch",
            actual=_percentage(
                changed_stats.covered_branches, changed_stats.total_branches
            ),
            minimum=thresholds.changed_branches,
        )
    return violations


def evaluate_report(
    report: Mapping[str, object],
    *,
    thresholds: CoverageThresholds,
    changed_lines: dict[str, set[int]],
) -> list[str]:
    """Evaluate a coverage.py JSON report without trusting its aggregate totals."""
    files = _mapping(report.get("files"))
    production = {
        _normalize_path(path): details
        for path, details in files.items()
        if _is_production_path(path)
    }
    if not production:
        return ["coverage report contains no production src files"]

    global_stats = sum((_stats(value) for value in production.values()), _Stats())
    violations: list[str] = []
    _require_measured_metric(
        violations,
        label="global line",
        covered=global_stats.covered_lines,
        total=global_stats.total_lines,
        minimum=thresholds.global_lines,
        unmeasured="coverage report contains no measured production lines",
    )
    _require_measured_metric(
        violations,
        label="global branch",
        covered=global_stats.covered_branches,
        total=global_stats.total_branches,
        minimum=thresholds.global_branches,
        unmeasured="coverage report contains no measured production branches",
    )
    violations.extend(_sensitive_package_violations(production, thresholds))
    violations.extend(
        _changed_coverage_violations(production, changed_lines, thresholds)
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


def _declaration_statement(node: ast.stmt) -> bool:
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
        return isinstance(node.value.value, str) or node.value.value is Ellipsis
    if isinstance(node, ast.Pass):
        return True
    if isinstance(node, ast.AnnAssign):
        return node.value is None
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return (
            not node.args.defaults
            and not any(value is not None for value in node.args.kw_defaults)
            and all(
                isinstance(item, ast.Name) and item.id in {"property", "abstractmethod"}
                for item in node.decorator_list
            )
            and all(_declaration_statement(item) for item in node.body)
        )
    return False


def protocol_declaration_lines(source: str) -> set[int]:
    """Recognize only pure typing.Protocol stubs, never default implementations."""
    tree = ast.parse(source)
    imported = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "typing"
        and any(
            alias.name == "Protocol" and alias.asname is None for alias in node.names
        )
        for node in tree.body
    )
    if not imported:
        return set()
    declarations: set[int] = set()
    for node in tree.body:
        if (
            isinstance(node, ast.ClassDef)
            and not node.decorator_list
            and not node.keywords
            and all(isinstance(base, ast.Name) for base in node.bases)
            and any(
                isinstance(base, ast.Name) and base.id == "Protocol"
                for base in node.bases
            )
            and all(_declaration_statement(item) for item in node.body)
        ):
            declarations.update(
                range(node.lineno, (node.end_lineno or node.lineno) + 1)
            )
    return declarations


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
    for name, lines in changed.items():
        source = root / name
        if source.suffix == ".py" and source.is_file():
            lines.difference_update(
                protocol_declaration_lines(source.read_text(encoding="utf-8"))
            )
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
