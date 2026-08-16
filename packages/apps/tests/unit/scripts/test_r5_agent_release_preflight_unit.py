"""Fail-closed R5 Agent release-preflight evidence contracts."""

from __future__ import annotations

import shutil
from pathlib import Path

import orjson
import pytest
from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_apps.scripts.r5_agent_release_preflight import (
    ReleaseCheckStatus,
    build_release_preflight,
    main,
)

REPO_ROOT = Path(__file__).parents[5]


def _copy_release_surface(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(
        REPO_ROOT / "docs" / "evidence" / "r5" / "release",
        repo / "docs" / "evidence" / "r5" / "release",
    )
    for relative in (
        Path("docs/openapi/v1.json"),
        Path("docs/operations/r5-agent-runbook.md"),
        Path("docs/security/r5-agent-security-boundary.md"),
        Path("docs/roadmaps/ditto-development-roadmap.md"),
    ):
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative, target)
    return repo


def _write_authenticated_report(path: Path, payload: dict[str, object]) -> None:
    identity = {key: value for key, value in payload.items() if key != "report_hash"}
    payload["report_hash"] = canonical_sha256(identity)
    path.write_bytes(canonical_bytes(payload))


def test_current_preflight_is_blocked_only_by_exact_a3_a4_gates() -> None:
    first = build_release_preflight(REPO_ROOT)
    second = build_release_preflight(REPO_ROOT)

    assert first.to_bytes() == second.to_bytes()
    assert first.passed is False
    assert first.exit_code == 5
    assert first.blockers == ("A3", "A4")
    assert first.failures == ()
    checks = {item.name: item for item in first.checks}
    assert checks["fake_eval"].status is ReleaseCheckStatus.PASSED
    assert checks["operational_exercises"].status is ReleaseCheckStatus.PASSED
    assert checks["interface_contracts"].status is ReleaseCheckStatus.PASSED
    assert checks["sandbox_live"].status is ReleaseCheckStatus.BLOCKED
    assert checks["balanced_live_eval"].status is ReleaseCheckStatus.BLOCKED
    assert checks["quality_live_eval"].status is ReleaseCheckStatus.BLOCKED
    assert (
        first.to_bytes()
        == (
            REPO_ROOT
            / "docs"
            / "evidence"
            / "r5"
            / "release"
            / "release-preflight.json"
        ).read_bytes()
    )


def test_tampered_fake_report_is_a_failure_not_an_approval_blocker(
    tmp_path: Path,
) -> None:
    repo = _copy_release_surface(tmp_path)
    report_path = repo / "docs/evidence/r5/release/eval-report-fake.json"
    payload = orjson.loads(report_path.read_bytes())
    payload["passed"] = False
    report_path.write_bytes(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS))

    report = build_release_preflight(repo)

    assert report.exit_code == 1
    assert report.passed is False
    assert report.failures == ("fake_eval",)
    fake_check = next(item for item in report.checks if item.name == "fake_eval")
    assert fake_check.status is ReleaseCheckStatus.FAILED
    assert fake_check.reason_code == "fake_eval_report_hash_invalid"


def test_self_consistent_dataset_manifest_forgery_fails_closed(
    tmp_path: Path,
) -> None:
    repo = _copy_release_surface(tmp_path)
    report_path = repo / "docs/evidence/r5/release/eval-report-fake.json"
    payload = orjson.loads(report_path.read_bytes())
    payload["dataset_manifest"][0]["cases"][0]["case_id"] = "forged-case"
    payload["dataset_manifest_hash"] = canonical_sha256(payload["dataset_manifest"])
    _write_authenticated_report(report_path, payload)

    report = build_release_preflight(repo)

    assert report.exit_code == 1
    fake_check = next(item for item in report.checks if item.name == "fake_eval")
    assert fake_check.reason_code == "fake_eval_manifest_invalid"


def test_fully_rehashed_case_identity_forgery_breaks_the_frozen_release(
    tmp_path: Path,
) -> None:
    repo = _copy_release_surface(tmp_path)
    report_path = repo / "docs/evidence/r5/release/eval-report-fake.json"
    payload = orjson.loads(report_path.read_bytes())
    forged_input_hash = "0" * 64
    payload["dataset_manifest"][0]["cases"][0]["input_hash"] = forged_input_hash
    result = payload["suite_reports"][0]["results"][0]
    result["input_hash"] = forged_input_hash
    result["result_hash"] = canonical_sha256(
        {key: value for key, value in result.items() if key != "result_hash"}
    )
    suite_report = payload["suite_reports"][0]
    suite_report["report_hash"] = canonical_sha256(
        {key: value for key, value in suite_report.items() if key != "report_hash"}
    )
    payload["dataset_manifest_hash"] = canonical_sha256(payload["dataset_manifest"])
    _write_authenticated_report(report_path, payload)

    report = build_release_preflight(repo)

    assert report.exit_code == 1
    fake_check = next(item for item in report.checks if item.name == "fake_eval")
    assert fake_check.reason_code == "fake_eval_frozen_identity_mismatch"


def test_self_consistent_observation_manifest_forgery_fails_closed(
    tmp_path: Path,
) -> None:
    repo = _copy_release_surface(tmp_path)
    report_path = repo / "docs/evidence/r5/release/eval-report-fake.json"
    payload = orjson.loads(report_path.read_bytes())
    payload["observation_manifest"][0]["case_id"] = "forged-case"
    payload["observation_manifest_hash"] = canonical_sha256(
        payload["observation_manifest"]
    )
    _write_authenticated_report(report_path, payload)

    report = build_release_preflight(repo)

    assert report.exit_code == 1
    fake_check = next(item for item in report.checks if item.name == "fake_eval")
    assert fake_check.reason_code == "fake_eval_manifest_invalid"


def test_malformed_performance_evidence_fails_closed_without_raising(
    tmp_path: Path,
) -> None:
    repo = _copy_release_surface(tmp_path)
    report_path = repo / "docs/evidence/r5/release/eval-report-fake.json"
    payload = orjson.loads(report_path.read_bytes())
    payload["performance"][0]["suites"] = None
    _write_authenticated_report(report_path, payload)

    report = build_release_preflight(repo)

    assert report.exit_code == 1
    fake_check = next(item for item in report.checks if item.name == "fake_eval")
    assert fake_check.reason_code == "fake_eval_manifest_invalid"


def test_missing_operational_evidence_fails_closed(tmp_path: Path) -> None:
    repo = _copy_release_surface(tmp_path)
    (repo / "docs/evidence/r5/release/release-exercises.json").unlink()

    report = build_release_preflight(repo)

    assert report.exit_code == 1
    assert report.failures == ("operational_exercises",)
    exercise_check = next(
        item for item in report.checks if item.name == "operational_exercises"
    )
    assert exercise_check.reason_code == "operational_evidence_missing"


def test_self_consistent_operational_result_forgery_fails_closed(
    tmp_path: Path,
) -> None:
    repo = _copy_release_surface(tmp_path)
    evidence_path = repo / "docs/evidence/r5/release/release-exercises.json"
    payload = orjson.loads(evidence_path.read_bytes())
    payload["exercises"][0]["result"] = "999 passed"
    identity = {key: value for key, value in payload.items() if key != "evidence_hash"}
    payload["evidence_hash"] = canonical_sha256(identity)
    evidence_path.write_bytes(canonical_bytes(payload))

    report = build_release_preflight(repo)

    assert report.exit_code == 1
    exercise_check = next(
        item for item in report.checks if item.name == "operational_exercises"
    )
    assert exercise_check.reason_code == "operational_exercise_failed"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reason_code", "forged_reason"),
        ("prohibited_actions_observed", {"not_a_real_safety_check": False}),
    ],
)
def test_approval_blocker_requires_exact_not_run_contract(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    repo = _copy_release_surface(tmp_path)
    status_path = repo / "docs/evidence/r5/release/sandbox-live-status.json"
    payload = orjson.loads(status_path.read_bytes())
    payload[field] = value
    status_path.write_bytes(canonical_bytes(payload))

    report = build_release_preflight(repo)

    assert report.exit_code == 1
    sandbox_check = next(item for item in report.checks if item.name == "sandbox_live")
    assert sandbox_check.status is ReleaseCheckStatus.FAILED


def test_cli_writes_the_same_blocked_report_without_running_external_systems(
    tmp_path: Path,
) -> None:
    output = tmp_path / "preflight.json"

    exit_code = main(
        (
            "--repo-root",
            str(REPO_ROOT),
            "--output",
            str(output),
        )
    )

    assert exit_code == 5
    assert output.read_bytes() == build_release_preflight(REPO_ROOT).to_bytes()
