import json
from pathlib import Path

import pytest

from tooling.quality import coverage_gate
from tooling.quality.coverage_gate import CoverageThresholds, evaluate_report


def test_protocol_declarations_are_not_executable_but_default_bodies_are() -> None:
    source = (
        "from typing import Protocol\n"
        "class Port(Protocol):\n"
        "    def read(self) -> str: ...\n"
        "class DefaultPort(Protocol):\n"
        "    def read(self) -> str:\n"
        "        return 'real behavior'\n"
        "def health():\n"
        "    logger.debug('observable behavior')\n"
        "class ChildPort(Port, Protocol):\n"
        "    def write(self) -> None: ...\n"
    )
    assert coverage_gate.protocol_declaration_lines(source) == {2, 3, 9, 10}


def _file(
    *,
    executed: list[int],
    missing: list[int],
    executed_branches: list[list[int]] | None = None,
    missing_branches: list[list[int]] | None = None,
    excluded: list[int] | None = None,
) -> dict[str, object]:
    return {
        "executed_lines": executed,
        "missing_lines": missing,
        "executed_branches": executed_branches or [],
        "missing_branches": missing_branches or [],
        "excluded_lines": excluded or [],
    }


def _fully_covered_sensitive_files() -> dict[str, object]:
    return {
        f"packages/{package}/src/ditto_{package}/covered.py": _file(
            executed=[1],
            missing=[],
            executed_branches=[[1, 2], [1, 3]],
        )
        for package in ("risk", "execution", "portfolio", "backtest")
    }


def test_accepts_report_meeting_global_sensitive_and_changed_thresholds() -> None:
    report = {
        "files": {
            **_fully_covered_sensitive_files(),
            "packages/risk/src/ditto_risk/rules.py": _file(
                executed=list(range(1, 10)),
                missing=[10],
                executed_branches=[[1, 2], [1, 3], [4, 5], [4, 6]],
            ),
            "packages/data/src/ditto_data/query.py": _file(
                executed=list(range(1, 10)),
                missing=[10],
                executed_branches=[[1, 2], [1, 3], [4, 5], [4, 6]],
            ),
        }
    }
    thresholds = CoverageThresholds(
        global_lines=90,
        global_branches=80,
        sensitive_branches=80,
        changed_lines=90,
        changed_branches=80,
    )

    assert (
        evaluate_report(
            report,
            thresholds=thresholds,
            changed_lines={"packages/risk/src/ditto_risk/rules.py": {1, 2}},
        )
        == []
    )


def test_reports_each_threshold_family_independently() -> None:
    report = {
        "files": {
            **_fully_covered_sensitive_files(),
            "packages/risk/src/ditto_risk/rules.py": _file(
                executed=[1],
                missing=[2, 3],
                executed_branches=[[1, 2]],
                missing_branches=[[1, 3], [2, 3]],
            ),
            "packages/data/src/ditto_data/query.py": _file(
                executed=[1],
                missing=[2, 3],
                missing_branches=[[1, 2]],
            ),
        }
    }

    violations = evaluate_report(
        report,
        thresholds=CoverageThresholds(),
        changed_lines={"packages/risk/src/ditto_risk/rules.py": {1, 2}},
    )

    assert any("global line" in item for item in violations)
    assert any("global branch" in item for item in violations)
    assert any("packages/risk branch" in item for item in violations)
    assert any("changed line" in item for item in violations)
    assert any("changed branch" in item for item in violations)


def test_ignores_non_production_files_even_if_report_contains_them() -> None:
    report = {
        "files": {
            **_fully_covered_sensitive_files(),
            "packages/risk/src/ditto_risk/rules.py": _file(
                executed=list(range(1, 11)), missing=[]
            ),
            "packages/risk/tests/test_rules.py": _file(executed=[], missing=[1, 2]),
        }
    }

    violations = evaluate_report(
        report,
        thresholds=CoverageThresholds(
            global_lines=100,
            global_branches=0,
            sensitive_branches=0,
            changed_lines=0,
            changed_branches=0,
        ),
        changed_lines={},
    )

    assert violations == []


@pytest.mark.parametrize("package", ["risk", "execution", "portfolio", "backtest"])
def test_rejects_report_when_a_sensitive_package_is_completely_missing(
    package: str,
) -> None:
    files = _fully_covered_sensitive_files()
    del files[f"packages/{package}/src/ditto_{package}/covered.py"]

    violations = evaluate_report(
        {"files": files},
        thresholds=CoverageThresholds(
            global_lines=0,
            global_branches=0,
            sensitive_branches=0,
            changed_lines=0,
            changed_branches=0,
        ),
        changed_lines={},
    )

    assert violations == [
        "coverage report contains no source files for sensitive package "
        f"packages/{package}"
    ]


def test_rejects_sensitive_package_without_measured_branches() -> None:
    files = _fully_covered_sensitive_files()
    files["packages/risk/src/ditto_risk/covered.py"] = _file(
        executed=[1],
        missing=[],
    )

    violations = evaluate_report(
        {"files": files},
        thresholds=CoverageThresholds(
            global_lines=0,
            global_branches=0,
            sensitive_branches=0,
            changed_lines=0,
            changed_branches=0,
        ),
        changed_lines={},
    )

    assert violations == [
        "coverage report contains no measured branches for sensitive package "
        "packages/risk"
    ]


def test_rejects_global_report_without_measured_lines_or_branches() -> None:
    files = {
        f"packages/{package}/src/ditto_{package}/empty.py": _file(
            executed=[],
            missing=[],
        )
        for package in ("risk", "execution", "portfolio", "backtest")
    }

    violations = evaluate_report(
        {"files": files},
        thresholds=CoverageThresholds(
            global_lines=0,
            global_branches=0,
            sensitive_branches=0,
            changed_lines=0,
            changed_branches=0,
        ),
        changed_lines={},
    )

    assert "coverage report contains no measured production lines" in violations
    assert "coverage report contains no measured production branches" in violations


def test_production_paths_require_python_source() -> None:
    assert coverage_gate._is_production_path(
        "packages/data/src/ditto_data/sources/example.py"
    )
    assert not coverage_gate._is_production_path(
        "packages/data/src/ditto_data/sources/README.md"
    )


def test_rejects_changed_production_path_absent_from_report() -> None:
    missing_path = "apps/backend/src/ditto_apps/new_behavior.py"

    violations = evaluate_report(
        {"files": _fully_covered_sensitive_files()},
        thresholds=CoverageThresholds(
            global_lines=0,
            global_branches=0,
            sensitive_branches=0,
            changed_lines=0,
            changed_branches=0,
        ),
        changed_lines={missing_path: {10}},
    )

    assert violations == [
        f"changed production path is absent from coverage report: {missing_path}"
    ]


def test_allows_instrumented_changed_file_with_only_non_executable_lines() -> None:
    path = "apps/backend/src/ditto_apps/comment_only.py"
    files = _fully_covered_sensitive_files()
    files[path] = _file(executed=[10], missing=[])

    violations = evaluate_report(
        {"files": files},
        thresholds=CoverageThresholds(
            global_lines=0,
            global_branches=0,
            sensitive_branches=0,
            changed_lines=100,
            changed_branches=100,
        ),
        changed_lines={path: {1, 2}},
    )

    assert violations == []


def test_applies_changed_line_gate_when_changed_code_has_no_branches() -> None:
    path = "apps/backend/src/ditto_apps/linear_change.py"
    files = _fully_covered_sensitive_files()
    files[path] = _file(executed=[1], missing=[2])

    violations = evaluate_report(
        {"files": files},
        thresholds=CoverageThresholds(
            global_lines=0,
            global_branches=0,
            sensitive_branches=0,
            changed_lines=100,
            changed_branches=100,
        ),
        changed_lines={path: {2}},
    )

    assert violations == ["changed line coverage 0.00% is below 100.00%"]


def test_rejects_changed_production_lines_excluded_from_coverage() -> None:
    path = "apps/backend/src/ditto_apps/excluded_change.py"
    files = _fully_covered_sensitive_files()
    files[path] = _file(executed=[1], missing=[], excluded=[2])

    violations = evaluate_report(
        {"files": files},
        thresholds=CoverageThresholds(
            global_lines=0,
            global_branches=0,
            sensitive_branches=0,
            changed_lines=0,
            changed_branches=0,
        ),
        changed_lines={path: {2}},
    )

    assert violations == [
        f"changed production lines are excluded from coverage: {path}:2"
    ]


def test_cli_uses_the_exact_ci_base_supplied_by_the_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The workflow's event SHA must reach the Git merge-base calculation unchanged."""
    report_path = tmp_path / "coverage.json"
    report_path.write_text(
        json.dumps(
            {
                "files": {
                    **_fully_covered_sensitive_files(),
                    "apps/backend/src/ditto_apps/example.py": _file(
                        executed=list(range(1, 11)),
                        missing=[],
                        executed_branches=[[1, 2], [1, 3]],
                    ),
                }
            }
        ),
        encoding="utf-8",
    )
    observed: list[str] = []

    def fake_changed_lines(_root: Path, base_ref: str) -> dict[str, set[int]]:
        observed.append(base_ref)
        return {}

    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("COVERAGE_BASE_REF", "event-base-sha")
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    monkeypatch.setattr(coverage_gate, "changed_executable_lines", fake_changed_lines)

    assert coverage_gate.main(["--report", str(report_path)]) == 0
    assert observed == ["event-base-sha"]
