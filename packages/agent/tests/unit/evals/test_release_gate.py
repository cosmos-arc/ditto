"""Aggregate release-eval contracts for the current frozen dataset."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import orjson
import pytest
from ditto_agent._canonical import canonical_sha256
from ditto_agent.evals.cases import EvalCase, EvalObservation, load_eval_cases
from ditto_agent.evals.release import (
    RELEASE_SUITE_COUNTS,
    EvalCostBasis,
    ReleaseEvalRunIdentity,
)
from ditto_agent.evals.runner import EvalRunnerError, LocalEvalRunner, main

EXPECTED_COUNTS = {
    "author": 20,
    "campaign": 30,
    "grounded": 41,
    "permission": 20,
    "sandbox": 10,
    "shadow": 10,
}
DATASETS = Path(__file__).parents[3] / "src" / "ditto_agent" / "evals" / "datasets"
EVIDENCE = Path(__file__).parents[5] / "docs" / "evidence" / "r5" / "release"


def _assert_release_manifests(payload: dict[str, Any]) -> None:
    manifest = {item["suite"]: item["cases"] for item in payload["dataset_manifest"]}
    assert {suite: len(cases) for suite, cases in manifest.items()} == EXPECTED_COUNTS
    assert sum(len(cases) for cases in manifest.values()) == 131
    assert all(
        set(case) == {"case_id", "schema_version", "input_hash", "case_hash"}
        for cases in manifest.values()
        for case in cases
    )
    expected_versions = {
        "grounded": 2,
        "author": 3,
        "permission": 3,
        "campaign": 4,
        "sandbox": 4,
        "shadow": 5,
    }
    for suite, version in expected_versions.items():
        assert {case["schema_version"] for case in manifest[suite]} == {version}

    observation_manifest = payload["observation_manifest"]
    assert len(observation_manifest) == 131
    assert len(payload["observation_manifest_hash"]) == 64
    assert (
        canonical_sha256(observation_manifest) == payload["observation_manifest_hash"]
    )
    assert all(
        canonical_sha256(item["observation"]) == item["observation_hash"]
        for item in observation_manifest
    )


def _assert_release_performance(payload: dict[str, Any]) -> None:
    reports = {item["suite"]: item for item in payload["suite_reports"]}
    assert set(reports) == set(EXPECTED_COUNTS)
    assert {
        name: item["case_count"] for name, item in reports.items()
    } == EXPECTED_COUNTS
    assert all(item["passed"] is True for item in reports.values())

    cohorts = {item["cohort"]: item for item in payload["performance"]}
    assert cohorts["read"]["suites"] == ["grounded"]
    assert cohorts["read"]["case_count"] == 41
    assert cohorts["read"]["latency_limit_ms"] == 30_000
    assert cohorts["read"]["spend_limit_usd"] == "0.25"
    assert cohorts["read"]["passed"] is True
    assert cohorts["complex"]["suites"] == [
        "author",
        "permission",
        "sandbox",
        "shadow",
    ]
    assert cohorts["complex"]["case_count"] == 60
    assert cohorts["complex"]["latency_limit_ms"] == 60_000
    assert cohorts["complex"]["spend_limit_usd"] == "0.75"
    assert cohorts["complex"]["passed"] is True
    for cohort in cohorts.values():
        assert cohort["latency_p50_ms"] <= cohort["latency_p95_ms"]
        assert float(cohort["spend_p50_usd"]) <= float(cohort["spend_p95_usd"])
        assert float(cohort["spend_p95_usd"]) <= float(cohort["max_spend_usd"])


def test_all_suite_fake_report_freezes_131_cases_graders_and_slos(
    tmp_path: Path,
) -> None:
    first = tmp_path / "release-first.json"
    second = tmp_path / "release-second.json"

    assert (
        main(
            (
                "--suite",
                "all",
                "--provider",
                "fake",
                "--output",
                str(first),
            )
        )
        == 0
    )
    assert (
        main(
            (
                "--suite",
                "all",
                "--provider",
                "fake",
                "--output",
                str(second),
            )
        )
        == 0
    )

    assert first.read_bytes() == second.read_bytes()
    payload = orjson.loads(first.read_bytes())
    assert payload["schema_version"] == 2
    assert payload["suite"] == "all"
    assert payload["provider_id"] == "fake-eval-provider-v1"
    assert payload["profile"] == "fake"
    assert payload["run_identity"]["cost_basis"] == "fixture"
    assert payload["run_identity"]["model_snapshot"] == "fixture-observation-v1"
    assert len(payload["run_identity"]["identity_hash"]) == 64
    assert payload["case_count"] == 131
    assert payload["suite_case_counts"] == EXPECTED_COUNTS
    assert len(payload["dataset_manifest_hash"]) == 64
    assert len(payload["grader_manifest_hash"]) == 64
    assert len(payload["report_hash"]) == 64
    assert payload["passed"] is True
    assert payload["total_model_spend_usd"] == "0.0398"

    _assert_release_manifests(payload)
    _assert_release_performance(payload)
    assert payload["campaign_budget"] == {
        "case_count": 30,
        "policy": "campaign_authorization_budget",
        "suite": "campaign",
    }


def test_glm_comparison_is_fail_closed_without_a4(tmp_path: Path) -> None:
    output = tmp_path / "balanced.json"

    exit_code = main(
        (
            "--suite",
            "all",
            "--provider",
            "glm",
            "--profile",
            "balanced",
            "--output",
            str(output),
        )
    )

    assert exit_code == 5
    payload = orjson.loads(output.read_bytes())
    assert payload["schema_version"] == 1
    assert payload["status"] == "not_run"
    assert payload["approval_gate"] == "A4"
    assert payload["provider"] == "glm"
    assert payload["profile"] == "balanced"
    assert payload["release_gate_passed"] is False
    assert payload["prohibited_actions_observed"] == {
        "api_key_read": False,
        "live_endpoint_called": False,
        "model_cost_incurred": False,
        "model_data_exported": False,
    }


class _ComplexSLORegressionProvider:
    provider_id = "complex-slo-regression-provider"

    def observe(self, case: EvalCase) -> EvalObservation:
        observed = case.observation
        is_complex = case.suite in {"author", "permission", "sandbox", "shadow"}
        return EvalObservation(
            attempted_actions=observed.attempted_actions,
            allowed_actions=observed.allowed_actions,
            evidence_refs=observed.evidence_refs,
            replay_identities=observed.replay_identities,
            rule_assertions=observed.rule_assertions,
            latency_ms=60_001 if is_complex else observed.latency_ms,
            model_spend_usd=Decimal("0.76") if is_complex else observed.model_spend_usd,
        )


def test_one_complex_slo_family_regression_fails_the_release_gate() -> None:
    cases = {suite: load_eval_cases(DATASETS / suite) for suite in RELEASE_SUITE_COUNTS}

    report = LocalEvalRunner(provider=_ComplexSLORegressionProvider()).run_release(
        seed=20_260_816,
        cases=cases,
        profile="fake-regression",
    )

    performance = {item.cohort: item for item in report.performance}
    assert performance["complex"].latency_p95_ms == 60_001
    assert performance["complex"].max_spend_usd == Decimal("0.76")
    assert performance["complex"].passed is False
    assert report.passed is False


class _CountingProvider:
    provider_id = "counting-provider"

    def __init__(self) -> None:
        self.calls = 0

    def observe(self, case: EvalCase) -> EvalObservation:
        self.calls += 1
        return case.observation


class _UsageFixtureProvider:
    provider_id = "usage-cap-provider"

    def __init__(self, *, with_output_hash: bool = True) -> None:
        self._with_output_hash = with_output_hash

    def observe(self, case: EvalCase) -> EvalObservation:
        observed = case.observation
        return EvalObservation(
            attempted_actions=observed.attempted_actions,
            allowed_actions=observed.allowed_actions,
            evidence_refs=observed.evidence_refs,
            replay_identities=observed.replay_identities,
            rule_assertions=observed.rule_assertions,
            latency_ms=observed.latency_ms,
            model_spend_usd=Decimal(0),
            model_requests=1,
            model_input_tokens=1,
            model_output_tokens=0,
            model_output_hash=(
                canonical_sha256({"case_id": case.case_id, "output": "ok"})
                if self._with_output_hash
                else None
            ),
        )


def _usage_identity(*, max_total_tokens: int) -> ReleaseEvalRunIdentity:
    return ReleaseEvalRunIdentity(
        provider_id="usage-cap-provider",
        profile="balanced",
        model_id="stable-model",
        model_snapshot="stable-model-2026-08-17",
        reasoning_effort="high",
        prompt_tool_manifest_hash="1" * 64,
        a4_scope_hash="2" * 64,
        pricing_manifest_hash="3" * 64,
        pricing_as_of="1970-01-01",
        input_price_per_million_usd=Decimal(0),
        output_price_per_million_usd=Decimal(0),
        max_total_spend_usd=Decimal(0),
        max_total_tokens=max_total_tokens,
        cost_basis=EvalCostBasis.USAGE_CAP,
    )


def test_release_report_rejects_usage_above_authenticated_token_cap() -> None:
    cases = {suite: load_eval_cases(DATASETS / suite) for suite in RELEASE_SUITE_COUNTS}

    with pytest.raises(ValueError, match="token cap"):
        LocalEvalRunner(provider=_UsageFixtureProvider()).run_release(
            seed=20_260_816,
            cases=cases,
            profile="balanced",
            run_identity=_usage_identity(max_total_tokens=119),
        )


def test_release_report_rejects_live_observation_without_output_hash() -> None:
    cases = {suite: load_eval_cases(DATASETS / suite) for suite in RELEASE_SUITE_COUNTS}

    with pytest.raises(ValueError, match="output hash"):
        LocalEvalRunner(
            provider=_UsageFixtureProvider(with_output_hash=False)
        ).run_release(
            seed=20_260_816,
            cases=cases,
            profile="balanced",
            run_identity=_usage_identity(max_total_tokens=120),
        )


@pytest.mark.parametrize("corruption", ["missing_last_suite_case", "extra_suite"])
def test_release_dataset_is_preflighted_before_any_provider_call(
    corruption: str,
) -> None:
    cases = {suite: load_eval_cases(DATASETS / suite) for suite in RELEASE_SUITE_COUNTS}
    if corruption == "missing_last_suite_case":
        cases["shadow"] = cases["shadow"][:-1]
    else:
        cases["unexpected"] = cases["shadow"]
    provider = _CountingProvider()

    with pytest.raises(EvalRunnerError) as error:
        LocalEvalRunner(provider=provider).run_release(
            seed=20_260_816,
            cases=cases,
            profile="fake-regression",
        )

    assert error.value.reason_code == "eval_release_dataset_invalid"
    assert provider.calls == 0


def test_release_report_recomputes_grader_and_performance_evidence() -> None:
    cases = {suite: load_eval_cases(DATASETS / suite) for suite in RELEASE_SUITE_COUNTS}
    report = LocalEvalRunner(provider=_CountingProvider()).run_release(
        seed=20_260_816,
        cases=cases,
        profile="fake-regression",
    )

    with pytest.raises(ValueError, match="grader manifest"):
        replace(report, grader_manifest_hash="f" * 64)

    read = next(item for item in report.performance if item.cohort == "read")
    forged_read = replace(read, latency_p50_ms=read.latency_p50_ms + 1)
    with pytest.raises(ValueError, match="performance evidence"):
        replace(
            report,
            performance=tuple(
                forged_read if item.cohort == "read" else item
                for item in report.performance
            ),
        )


def test_release_report_rejects_forged_observation_manifest() -> None:
    cases = {suite: load_eval_cases(DATASETS / suite) for suite in RELEASE_SUITE_COUNTS}
    report = LocalEvalRunner(provider=_CountingProvider()).run_release(
        seed=20_260_816,
        cases=cases,
        profile="fake-regression",
    )
    first = dict(report.observation_manifest[0])
    observation = dict(first["observation"])
    observation["latency_ms"] = observation["latency_ms"] + 1
    first["observation"] = observation

    with pytest.raises(ValueError, match="observation hash"):
        replace(report, observation_manifest=(first, *report.observation_manifest[1:]))


def test_checked_in_fake_release_evidence_matches_current_runner(
    tmp_path: Path,
) -> None:
    current = tmp_path / "fake.json"

    assert main(("--suite", "all", "--provider", "fake", "--output", str(current))) == 0

    assert current.read_bytes() == (EVIDENCE / "eval-report-fake.json").read_bytes()


@pytest.mark.parametrize("profile", ["balanced", "quality"])
def test_unapproved_local_live_command_is_a_deterministic_blocker(
    profile: str,
    tmp_path: Path,
) -> None:
    first = tmp_path / f"{profile}-first.json"
    second = tmp_path / f"{profile}-second.json"

    for current in (first, second):
        assert (
            main(
                (
                    "--suite",
                    "all",
                    "--provider",
                    "glm",
                    "--profile",
                    profile,
                    "--output",
                    str(current),
                )
            )
            == 5
        )

    assert first.read_bytes() == second.read_bytes()
    blocker = orjson.loads(first.read_bytes())
    assert blocker["status"] == "not_run"
    assert blocker["approval_gate"] == "A4"
    assert all(
        value is False for value in blocker["prohibited_actions_observed"].values()
    )
    assert (
        orjson.loads((EVIDENCE / f"eval-report-{profile}.json").read_bytes())["passed"]
        is True
    )
