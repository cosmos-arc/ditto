"""Remaining fail-closed edges for the R5 Agent release preflight."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import cast

import orjson
import pytest
from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_apps.scripts import _r5_agent_release_contract as contract
from ditto_apps.scripts import r5_agent_release_preflight as preflight

REPO_ROOT = Path(__file__).parents[5]
RELEASE_ROOT = REPO_ROOT / "docs/evidence/r5/release"


def _payload(name: str) -> dict[str, object]:
    parsed = orjson.loads((RELEASE_ROOT / name).read_bytes())
    assert isinstance(parsed, dict)
    return cast("dict[str, object]", parsed)


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(payload))


def _rehash(payload: dict[str, object], *, field: str = "report_hash") -> None:
    identity = {key: value for key, value in payload.items() if key != field}
    payload[field] = canonical_sha256(identity)


def _first_suite(payload: dict[str, object]) -> dict[str, object]:
    reports = cast("list[object]", payload["suite_reports"])
    return cast("dict[str, object]", reports[0])


def _approval_payload(*, gate: str, provider: str, profile: str) -> dict[str, object]:
    return {
        "approval_gate": gate,
        "profile": profile,
        "prohibited_actions_observed": dict.fromkeys(
            contract.EXPECTED_PROHIBITED_ACTIONS[gate, provider, profile], False
        ),
        "provider": provider,
        "reason_code": f"{gate.lower()}_approval_required",
        "release_gate_passed": False,
        "schema_version": 1,
        "status": "not_run",
    }


def _copy_interface_surface(repo: Path) -> None:
    for relative in (
        Path("contracts/openapi/v1.json"),
        Path("docs/operations/r5-agent-runbook.md"),
        Path("docs/security/r5-agent-security-boundary.md"),
        Path("docs/roadmaps/ditto-development-roadmap.md"),
    ):
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative, target)


def test_suite_evidence_rejects_unindexed_and_malformed_suite_reports() -> None:
    assert preflight._suite_evidence({}, provider_id=contract.FAKE_PROVIDER_ID) is None

    payload = _payload("eval-report-fake.json")
    report = _first_suite(payload)
    report["schema_version"] = 2
    assert (
        preflight._suite_evidence(payload, provider_id=contract.FAKE_PROVIDER_ID)
        is None
    )

    payload = _payload("eval-report-fake.json")
    report = _first_suite(payload)
    results = cast("list[object]", report["results"])
    results[0] = []
    _rehash(report)
    assert (
        preflight._suite_evidence(payload, provider_id=contract.FAKE_PROVIDER_ID)
        is None
    )


def test_suite_evidence_rejects_duplicate_results_and_grader_drift() -> None:
    payload = _payload("eval-report-fake.json")
    report = _first_suite(payload)
    results = cast("list[object]", report["results"])
    results[1] = deepcopy(results[0])
    _rehash(report)
    assert (
        preflight._suite_evidence(payload, provider_id=contract.FAKE_PROVIDER_ID)
        is None
    )

    payload = _payload("eval-report-fake.json")
    payload["grader_manifest_hash"] = "0" * 64
    assert (
        preflight._suite_evidence(payload, provider_id=contract.FAKE_PROVIDER_ID)
        is None
    )


def test_fake_eval_missing_invalid_and_rehashed_gate_drift_fail_closed(
    tmp_path: Path,
) -> None:
    missing = preflight._fake_eval_check(tmp_path / "missing.json")
    assert missing.reason_code == "fake_eval_evidence_missing"

    invalid_path = tmp_path / "invalid.json"
    _write(invalid_path, [])
    invalid = preflight._fake_eval_check(invalid_path)
    assert invalid.reason_code == "fake_eval_evidence_invalid"

    gate_path = tmp_path / "gate.json"
    payload = _payload("eval-report-fake.json")
    payload["profile"] = "not-fake"
    _rehash(payload)
    _write(gate_path, payload)
    gate = preflight._fake_eval_check(gate_path)
    assert gate.reason_code == "fake_eval_gate_failed"
    assert gate.status is preflight.ReleaseCheckStatus.FAILED


def test_operational_evidence_rejects_invalid_json_and_top_level_contract(
    tmp_path: Path,
) -> None:
    invalid_path = tmp_path / "invalid.json"
    _write(invalid_path, [])
    invalid = preflight._operational_check(invalid_path)
    assert invalid.reason_code == "operational_evidence_invalid"

    schema_path = tmp_path / "schema.json"
    payload = _payload("release-exercises.json")
    payload["schema_version"] = 2
    _rehash(payload, field="evidence_hash")
    _write(schema_path, payload)
    schema = preflight._operational_check(schema_path)
    assert schema.reason_code == "operational_evidence_invalid"


def test_operational_evidence_rejects_malformed_exercise_items(tmp_path: Path) -> None:
    path = tmp_path / "exercises.json"
    payload = _payload("release-exercises.json")
    exercises = cast("list[object]", payload["exercises"])
    exercises[0] = []
    _rehash(payload, field="evidence_hash")
    _write(path, payload)

    check = preflight._operational_check(path)

    assert check.reason_code == "operational_exercise_failed"
    assert check.status is preflight.ReleaseCheckStatus.FAILED


def test_interface_contracts_fail_closed_for_missing_and_invalid_evidence(
    tmp_path: Path,
) -> None:
    missing = preflight._interface_check(tmp_path / "missing")
    assert missing.reason_code == "release_document_missing"

    repo = tmp_path / "invalid"
    _copy_interface_surface(repo)
    _write(repo / "contracts/openapi/v1.json", [])
    invalid = preflight._interface_check(repo)
    assert invalid.reason_code == "interface_evidence_invalid"


def test_interface_contracts_require_all_agent_paths_and_cli_commands(
    tmp_path: Path,
) -> None:
    missing_paths_repo = tmp_path / "paths"
    _copy_interface_surface(missing_paths_repo)
    openapi_path = missing_paths_repo / "contracts/openapi/v1.json"
    openapi = cast("dict[str, object]", orjson.loads(openapi_path.read_bytes()))
    cast("dict[str, object]", openapi["paths"]).clear()
    _write(openapi_path, openapi)
    incomplete_api = preflight._interface_check(missing_paths_repo)
    assert incomplete_api.reason_code == "agent_openapi_incomplete"

    missing_cli_repo = tmp_path / "cli"
    _copy_interface_surface(missing_cli_repo)
    runbook_path = missing_cli_repo / "docs/operations/r5-agent-runbook.md"
    runbook = runbook_path.read_text(encoding="utf-8")
    token = contract.EXPECTED_CLI_TOKENS[-1]
    assert token in runbook
    runbook_path.write_text(runbook.replace(token, "agent cleanup"), encoding="utf-8")
    incomplete_cli = preflight._interface_check(missing_cli_repo)
    assert incomplete_cli.reason_code == "agent_cli_documentation_incomplete"


def test_approval_status_requires_parseable_exact_fail_closed_credentials(
    tmp_path: Path,
) -> None:
    path = tmp_path / "status.json"
    kwargs = {
        "name": "balanced_live_eval",
        "gate": "A4",
        "provider": "glm",
        "profile": "balanced",
    }
    missing = preflight._approval_status_check(path, **kwargs)
    assert missing.reason_code == "balanced_live_eval_evidence_missing"

    _write(path, [])
    invalid_json = preflight._approval_status_check(path, **kwargs)
    assert invalid_json.reason_code == "balanced_live_eval_evidence_invalid"

    payload = _approval_payload(gate="A4", provider="glm", profile="balanced")
    payload["unexpected"] = True
    _write(path, payload)
    unexpected = preflight._approval_status_check(path, **kwargs)
    assert unexpected.reason_code == "balanced_live_eval_status_invalid"

    payload = _approval_payload(gate="A4", provider="glm", profile="balanced")
    prohibited = cast("dict[str, object]", payload["prohibited_actions_observed"])
    prohibited["api_key_read"] = True
    _write(path, payload)
    observed = preflight._approval_status_check(path, **kwargs)
    assert observed.reason_code == "balanced_live_eval_status_invalid"


def test_valid_not_run_status_is_an_authenticated_approval_blocker(
    tmp_path: Path,
) -> None:
    path = tmp_path / "balanced-status.json"
    _write(
        path,
        _approval_payload(gate="A4", provider="glm", profile="balanced"),
    )

    check = preflight._approval_status_check(
        path,
        name="balanced_live_eval",
        gate="A4",
        provider="glm",
        profile="balanced",
    )

    assert check.status is preflight.ReleaseCheckStatus.BLOCKED
    assert check.reason_code == "a4_approval_required"
    assert check.approval_gate == "A4"
    assert check.evidence_hash == preflight._file_hash(path)


def test_live_eval_handles_missing_invalid_and_not_run_evidence(tmp_path: Path) -> None:
    kwargs = {
        "name": "balanced_live_eval",
        "profile": "balanced",
        "repo_root": REPO_ROOT,
    }
    path = tmp_path / "balanced.json"
    missing = preflight._live_eval_check(path, **kwargs)
    assert missing.reason_code == "balanced_live_eval_evidence_missing"

    _write(path, [])
    invalid = preflight._live_eval_check(path, **kwargs)
    assert invalid.reason_code == "balanced_live_eval_evidence_invalid"

    _write(path, _approval_payload(gate="A4", provider="glm", profile="balanced"))
    blocked = preflight._live_eval_check(path, **kwargs)
    assert blocked.status is preflight.ReleaseCheckStatus.BLOCKED
    assert blocked.approval_gate == "A4"


def test_live_eval_distinguishes_hash_failure_from_rehashed_gate_drift(
    tmp_path: Path,
) -> None:
    path = tmp_path / "balanced.json"
    kwargs = {
        "name": "balanced_live_eval",
        "profile": "balanced",
        "repo_root": REPO_ROOT,
    }
    payload = _payload("eval-report-balanced.json")
    payload["passed"] = False
    _write(path, payload)
    bad_hash = preflight._live_eval_check(path, **kwargs)
    assert bad_hash.reason_code == "balanced_live_eval_report_hash_invalid"

    payload = _payload("eval-report-balanced.json")
    payload["profile"] = "quality"
    _rehash(payload)
    _write(path, payload)
    gate_drift = preflight._live_eval_check(path, **kwargs)
    assert gate_drift.reason_code == "balanced_live_eval_gate_failed"


def test_sandbox_artifacts_reject_unreadable_and_incomplete_manifests(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    manifest = repo / "deploy/agent-sandbox/image-manifest.json"
    _write(manifest, [])
    assert not preflight._sandbox_artifacts_match(repo_root=repo, report={})

    _write(manifest, {"artifacts": {}})
    assert not preflight._sandbox_artifacts_match(repo_root=repo, report={})


def test_sandbox_live_handles_missing_invalid_and_not_run_evidence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sandbox.json"
    missing = preflight._sandbox_live_check(path, repo_root=tmp_path)
    assert missing.reason_code == "sandbox_live_evidence_missing"

    _write(path, [])
    invalid = preflight._sandbox_live_check(path, repo_root=tmp_path)
    assert invalid.reason_code == "sandbox_live_evidence_invalid"

    _write(path, _approval_payload(gate="A3", provider="oci", profile="hardened"))
    blocked = preflight._sandbox_live_check(path, repo_root=tmp_path)
    assert blocked.status is preflight.ReleaseCheckStatus.BLOCKED
    assert blocked.approval_gate == "A3"


def test_sandbox_live_converts_validator_errors_to_closed_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "sandbox.json"
    _write(path, {"status": "passed"})

    def _invalid_contract(_payload: Mapping[str, object]) -> bool:
        raise ValueError("malformed third-party validation input")

    monkeypatch.setattr(preflight, "validate_live_report", _invalid_contract)

    check = preflight._sandbox_live_check(path, repo_root=tmp_path)

    assert check.status is preflight.ReleaseCheckStatus.FAILED
    assert check.reason_code == "sandbox_live_evidence_invalid"


def test_cli_writes_canonical_report_to_stdout_when_output_is_omitted(
    capfd: pytest.CaptureFixture[str],
) -> None:
    expected = preflight.build_release_preflight(REPO_ROOT)

    exit_code = preflight.main(("--repo-root", str(REPO_ROOT)))

    captured = capfd.readouterr()
    assert exit_code == expected.exit_code
    assert captured.err == ""
    assert captured.out.encode() == expected.to_bytes() + b"\n"
