"""Build the fail-closed R5 Agent release-preflight report."""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import cast

import orjson
from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.contracts._validation import normalized_text, sha256_hex

from ditto_apps.scripts._r5_agent_release_contract import (
    CHECK_ORDER as _CHECK_ORDER,
)
from ditto_apps.scripts._r5_agent_release_contract import (
    EXPECTED_AGENT_PATHS as _EXPECTED_AGENT_PATHS,
)
from ditto_apps.scripts._r5_agent_release_contract import (
    EXPECTED_CASE_COUNT as _EXPECTED_CASE_COUNT,
)
from ditto_apps.scripts._r5_agent_release_contract import (
    EXPECTED_CLI_TOKENS as _EXPECTED_CLI_TOKENS,
)
from ditto_apps.scripts._r5_agent_release_contract import (
    EXPECTED_COUNTS as _EXPECTED_COUNTS,
)
from ditto_apps.scripts._r5_agent_release_contract import (
    EXPECTED_EXERCISES as _EXPECTED_EXERCISES,
)
from ditto_apps.scripts._r5_agent_release_contract import (
    EXPECTED_PROHIBITED_ACTIONS as _EXPECTED_PROHIBITED_ACTIONS,
)
from ditto_apps.scripts._r5_agent_release_contract import (
    EXPECTED_THRESHOLDS as _EXPECTED_THRESHOLDS,
)
from ditto_apps.scripts._r5_agent_release_contract import (
    FAKE_PROVIDER_ID as _FAKE_PROVIDER_ID,
)
from ditto_apps.scripts._r5_agent_release_contract import (
    FAKE_SEED as _FAKE_SEED,
)
from ditto_apps.scripts._r5_agent_release_contract import (
    FROZEN_FAKE_IDENTITIES as _FROZEN_FAKE_IDENTITIES,
)
from ditto_apps.scripts._r5_agent_release_contract import (
    FROZEN_OPERATION_EVIDENCE_HASH as _FROZEN_OPERATION_EVIDENCE_HASH,
)


class ReleaseCheckStatus(StrEnum):
    """Closed result vocabulary for one release preflight check."""

    PASSED = "passed"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ReleaseCheck:
    """One content-addressed release fact, blocker, or failure."""

    name: str
    status: ReleaseCheckStatus
    reason_code: str
    evidence_hash: str | None
    approval_gate: str | None = None

    def __post_init__(self) -> None:
        """Normalize fields and enforce blocked-check approval semantics."""
        object.__setattr__(self, "name", normalized_text(self.name, field="check name"))
        object.__setattr__(
            self,
            "reason_code",
            normalized_text(self.reason_code, field="reason_code"),
        )
        status = cast(object, self.status)
        if not isinstance(status, ReleaseCheckStatus):
            raise ValueError("release check status is invalid")
        if self.evidence_hash is not None:
            object.__setattr__(
                self,
                "evidence_hash",
                sha256_hex(self.evidence_hash, field="evidence_hash"),
            )
        if self.approval_gate is not None:
            object.__setattr__(
                self,
                "approval_gate",
                normalized_text(self.approval_gate, field="approval_gate"),
            )
        if (self.status is ReleaseCheckStatus.BLOCKED) != (
            self.approval_gate is not None
        ):
            raise ValueError("only blocked checks may carry an approval gate")

    def identity_payload(self) -> dict[str, object]:
        """Return the fields authenticated by the enclosing report."""
        return {
            "name": self.name,
            "status": self.status,
            "reason_code": self.reason_code,
            "evidence_hash": self.evidence_hash,
            "approval_gate": self.approval_gate,
        }


@dataclass(frozen=True, slots=True)
class ReleasePreflightReport:
    """Deterministic report that can pass only when every hard gate passes."""

    checks: tuple[ReleaseCheck, ...]
    schema_version: int = 1
    schema_id: str = field(init=False, default="r5-agent-release-preflight")
    blockers: tuple[str, ...] = field(init=False)
    failures: tuple[str, ...] = field(init=False)
    passed: bool = field(init=False)
    report_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Derive the fail-closed release result and its content hash."""
        if self.schema_version != 1:
            raise ValueError("release preflight schema_version is unsupported")
        if tuple(item.name for item in self.checks) != _CHECK_ORDER:
            raise ValueError("release preflight requires the exact ordered checks")
        blockers = tuple(
            sorted(
                {
                    cast(str, item.approval_gate)
                    for item in self.checks
                    if item.status is ReleaseCheckStatus.BLOCKED
                }
            )
        )
        failures = tuple(
            item.name
            for item in self.checks
            if item.status is ReleaseCheckStatus.FAILED
        )
        object.__setattr__(self, "blockers", blockers)
        object.__setattr__(self, "failures", failures)
        object.__setattr__(
            self,
            "passed",
            all(item.status is ReleaseCheckStatus.PASSED for item in self.checks),
        )
        object.__setattr__(
            self,
            "report_hash",
            canonical_sha256(self.identity_payload()),
        )

    @property
    def exit_code(self) -> int:
        """Return 0 for pass, 1 for invalid evidence, or 5 for approval blocks."""
        if self.failures:
            return 1
        if self.blockers:
            return 5
        return 0

    @property
    def release_status(self) -> str:
        """Return the stable human-readable aggregate status."""
        if self.failures:
            return "failed"
        if self.blockers:
            return "blocked"
        return "passed"

    def identity_payload(self) -> dict[str, object]:
        """Return every field covered by ``report_hash``."""
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "checks": tuple(item.identity_payload() for item in self.checks),
            "blockers": self.blockers,
            "failures": self.failures,
            "release_status": self.release_status,
            "passed": self.passed,
        }

    def to_bytes(self) -> bytes:
        """Render canonical JSON after verifying the derived report hash."""
        if self.report_hash != canonical_sha256(self.identity_payload()):
            raise ValueError("release preflight report hash is invalid")
        return canonical_bytes(
            {**self.identity_payload(), "report_hash": self.report_hash}
        )


def _file_hash(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _object_list(value: object) -> list[object] | None:
    if not isinstance(value, list):
        return None
    return cast(list[object], value)


def _string_mapping(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    return cast(Mapping[str, object], value)


def _read_mapping(path: Path) -> Mapping[str, object]:
    payload = _string_mapping(cast(object, orjson.loads(path.read_bytes())))
    if payload is None:
        raise ValueError("JSON root must be an object")
    return payload


def _failed(name: str, reason_code: str, path: Path) -> ReleaseCheck:
    return ReleaseCheck(
        name=name,
        status=ReleaseCheckStatus.FAILED,
        reason_code=reason_code,
        evidence_hash=_file_hash(path),
    )


@dataclass(frozen=True, slots=True)
class _SuiteEvidence:
    dataset_identities: Mapping[str, tuple[tuple[str, str, str], ...]]
    observation_identities: tuple[tuple[str, str, str], ...]
    grader_manifest_hash: str


def _report_hash_valid(payload: Mapping[str, object]) -> bool:
    report_hash = payload.get("report_hash")
    if not isinstance(report_hash, str):
        return False
    identity = {key: value for key, value in payload.items() if key != "report_hash"}
    return report_hash == canonical_sha256(identity)


def _indexed_suite_reports(
    payload: Mapping[str, object],
) -> Mapping[str, Mapping[str, object]] | None:
    reports = _object_list(payload.get("suite_reports"))
    if reports is None or len(reports) != len(_EXPECTED_COUNTS):
        return None
    by_suite: dict[str, Mapping[str, object]] = {}
    for raw_report in reports:
        report = _string_mapping(raw_report)
        if report is None:
            return None
        suite = report.get("suite")
        if not isinstance(suite, str) or suite in by_suite:
            return None
        by_suite[suite] = report
    if set(by_suite) != set(_EXPECTED_COUNTS):
        return None
    return by_suite


def _result_identity(
    result: Mapping[str, object],
) -> tuple[tuple[str, str, str], str] | None:
    case_id = result.get("case_id")
    case_hash = result.get("case_hash")
    input_hash = result.get("input_hash")
    observation_hash = result.get("observation_hash")
    result_hash = result.get("result_hash")
    if not all(
        isinstance(item, str)
        for item in (case_id, case_hash, input_hash, observation_hash, result_hash)
    ):
        return None
    try:
        normalized_case_id = normalized_text(cast(str, case_id), field="case_id")
        normalized_case_hash = sha256_hex(cast(str, case_hash), field="case_hash")
        normalized_input_hash = sha256_hex(cast(str, input_hash), field="input_hash")
        normalized_observation_hash = sha256_hex(
            cast(str, observation_hash), field="observation_hash"
        )
        normalized_result_hash = sha256_hex(cast(str, result_hash), field="result_hash")
    except ValueError:
        return None
    identity = {key: value for key, value in result.items() if key != "result_hash"}
    if (
        normalized_result_hash != canonical_sha256(identity)
        or result.get("passed") is not True
    ):
        return None
    return (
        (normalized_case_id, normalized_input_hash, normalized_case_hash),
        normalized_observation_hash,
    )


def _metric_thresholds_valid(suite: str, report: Mapping[str, object]) -> bool:
    summaries = _object_list(report.get("metric_summaries"))
    if summaries is None or len(summaries) != len(_EXPECTED_THRESHOLDS[suite]):
        return False
    thresholds: dict[object, object] = {}
    for raw_summary in summaries:
        item = _string_mapping(raw_summary)
        if item is None or item.get("passed") is not True:
            return False
        thresholds[item.get("metric")] = item.get("threshold_basis_points")
    return thresholds == _EXPECTED_THRESHOLDS[suite]


def _suite_evidence(payload: Mapping[str, object]) -> _SuiteEvidence | None:
    by_suite = _indexed_suite_reports(payload)
    if by_suite is None:
        return None
    dataset_identities: dict[str, tuple[tuple[str, str, str], ...]] = {}
    observation_identities: list[tuple[str, str, str]] = []
    for suite in sorted(_EXPECTED_COUNTS):
        report = by_suite[suite]
        expected_count = _EXPECTED_COUNTS[suite]
        results = _object_list(report.get("results"))
        if (
            report.get("schema_version") != 1
            or report.get("provider_id") != _FAKE_PROVIDER_ID
            or report.get("seed") != _FAKE_SEED
            or report.get("minimum_case_count") != expected_count
            or report.get("case_count") != expected_count
            or report.get("passed") is not True
            or results is None
            or len(results) != expected_count
            or not _report_hash_valid(report)
            or not _metric_thresholds_valid(suite, report)
        ):
            return None
        identities: list[tuple[str, str, str]] = []
        case_ids: set[str] = set()
        for raw_result in results:
            result = _string_mapping(raw_result)
            if result is None:
                return None
            identity = _result_identity(result)
            if identity is None or identity[0][0] in case_ids:
                return None
            case_ids.add(identity[0][0])
            identities.append(identity[0])
            observation_identities.append((suite, identity[0][0], identity[1]))
        dataset_identities[suite] = tuple(identities)
    grader_manifest_hash = canonical_sha256(
        tuple(
            (suite, by_suite[suite].get("grader_manifest_hash"))
            for suite in sorted(by_suite)
        )
    )
    if payload.get("grader_manifest_hash") != grader_manifest_hash:
        return None
    return _SuiteEvidence(
        dataset_identities=dataset_identities,
        observation_identities=tuple(observation_identities),
        grader_manifest_hash=grader_manifest_hash,
    )


def _dataset_manifest_valid(
    payload: Mapping[str, object],
    suite_evidence: _SuiteEvidence,
) -> bool:
    manifest = _object_list(payload.get("dataset_manifest"))
    if (
        manifest is None
        or len(manifest) != len(_EXPECTED_COUNTS)
        or payload.get("dataset_manifest_hash") != canonical_sha256(manifest)
    ):
        return False
    actual: dict[str, tuple[tuple[str, str, str], ...]] = {}
    for raw_suite in manifest:
        suite_manifest = _string_mapping(raw_suite)
        if suite_manifest is None:
            return False
        suite = suite_manifest.get("suite")
        cases = _object_list(suite_manifest.get("cases"))
        if not isinstance(suite, str) or suite in actual or cases is None:
            return False
        identities: list[tuple[str, str, str]] = []
        for raw_case in cases:
            case = _string_mapping(raw_case)
            if case is None:
                return False
            case_id = case.get("case_id")
            input_hash = case.get("input_hash")
            case_hash = case.get("case_hash")
            if not all(
                isinstance(item, str) for item in (case_id, input_hash, case_hash)
            ):
                return False
            identities.append(
                (cast(str, case_id), cast(str, input_hash), cast(str, case_hash))
            )
        actual[suite] = tuple(identities)
    return actual == suite_evidence.dataset_identities


def _observation_manifest_valid(
    payload: Mapping[str, object],
    suite_evidence: _SuiteEvidence,
) -> bool:
    manifest = _object_list(payload.get("observation_manifest"))
    if manifest is None or len(manifest) != _EXPECTED_CASE_COUNT:
        return False
    if payload.get("observation_manifest_hash") != canonical_sha256(manifest):
        return False
    identities: list[tuple[str, str, str]] = []
    for raw_row in manifest:
        row = _string_mapping(raw_row)
        if row is None:
            return False
        suite = row.get("suite")
        case_id = row.get("case_id")
        observation_hash = row.get("observation_hash")
        observation = _string_mapping(row.get("observation"))
        if (
            not all(
                isinstance(item, str) for item in (suite, case_id, observation_hash)
            )
            or observation is None
        ):
            return False
        if observation_hash != canonical_sha256(observation):
            return False
        identities.append(
            (cast(str, suite), cast(str, case_id), cast(str, observation_hash))
        )
    return tuple(identities) == suite_evidence.observation_identities


def _cohort_performance_valid(
    item: Mapping[str, object],
    *,
    suites: tuple[str, ...],
    count: int,
    latency_limit: int,
    spend_limit: Decimal,
) -> bool:
    raw_suites = _object_list(item.get("suites"))
    if raw_suites is None or not all(isinstance(suite, str) for suite in raw_suites):
        return False
    try:
        p95 = int(cast(int, item.get("latency_p95_ms")))
        maximum = Decimal(cast(str, item.get("max_spend_usd")))
        observed_limit = Decimal(cast(str, item.get("spend_limit_usd")))
    except (InvalidOperation, TypeError, ValueError):
        return False
    return (
        tuple(cast(str, suite) for suite in raw_suites) == suites
        and item.get("case_count") == count
        and item.get("latency_limit_ms") == latency_limit
        and observed_limit == spend_limit
        and p95 <= latency_limit
        and maximum <= spend_limit
        and item.get("passed") is True
    )


def _performance_valid(payload: Mapping[str, object]) -> bool:
    performance = _object_list(payload.get("performance"))
    if performance is None:
        return False
    cohorts: dict[str, Mapping[str, object]] = {}
    for raw_item in performance:
        item = _string_mapping(raw_item)
        if item is None or not isinstance(item.get("cohort"), str):
            return False
        cohorts[cast(str, item["cohort"])] = item
    expected = {
        "read": (("grounded",), 30, 30_000, Decimal("0.25")),
        "complex": (
            ("author", "permission", "sandbox", "shadow"),
            60,
            60_000,
            Decimal("0.75"),
        ),
    }
    if set(cohorts) != set(expected):
        return False
    if not all(
        _cohort_performance_valid(
            cohorts[cohort],
            suites=suites,
            count=count,
            latency_limit=latency_limit,
            spend_limit=spend_limit,
        )
        for cohort, (suites, count, latency_limit, spend_limit) in expected.items()
    ):
        return False
    return payload.get("campaign_budget") == {
        "case_count": 30,
        "policy": "campaign_authorization_budget",
        "suite": "campaign",
    }


def _fake_eval_check(path: Path) -> ReleaseCheck:
    name = "fake_eval"
    if not path.is_file():
        return _failed(name, "fake_eval_evidence_missing", path)
    try:
        payload = _read_mapping(path)
    except (OSError, ValueError, orjson.JSONDecodeError):
        return _failed(name, "fake_eval_evidence_invalid", path)
    if not _report_hash_valid(payload):
        return _failed(name, "fake_eval_report_hash_invalid", path)
    if (
        payload.get("schema_version") != 1
        or payload.get("suite") != "all"
        or payload.get("profile") != "fake"
        or payload.get("provider_id") != _FAKE_PROVIDER_ID
        or payload.get("seed") != _FAKE_SEED
        or payload.get("case_count") != _EXPECTED_CASE_COUNT
        or payload.get("suite_case_counts") != _EXPECTED_COUNTS
        or payload.get("passed") is not True
    ):
        return _failed(name, "fake_eval_gate_failed", path)
    suite_evidence = _suite_evidence(payload)
    manifests_valid = suite_evidence is not None and all(
        (
            _dataset_manifest_valid(payload, suite_evidence),
            _observation_manifest_valid(payload, suite_evidence),
            _performance_valid(payload),
        )
    )
    frozen_identity_mismatch = any(
        payload.get(field) != value for field, value in _FROZEN_FAKE_IDENTITIES.items()
    )
    if not manifests_valid or frozen_identity_mismatch:
        reason_code = (
            "fake_eval_manifest_invalid"
            if not manifests_valid
            else "fake_eval_frozen_identity_mismatch"
        )
        return _failed(name, reason_code, path)
    return ReleaseCheck(
        name=name,
        status=ReleaseCheckStatus.PASSED,
        reason_code="fake_eval_passed",
        evidence_hash=cast(str, _file_hash(path)),
    )


def _operational_check(path: Path) -> ReleaseCheck:
    name = "operational_exercises"
    if not path.is_file():
        return _failed(name, "operational_evidence_missing", path)
    try:
        payload = _read_mapping(path)
    except (OSError, ValueError, orjson.JSONDecodeError):
        return _failed(name, "operational_evidence_invalid", path)
    supplied_hash = payload.get("evidence_hash")
    identity = {key: value for key, value in payload.items() if key != "evidence_hash"}
    exercises = _object_list(payload.get("exercises"))
    if (
        not isinstance(supplied_hash, str)
        or supplied_hash != canonical_sha256(identity)
        or payload.get("schema_id") != "r5-release-operational-exercises"
        or payload.get("schema_version") != 1
        or payload.get("real_data_touched") is not False
        or exercises is None
        or len(exercises) != len(_EXPECTED_EXERCISES)
    ):
        return _failed(name, "operational_evidence_invalid", path)
    by_name: dict[str, Mapping[str, object]] = {}
    for raw_item in exercises:
        item = _string_mapping(raw_item)
        if item is None or not isinstance(item.get("name"), str):
            return _failed(name, "operational_exercise_failed", path)
        by_name[cast(str, item["name"])] = item
    if (
        set(by_name) != _EXPECTED_EXERCISES
        or any(
            item.get("status") != "passed"
            or not isinstance(item.get("command"), str)
            or not isinstance(item.get("result"), str)
            or not isinstance(item.get("safety_boundary"), str)
            for item in by_name.values()
        )
        or supplied_hash != _FROZEN_OPERATION_EVIDENCE_HASH
    ):
        return _failed(name, "operational_exercise_failed", path)
    return ReleaseCheck(
        name=name,
        status=ReleaseCheckStatus.PASSED,
        reason_code="operational_exercises_passed",
        evidence_hash=cast(str, _file_hash(path)),
    )


def _interface_check(repo_root: Path) -> ReleaseCheck:
    name = "interface_contracts"
    openapi_path = repo_root / "docs/openapi/v1.json"
    runbook_path = repo_root / "docs/operations/r5-agent-runbook.md"
    security_path = repo_root / "docs/security/r5-agent-security-boundary.md"
    roadmap_path = repo_root / "docs/roadmaps/ditto-development-roadmap.md"
    paths = (openapi_path, runbook_path, security_path, roadmap_path)
    if any(not path.is_file() for path in paths):
        return _failed(name, "release_document_missing", runbook_path)
    try:
        openapi = _read_mapping(openapi_path)
        api_paths = _string_mapping(openapi.get("paths"))
        runbook = runbook_path.read_text(encoding="utf-8")
        security = security_path.read_text(encoding="utf-8")
        roadmap = roadmap_path.read_text(encoding="utf-8")
    except (OSError, ValueError, orjson.JSONDecodeError):
        return _failed(name, "interface_evidence_invalid", openapi_path)
    if api_paths is None or not _EXPECTED_AGENT_PATHS.issubset(set(api_paths)):
        return _failed(name, "agent_openapi_incomplete", openapi_path)
    if any(token not in runbook for token in _EXPECTED_CLI_TOKENS):
        return _failed(name, "agent_cli_documentation_incomplete", runbook_path)
    if "A3" not in security or "A4" not in security or "R5.5 BLOCKED" not in roadmap:
        return _failed(name, "release_document_status_inconsistent", roadmap_path)
    evidence_hash = canonical_sha256(
        {path.relative_to(repo_root).as_posix(): _file_hash(path) for path in paths}
    )
    return ReleaseCheck(
        name=name,
        status=ReleaseCheckStatus.PASSED,
        reason_code="interface_contracts_passed",
        evidence_hash=evidence_hash,
    )


def _approval_status_check(
    path: Path,
    *,
    name: str,
    gate: str,
    provider: str,
    profile: str,
) -> ReleaseCheck:
    if not path.is_file():
        return _failed(name, f"{name}_evidence_missing", path)
    try:
        payload = _read_mapping(path)
    except (OSError, ValueError, orjson.JSONDecodeError):
        return _failed(name, f"{name}_evidence_invalid", path)
    prohibited = _string_mapping(payload.get("prohibited_actions_observed"))
    expected_prohibited = _EXPECTED_PROHIBITED_ACTIONS[(gate, provider, profile)]
    expected_reason = f"{gate.lower()}_approval_required"
    if (
        set(payload)
        != {
            "approval_gate",
            "profile",
            "prohibited_actions_observed",
            "provider",
            "reason_code",
            "release_gate_passed",
            "schema_version",
            "status",
        }
        or payload.get("schema_version") != 1
        or payload.get("status") != "not_run"
        or payload.get("approval_gate") != gate
        or payload.get("provider") != provider
        or payload.get("profile") != profile
        or payload.get("release_gate_passed") is not False
        or prohibited is None
        or set(prohibited) != expected_prohibited
        or any(value is not False for value in prohibited.values())
        or payload.get("reason_code") != expected_reason
    ):
        return _failed(name, f"{name}_status_invalid", path)
    return ReleaseCheck(
        name=name,
        status=ReleaseCheckStatus.BLOCKED,
        reason_code=expected_reason,
        evidence_hash=cast(str, _file_hash(path)),
        approval_gate=gate,
    )


def build_release_preflight(repo_root: Path) -> ReleasePreflightReport:
    """Validate repository evidence without calling providers, sandboxes, or data."""
    root = repo_root.resolve(strict=True)
    evidence = root / "docs/evidence/r5/release"
    return ReleasePreflightReport(
        checks=(
            _fake_eval_check(evidence / "eval-report-fake.json"),
            _operational_check(evidence / "release-exercises.json"),
            _interface_check(root),
            _approval_status_check(
                evidence / "sandbox-live-status.json",
                name="sandbox_live",
                gate="A3",
                provider="oci",
                profile="hardened",
            ),
            _approval_status_check(
                evidence / "eval-report-balanced.json",
                name="balanced_live_eval",
                gate="A4",
                provider="openai",
                profile="balanced",
            ),
            _approval_status_check(
                evidence / "eval-report-quality.json",
                name="quality_live_eval",
                gate="A4",
                provider="openai",
                profile="quality",
            ),
        )
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Write deterministic preflight evidence and return PASS/BLOCKED/FAIL."""
    arguments = _parser().parse_args(argv)
    report = build_release_preflight(Path(arguments.repo_root))
    payload = report.to_bytes()
    if arguments.output is None:
        sys.stdout.buffer.write(payload + b"\n")
    else:
        Path(arguments.output).write_bytes(payload)
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ReleaseCheck",
    "ReleaseCheckStatus",
    "ReleasePreflightReport",
    "build_release_preflight",
    "main",
]
