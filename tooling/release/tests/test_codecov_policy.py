"""Coverage publication must reflect both monorepo stacks."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[3]


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast("dict[str, Any]", value)


def test_codecov_flags_cover_current_backend_and_web_trees() -> None:
    config = _yaml(ROOT / "codecov.yml")
    flags = config["flags"]
    assert flags["backend"]["paths"] == ["apps/backend/src/", "packages/"]
    assert set(flags["backend-critical"]["paths"]) == {
        "packages/backtest/src/",
        "packages/execution/src/",
        "packages/portfolio/src/",
        "packages/risk/src/",
    }
    assert flags["web"]["paths"] == ["apps/web/src/"]
    serialized = (ROOT / "codecov.yml").read_text(encoding="utf-8")
    for removed in ("packages/engine", "packages/infra", "interfaces/src"):
        assert removed not in serialized


def test_ci_publishes_both_coverage_reports_with_oidc_and_fails_closed() -> None:
    workflow = _yaml(ROOT / ".github" / "workflows" / "ci.yml")
    jobs = workflow["jobs"]
    for job_name, report, flags in (
        ("backend-tests", "coverage.xml", "backend,backend-critical"),
        ("web-quality", "apps/web/coverage/coverage-final.json", "web"),
    ):
        job = jobs[job_name]
        assert job["permissions"] == {"contents": "read", "id-token": "write"}
        upload = next(
            step
            for step in job["steps"]
            if str(step.get("uses", "")).startswith("codecov/codecov-action@")
        )
        assert upload["uses"].split("@", maxsplit=1)[1].isalnum()
        assert len(upload["uses"].split("@", maxsplit=1)[1]) == 40
        assert upload["with"] == {
            "disable_search": True,
            "fail_ci_if_error": True,
            "files": report,
            "flags": flags,
            "use_oidc": True,
        }
