"""R5.3 Campaign, PIT, holdout, and sandbox release-gate contracts."""

from __future__ import annotations

from pathlib import Path

import orjson
import pytest
from ditto_agent.evals.cases import (
    CampaignCaseFamily,
    EvalCase,
    EvalCaseError,
    EvalObservation,
    R53Metric,
    SandboxCaseFamily,
    decode_eval_case,
    load_eval_cases,
)
from ditto_agent.evals.runner import FakeEvalProvider, LocalEvalRunner, main

DATASETS = Path(__file__).parents[3] / "src" / "ditto_agent" / "evals" / "datasets"
EVIDENCE = Path(__file__).parents[5] / "docs" / "evidence" / "r5" / "r5.3"
CAMPAIGN_CASES = DATASETS / "campaign"
SANDBOX_CASES = DATASETS / "sandbox"
PERMISSION_CASES = DATASETS / "permission"
FIXED_SEED = 20_260_816


@pytest.mark.parametrize(
    ("directory", "suite", "case_count", "families"),
    [
        (CAMPAIGN_CASES, "campaign", 30, set(CampaignCaseFamily)),
        (SANDBOX_CASES, "sandbox", 10, set(SandboxCaseFamily)),
    ],
)
def test_r5_3_datasets_are_complete_authenticated_and_family_exact(
    directory: Path,
    suite: str,
    case_count: int,
    families: set[object],
) -> None:
    cases = load_eval_cases(directory)

    assert len(cases) == case_count
    assert all(case.schema_version == 4 for case in cases)
    assert all(case.suite == suite for case in cases)
    assert all(case.verify_hashes() for case in cases)
    assert {case.r5_3_family for case in cases} == families
    assert all(R53Metric.EPISODE_REPLAY in case.required_metrics for case in cases)


@pytest.mark.parametrize(
    ("suite", "directory", "case_count", "expected_metrics"),
    [
        (
            "campaign",
            CAMPAIGN_CASES,
            30,
            {
                R53Metric.APPROVAL_BYPASS,
                R53Metric.CAMPAIGN_BUDGET,
                R53Metric.CAMPAIGN_INTEGRITY,
                R53Metric.EPISODE_REPLAY,
                R53Metric.FORBIDDEN_ACTION,
                R53Metric.HOLDOUT_ISOLATION,
                R53Metric.PIT_SAFETY,
            },
        ),
        (
            "sandbox",
            SANDBOX_CASES,
            10,
            {
                R53Metric.EPISODE_REPLAY,
                R53Metric.FORBIDDEN_ACTION,
                R53Metric.SANDBOX_ESCAPE,
            },
        ),
    ],
)
def test_r5_3_fake_gates_are_byte_stable_and_every_metric_is_a_hard_gate(
    suite: str,
    directory: Path,
    case_count: int,
    expected_metrics: set[R53Metric],
) -> None:
    cases = load_eval_cases(directory)
    runner = LocalEvalRunner(provider=FakeEvalProvider())

    reports = tuple(
        runner.run(
            suite=suite,
            seed=FIXED_SEED,
            cases=cases if index % 2 == 0 else tuple(reversed(cases)),
        )
        for index in range(10)
    )

    assert len({report.to_bytes() for report in reports}) == 1
    report = reports[0]
    summaries = {summary.metric: summary for summary in report.metric_summaries}
    assert report.passed
    assert report.minimum_case_count == case_count
    assert set(summaries) == expected_metrics
    assert all(
        summary.threshold_basis_points == 10_000 for summary in summaries.values()
    )
    assert all(
        summary.observed_basis_points == 10_000 for summary in summaries.values()
    )


@pytest.mark.parametrize(
    ("suite", "case_count"),
    [("campaign", 30), ("sandbox", 10)],
)
def test_r5_3_runner_cli_uses_bundled_seed_and_cases(
    suite: str,
    case_count: int,
    tmp_path: Path,
) -> None:
    output = tmp_path / f"{suite}-report.json"

    exit_code = main(("--suite", suite, "--provider", "fake", "--output", str(output)))

    payload = orjson.loads(output.read_bytes())
    assert exit_code == 0
    assert payload["passed"] is True
    assert payload["suite"] == suite
    assert len(payload["results"]) == case_count
    assert payload["minimum_case_count"] == case_count


class _AssertionMutationProvider:
    provider_id = "r5-3-assertion-mutation-provider"

    def __init__(self, *, case_id: str, assertion: str) -> None:
        self._case_id = case_id
        self._assertion = assertion

    def observe(self, case: EvalCase) -> EvalObservation:
        observed = case.observation
        assertions = dict(observed.rule_assertions)
        if case.case_id == self._case_id:
            assertions[self._assertion] = False
        return EvalObservation(
            attempted_actions=observed.attempted_actions,
            allowed_actions=observed.allowed_actions,
            evidence_refs=observed.evidence_refs,
            replay_identities=observed.replay_identities,
            rule_assertions=assertions,
        )


@pytest.mark.parametrize(
    ("suite", "directory", "assertion", "metric"),
    [
        ("campaign", CAMPAIGN_CASES, "future_sentinel_isolated", R53Metric.PIT_SAFETY),
        (
            "campaign",
            CAMPAIGN_CASES,
            "holdout_feedback_isolated",
            R53Metric.HOLDOUT_ISOLATION,
        ),
        (
            "campaign",
            CAMPAIGN_CASES,
            "approval_bypass_blocked",
            R53Metric.APPROVAL_BYPASS,
        ),
        ("sandbox", SANDBOX_CASES, "sandbox_escape_blocked", R53Metric.SANDBOX_ESCAPE),
    ],
)
def test_one_r5_3_security_regression_fails_the_whole_gate(
    suite: str,
    directory: Path,
    assertion: str,
    metric: R53Metric,
) -> None:
    cases = load_eval_cases(directory)
    report = LocalEvalRunner(
        provider=_AssertionMutationProvider(
            case_id=cases[0].case_id, assertion=assertion
        )
    ).run(suite=suite, seed=FIXED_SEED, cases=cases)

    summary = {item.metric: item for item in report.metric_summaries}[metric]
    assert summary.observed_basis_points < 10_000
    assert not summary.passed
    assert not report.passed


@pytest.mark.parametrize(
    ("directory", "filename", "mutation"),
    [
        (CAMPAIGN_CASES, "01-manifest-authorization.json", "remove_metric"),
        (CAMPAIGN_CASES, "01-manifest-authorization.json", "expand_allowlist"),
        (SANDBOX_CASES, "01-network-egress.json", "remove_metric"),
    ],
)
def test_r5_3_cases_fail_closed_on_metric_or_allowlist_tamper(
    directory: Path,
    filename: str,
    mutation: str,
) -> None:
    payload = orjson.loads((directory / filename).read_bytes())
    if mutation == "remove_metric":
        payload["input_payload"]["required_metrics"].pop()
    else:
        payload["observation"]["allowed_actions"].append("publish_strategy")

    with pytest.raises(EvalCaseError):
        decode_eval_case(orjson.dumps(payload))


def test_r5_3_reuses_the_exact_permission_gate_without_lowering_it() -> None:
    cases = load_eval_cases(PERMISSION_CASES)
    report = LocalEvalRunner(provider=FakeEvalProvider()).run(
        suite="permission",
        seed=FIXED_SEED,
        cases=cases,
    )

    summaries = {item.metric.value: item for item in report.metric_summaries}
    assert report.passed
    assert summaries["approval_bypass"].threshold_basis_points == 10_000
    assert summaries["approval_bypass"].observed_basis_points == 10_000


@pytest.mark.parametrize(
    ("suite", "directory", "evidence_filename"),
    [
        ("campaign", CAMPAIGN_CASES, "campaign-fake-gate.json"),
        ("sandbox", SANDBOX_CASES, "sandbox-fake-gate.json"),
        ("permission", PERMISSION_CASES, "permission-regression-gate.json"),
    ],
)
def test_r5_3_evidence_identity_matches_the_canonical_report(
    suite: str,
    directory: Path,
    evidence_filename: str,
) -> None:
    report = LocalEvalRunner(provider=FakeEvalProvider()).run(
        suite=suite,
        seed=FIXED_SEED,
        cases=load_eval_cases(directory),
    )
    evidence = orjson.loads((EVIDENCE / evidence_filename).read_bytes())

    assert evidence["case_count"] == report.case_count
    assert evidence["minimum_case_count"] == report.minimum_case_count
    assert evidence["report_identity"] == {
        "report_hash": report.report_hash,
        "input_hash": report.input_hash,
        "grader_manifest_hash": report.grader_manifest_hash,
    }


def test_pending_live_evidence_is_explicit_and_cannot_impersonate_fake_gates() -> None:
    sandbox = orjson.loads((EVIDENCE / "sandbox-live-status.json").read_bytes())
    model = orjson.loads((EVIDENCE / "live-model-comparison-status.json").read_bytes())

    assert sandbox["status"] == "not_run"
    assert sandbox["approval_gate"] == "A3"
    assert sandbox["exit_code"] == 5
    assert sandbox["fake_report_treated_as_live"] is False
    assert sandbox["physical_acceptance_claimed"] is False
    assert model["status"] == "not_run"
    assert model["approval_gate"] == "A4"
    assert model["prohibited_actions_observed"] == {
        "api_key_read": False,
        "live_endpoint_called": False,
        "campaign_evidence_exported": False,
        "model_cost_incurred": False,
    }
