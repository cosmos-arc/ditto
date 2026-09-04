"""Focused fail-closed edges for the R5 release-preflight validators."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_apps.scripts import _r5_agent_release_contract as contract
from ditto_apps.scripts import r5_agent_release_preflight as preflight


def _check(
    name: str,
    *,
    status: preflight.ReleaseCheckStatus = preflight.ReleaseCheckStatus.PASSED,
    approval_gate: str | None = None,
) -> preflight.ReleaseCheck:
    return preflight.ReleaseCheck(
        name=name,
        status=status,
        reason_code=f"{name}_reason",
        evidence_hash="a" * 64,
        approval_gate=approval_gate,
    )


def _ordered_checks(
    *,
    failed: str | None = None,
    blocked: str | None = None,
) -> tuple[preflight.ReleaseCheck, ...]:
    return tuple(
        _check(
            name,
            status=(
                preflight.ReleaseCheckStatus.FAILED
                if name == failed
                else (
                    preflight.ReleaseCheckStatus.BLOCKED
                    if name == blocked
                    else preflight.ReleaseCheckStatus.PASSED
                )
            ),
            approval_gate="A4" if name == blocked else None,
        )
        for name in contract.CHECK_ORDER
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"name": " "}, "check name"),
        ({"reason_code": " "}, "reason_code"),
        ({"status": cast(preflight.ReleaseCheckStatus, "passed")}, "status"),
        ({"evidence_hash": "not-a-hash"}, "evidence_hash"),
        ({"approval_gate": " "}, "approval_gate"),
        (
            {"status": preflight.ReleaseCheckStatus.BLOCKED},
            "only blocked checks",
        ),
        ({"approval_gate": "A4"}, "only blocked checks"),
    ],
)
def test_release_check_rejects_malformed_identity_fields(
    kwargs: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "name": "fake_eval",
        "status": preflight.ReleaseCheckStatus.PASSED,
        "reason_code": "checked",
        "evidence_hash": "a" * 64,
        "approval_gate": None,
    }
    values.update(kwargs)

    constructor = cast(
        "Callable[..., preflight.ReleaseCheck]",
        preflight.ReleaseCheck,
    )
    with pytest.raises(ValueError, match=message):
        constructor(**values)


def test_release_report_enforces_schema_order_and_authenticated_bytes() -> None:
    checks = _ordered_checks()

    with pytest.raises(ValueError, match="schema_version"):
        preflight.ReleasePreflightReport(checks=checks, schema_version=2)
    with pytest.raises(ValueError, match="exact ordered checks"):
        preflight.ReleasePreflightReport(checks=tuple(reversed(checks)))

    report = preflight.ReleasePreflightReport(checks=checks)
    object.__setattr__(report, "report_hash", "0" * 64)
    with pytest.raises(ValueError, match="report hash"):
        report.to_bytes()


def test_release_report_prioritizes_failures_over_approval_blocks() -> None:
    report = preflight.ReleasePreflightReport(
        checks=_ordered_checks(
            failed="fake_eval",
            blocked="balanced_live_eval",
        )
    )

    assert report.failures == ("fake_eval",)
    assert report.blockers == ("A4",)
    assert report.exit_code == 1
    assert report.release_status == "failed"
    assert report.passed is False

    blocked = preflight.ReleasePreflightReport(
        checks=_ordered_checks(blocked="balanced_live_eval")
    )
    assert blocked.exit_code == 5
    assert blocked.release_status == "blocked"


def test_file_and_json_helpers_fail_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    assert preflight._file_hash(missing) is None
    assert preflight._object_list(()) is None
    assert preflight._string_mapping([]) is None

    array_path = tmp_path / "array.json"
    array_path.write_bytes(canonical_bytes(["not", "an", "object"]))
    with pytest.raises(ValueError, match="JSON root"):
        preflight._read_mapping(array_path)

    assert preflight._report_hash_valid({}) is False
    assert preflight._report_hash_valid({"report_hash": 7}) is False
    assert preflight._report_hash_valid({"report_hash": "0" * 64}) is False
    identity = {"schema_version": 1, "passed": True}
    assert preflight._report_hash_valid(
        {**identity, "report_hash": canonical_sha256(identity)}
    )


def _suite_index_payload() -> dict[str, object]:
    return {
        "suite_reports": [
            {"suite": suite} for suite in sorted(contract.EXPECTED_COUNTS)
        ]
    }


def test_suite_report_index_rejects_structural_ambiguity() -> None:
    assert preflight._indexed_suite_reports({}) is None
    assert preflight._indexed_suite_reports({"suite_reports": []}) is None

    payload = _suite_index_payload()
    reports = cast(list[object], payload["suite_reports"])
    reports[0] = []
    assert preflight._indexed_suite_reports(payload) is None

    payload = _suite_index_payload()
    reports = cast(list[dict[str, object]], payload["suite_reports"])
    reports[0]["suite"] = 7
    assert preflight._indexed_suite_reports(payload) is None

    payload = _suite_index_payload()
    reports = cast(list[dict[str, object]], payload["suite_reports"])
    reports[1]["suite"] = reports[0]["suite"]
    assert preflight._indexed_suite_reports(payload) is None

    payload = _suite_index_payload()
    reports = cast(list[dict[str, object]], payload["suite_reports"])
    reports[0]["suite"] = "unexpected"
    assert preflight._indexed_suite_reports(payload) is None
    assert set(preflight._indexed_suite_reports(_suite_index_payload()) or ()) == set(
        contract.EXPECTED_COUNTS
    )


def _valid_result() -> dict[str, object]:
    identity: dict[str, object] = {
        "case_id": "case-1",
        "case_hash": "a" * 64,
        "input_hash": "b" * 64,
        "observation_hash": "c" * 64,
        "passed": True,
    }
    return {**identity, "result_hash": canonical_sha256(identity)}


def test_result_identity_rejects_untrusted_result_fields() -> None:
    result = _valid_result()
    assert preflight._result_identity(result) == (
        ("case-1", "b" * 64, "a" * 64),
        "c" * 64,
    )

    for field, value in (
        ("case_id", 1),
        ("case_hash", "bad"),
        ("input_hash", "bad"),
        ("observation_hash", "bad"),
        ("result_hash", "bad"),
        ("passed", False),
    ):
        malformed = {**result, field: value}
        assert preflight._result_identity(malformed) is None


def _valid_metric_summaries(suite: str) -> list[dict[str, object]]:
    return [
        {
            "metric": metric,
            "threshold_basis_points": threshold,
            "passed": True,
        }
        for metric, threshold in contract.EXPECTED_THRESHOLDS[suite].items()
    ]


def test_metric_thresholds_require_exact_passing_manifest() -> None:
    suite = "author"
    summaries = _valid_metric_summaries(suite)
    assert preflight._metric_thresholds_valid(
        suite,
        {"metric_summaries": summaries},
    )
    assert not preflight._metric_thresholds_valid(suite, {})
    assert not preflight._metric_thresholds_valid(
        suite,
        {"metric_summaries": summaries[:-1]},
    )
    assert not preflight._metric_thresholds_valid(
        suite,
        {"metric_summaries": [[], summaries[1]]},
    )
    failed = deepcopy(summaries)
    failed[0]["passed"] = False
    assert not preflight._metric_thresholds_valid(
        suite,
        {"metric_summaries": failed},
    )
    wrong = deepcopy(summaries)
    wrong[0]["threshold_basis_points"] = 0
    assert not preflight._metric_thresholds_valid(
        suite,
        {"metric_summaries": wrong},
    )


def _empty_suite_evidence() -> preflight._SuiteEvidence:
    return preflight._SuiteEvidence(
        dataset_identities=dict.fromkeys(contract.EXPECTED_COUNTS, ()),
        observation_identities=(),
        grader_manifest_hash="d" * 64,
    )


def _empty_dataset_payload() -> dict[str, object]:
    manifest: list[object] = [
        {"suite": suite, "cases": []} for suite in sorted(contract.EXPECTED_COUNTS)
    ]
    return {
        "dataset_manifest": manifest,
        "dataset_manifest_hash": canonical_sha256(manifest),
    }


def test_dataset_manifest_rejects_every_untrusted_shape() -> None:
    evidence = _empty_suite_evidence()
    assert preflight._dataset_manifest_valid(_empty_dataset_payload(), evidence)
    assert not preflight._dataset_manifest_valid({}, evidence)

    payload = _empty_dataset_payload()
    cast(list[object], payload["dataset_manifest"])[0] = []
    payload["dataset_manifest_hash"] = canonical_sha256(payload["dataset_manifest"])
    assert not preflight._dataset_manifest_valid(payload, evidence)

    payload = _empty_dataset_payload()
    first = cast(list[dict[str, object]], payload["dataset_manifest"])[0]
    first["suite"] = 1
    payload["dataset_manifest_hash"] = canonical_sha256(payload["dataset_manifest"])
    assert not preflight._dataset_manifest_valid(payload, evidence)

    payload = _empty_dataset_payload()
    first = cast(list[dict[str, object]], payload["dataset_manifest"])[0]
    first["cases"] = [[]]
    payload["dataset_manifest_hash"] = canonical_sha256(payload["dataset_manifest"])
    assert not preflight._dataset_manifest_valid(payload, evidence)

    payload = _empty_dataset_payload()
    first = cast(list[dict[str, object]], payload["dataset_manifest"])[0]
    first["cases"] = [{"case_id": 1, "input_hash": "b", "case_hash": "c"}]
    payload["dataset_manifest_hash"] = canonical_sha256(payload["dataset_manifest"])
    assert not preflight._dataset_manifest_valid(payload, evidence)


def _observation_payload() -> tuple[dict[str, object], preflight._SuiteEvidence]:
    rows: list[object] = []
    identities: list[tuple[str, str, str]] = []
    for index in range(contract.EXPECTED_CASE_COUNT):
        observation: dict[str, object] = {"index": index}
        observation_hash = canonical_sha256(observation)
        case_id = f"case-{index}"
        rows.append(
            {
                "suite": "author",
                "case_id": case_id,
                "observation_hash": observation_hash,
                "observation": observation,
            }
        )
        identities.append(("author", case_id, observation_hash))
    payload = {
        "observation_manifest": rows,
        "observation_manifest_hash": canonical_sha256(rows),
    }
    evidence = preflight._SuiteEvidence(
        dataset_identities={},
        observation_identities=tuple(identities),
        grader_manifest_hash="d" * 64,
    )
    return payload, evidence


def test_observation_manifest_rejects_every_untrusted_shape() -> None:
    payload, evidence = _observation_payload()
    assert preflight._observation_manifest_valid(payload, evidence)
    assert not preflight._observation_manifest_valid({}, evidence)

    malformed, evidence = _observation_payload()
    malformed["observation_manifest_hash"] = "0" * 64
    assert not preflight._observation_manifest_valid(malformed, evidence)

    malformed, evidence = _observation_payload()
    cast(list[object], malformed["observation_manifest"])[0] = []
    malformed["observation_manifest_hash"] = canonical_sha256(
        malformed["observation_manifest"]
    )
    assert not preflight._observation_manifest_valid(malformed, evidence)

    malformed, evidence = _observation_payload()
    row = cast(list[dict[str, object]], malformed["observation_manifest"])[0]
    row["case_id"] = 1
    malformed["observation_manifest_hash"] = canonical_sha256(
        malformed["observation_manifest"]
    )
    assert not preflight._observation_manifest_valid(malformed, evidence)

    malformed, evidence = _observation_payload()
    row = cast(list[dict[str, object]], malformed["observation_manifest"])[0]
    row["observation"] = []
    malformed["observation_manifest_hash"] = canonical_sha256(
        malformed["observation_manifest"]
    )
    assert not preflight._observation_manifest_valid(malformed, evidence)

    malformed, evidence = _observation_payload()
    row = cast(list[dict[str, object]], malformed["observation_manifest"])[0]
    row["observation_hash"] = "0" * 64
    malformed["observation_manifest_hash"] = canonical_sha256(
        malformed["observation_manifest"]
    )
    assert not preflight._observation_manifest_valid(malformed, evidence)
