import json
from pathlib import Path

import pytest

from tooling.quality import coverage_gate
from tooling.quality.coverage_gate import CoverageThresholds, evaluate_report


def _file(
    *,
    executed: list[int],
    missing: list[int],
    executed_branches: list[list[int]] | None = None,
    missing_branches: list[list[int]] | None = None,
) -> dict[str, object]:
    return {
        "executed_lines": executed,
        "missing_lines": missing,
        "executed_branches": executed_branches or [],
        "missing_branches": missing_branches or [],
    }


def test_accepts_report_meeting_global_sensitive_and_changed_thresholds() -> None:
    report = {
        "files": {
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
                    "apps/backend/src/ditto_apps/example.py": _file(
                        executed=list(range(1, 11)),
                        missing=[],
                        executed_branches=[[1, 2], [1, 3]],
                    )
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
