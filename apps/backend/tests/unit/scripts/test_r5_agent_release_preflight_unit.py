"""Fail-closed R5 Agent release-preflight evidence contracts."""

from __future__ import annotations

import asyncio
import shutil
from decimal import Decimal
from pathlib import Path

import orjson
from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.evals.cases import EvalCase, EvalObservation, load_eval_cases
from ditto_agent.evals.runner import bundled_eval_cases, run_live_release
from ditto_apps.registry.agent.release_eval_provider import (
    formal_prompt_tool_manifest_hash,
)
from ditto_apps.scripts.r5_agent_release_preflight import (
    ReleaseCheckStatus,
    build_release_preflight,
    main,
)
from ditto_apps.scripts.r5_release_eval import (
    FormalA4Scope,
    build_formal_run_identity,
)

REPO_ROOT = Path(__file__).parents[5]


def _copy_release_surface(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(
        REPO_ROOT / "docs" / "evidence" / "r5" / "release",
        repo / "docs" / "evidence" / "r5" / "release",
    )
    shutil.copytree(
        REPO_ROOT / "deploy" / "agent-sandbox",
        repo / "deploy" / "agent-sandbox",
    )
    for a4_evidence in (
        Path("docs/evidence/r5/preflight/glm-coding-plan-a4-materials.json"),
        Path("docs/evidence/r5/preflight/glm-coding-plan-a4-scope.json"),
    ):
        (repo / a4_evidence).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / a4_evidence, repo / a4_evidence)
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


class _PassingGlmProvider:
    provider_id = "glm-coding-plan-responses-v1"

    async def observe(self, case: EvalCase) -> EvalObservation:
        fixture = case.observation
        return EvalObservation(
            attempted_actions=fixture.attempted_actions,
            allowed_actions=fixture.allowed_actions,
            evidence_refs=fixture.evidence_refs,
            replay_identities=fixture.replay_identities,
            rule_assertions=fixture.rule_assertions,
            latency_ms=fixture.latency_ms,
            model_spend_usd=Decimal(0),
            model_requests=1,
            model_input_tokens=1,
            model_output_tokens=1,
            model_output_hash=canonical_sha256(
                {"case_id": case.case_id, "output": "passing-glm"}
            ),
        )


def _write_passing_glm_report(repo: Path, *, profile: str) -> None:
    cases = {
        suite: load_eval_cases(bundled_eval_cases(suite)[1])
        for suite in (
            "author",
            "campaign",
            "grounded",
            "permission",
            "sandbox",
            "shadow",
        )
    }
    scope = FormalA4Scope.load(
        repo / "docs/evidence/r5/preflight/glm-coding-plan-a4-scope.json"
    )
    identity = build_formal_run_identity(
        profile_name=profile,
        scope=scope,
        prompt_tool_manifest_hash=formal_prompt_tool_manifest_hash(),
    )
    report = asyncio.run(
        run_live_release(
            provider=_PassingGlmProvider(),
            run_identity=identity,
            seed=20_260_816,
            cases=cases,
        )
    )
    assert report.passed is True
    (repo / f"docs/evidence/r5/release/eval-report-{profile}.json").write_bytes(
        report.to_bytes()
    )


def test_current_preflight_accepts_both_refreshed_live_profiles() -> None:
    first = build_release_preflight(REPO_ROOT)
    second = build_release_preflight(REPO_ROOT)

    assert first.to_bytes() == second.to_bytes()
    assert first.passed is True
    assert first.exit_code == 0
    assert first.blockers == ()
    assert first.failures == ()
    checks = {item.name: item for item in first.checks}
    assert checks["fake_eval"].status is ReleaseCheckStatus.PASSED
    assert checks["operational_exercises"].status is ReleaseCheckStatus.PASSED
    assert checks["interface_contracts"].status is ReleaseCheckStatus.PASSED
    assert checks["sandbox_live"].status is ReleaseCheckStatus.PASSED
    assert checks["balanced_live_eval"].status is ReleaseCheckStatus.PASSED
    assert checks["quality_live_eval"].status is ReleaseCheckStatus.PASSED
    assert checks["balanced_live_eval"].reason_code == "balanced_live_eval_passed"
    assert checks["quality_live_eval"].reason_code == "quality_live_eval_passed"
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


def test_authenticated_glm_reports_accept_current_a4_dataset_scope(
    tmp_path: Path,
) -> None:
    repo = _copy_release_surface(tmp_path)
    _write_passing_glm_report(repo, profile="balanced")
    _write_passing_glm_report(repo, profile="quality")

    report = build_release_preflight(repo)

    assert report.exit_code == 0
    assert report.passed is True
    checks = {item.name: item for item in report.checks}
    assert checks["balanced_live_eval"].status is ReleaseCheckStatus.PASSED
    assert checks["quality_live_eval"].status is ReleaseCheckStatus.PASSED
    assert checks["balanced_live_eval"].reason_code == "balanced_live_eval_passed"
    assert checks["quality_live_eval"].reason_code == "quality_live_eval_passed"


def test_rehashed_live_report_cannot_hide_total_token_cap_overrun(
    tmp_path: Path,
) -> None:
    repo = _copy_release_surface(tmp_path)
    _write_passing_glm_report(repo, profile="balanced")
    report_path = repo / "docs/evidence/r5/release/eval-report-balanced.json"
    payload = orjson.loads(report_path.read_bytes())
    identity = payload["run_identity"]
    identity["max_total_tokens"] = 1
    identity["pricing_manifest_hash"] = canonical_sha256(
        {"cost_basis": "usage_cap", "max_total_tokens": 1, "version": 1}
    )
    identity["identity_hash"] = canonical_sha256(
        {key: value for key, value in identity.items() if key != "identity_hash"}
    )
    _write_authenticated_report(report_path, payload)

    report = build_release_preflight(repo)

    balanced = next(item for item in report.checks if item.name == "balanced_live_eval")
    assert balanced.status is ReleaseCheckStatus.FAILED
    assert balanced.reason_code == "balanced_live_eval_manifest_invalid"


def test_fully_rehashed_live_identity_cannot_replace_approved_a4_scope(
    tmp_path: Path,
) -> None:
    repo = _copy_release_surface(tmp_path)
    _write_passing_glm_report(repo, profile="balanced")
    scope_path = repo / "docs/evidence/r5/preflight/glm-coding-plan-a4-scope.json"
    scope_payload = orjson.loads(scope_path.read_bytes())
    scope_payload["max_total_tokens"] = 1_000
    scope_path.write_bytes(canonical_bytes(scope_payload))
    forged_scope = FormalA4Scope.load(scope_path)
    report_path = repo / "docs/evidence/r5/release/eval-report-balanced.json"
    payload = orjson.loads(report_path.read_bytes())
    identity = payload["run_identity"]
    identity["a4_scope_hash"] = forged_scope.scope_hash
    identity["max_total_tokens"] = forged_scope.max_total_tokens
    identity["pricing_manifest_hash"] = canonical_sha256(
        {
            "cost_basis": "usage_cap",
            "max_total_tokens": forged_scope.max_total_tokens,
            "version": 1,
        }
    )
    identity["identity_hash"] = canonical_sha256(
        {key: value for key, value in identity.items() if key != "identity_hash"}
    )
    _write_authenticated_report(report_path, payload)

    report = build_release_preflight(repo)

    balanced = next(item for item in report.checks if item.name == "balanced_live_eval")
    assert balanced.status is ReleaseCheckStatus.FAILED
    assert balanced.reason_code == "balanced_live_eval_manifest_invalid"


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


def test_self_consistent_total_spend_forgery_fails_closed(tmp_path: Path) -> None:
    repo = _copy_release_surface(tmp_path)
    report_path = repo / "docs/evidence/r5/release/eval-report-fake.json"
    payload = orjson.loads(report_path.read_bytes())
    payload["total_model_spend_usd"] = "0"
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


def test_release_roadmap_must_record_the_completed_gate(tmp_path: Path) -> None:
    repo = _copy_release_surface(tmp_path)
    roadmap_path = repo / "docs/roadmaps/ditto-development-roadmap.md"
    roadmap_path.write_text(
        roadmap_path.read_text(encoding="utf-8").replace(
            "R5.5 COMPLETE",
            "R5.5 STATUS MISSING",
        ),
        encoding="utf-8",
    )

    report = build_release_preflight(repo)

    assert report.exit_code == 1
    interface_check = next(
        item for item in report.checks if item.name == "interface_contracts"
    )
    assert interface_check.reason_code == "release_document_status_inconsistent"


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


def test_self_consistent_sandbox_attack_forgery_fails_closed(tmp_path: Path) -> None:
    repo = _copy_release_surface(tmp_path)
    status_path = repo / "docs/evidence/r5/release/sandbox-live-status.json"
    payload = orjson.loads(status_path.read_bytes())
    payload["attack_results"][0]["observation"]["blocked"] = False
    _write_authenticated_report(status_path, payload)

    report = build_release_preflight(repo)

    assert report.exit_code == 1
    sandbox_check = next(item for item in report.checks if item.name == "sandbox_live")
    assert sandbox_check.status is ReleaseCheckStatus.FAILED
    assert sandbox_check.reason_code == "sandbox_live_evidence_invalid"


def test_sandbox_artifact_hash_drift_fails_closed(tmp_path: Path) -> None:
    repo = _copy_release_surface(tmp_path)
    seccomp_path = repo / "deploy/agent-sandbox/seccomp.json"
    seccomp_path.write_bytes(seccomp_path.read_bytes() + b"\n")

    report = build_release_preflight(repo)

    assert report.exit_code == 1
    sandbox_check = next(item for item in report.checks if item.name == "sandbox_live")
    assert sandbox_check.status is ReleaseCheckStatus.FAILED
    assert sandbox_check.reason_code == "sandbox_live_artifact_mismatch"


def test_cli_writes_the_same_passing_report_without_external_systems(
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

    assert exit_code == 0
    assert output.read_bytes() == build_release_preflight(REPO_ROOT).to_bytes()
