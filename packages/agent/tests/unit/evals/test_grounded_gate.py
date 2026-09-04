"""R5.1 grounded-suite quality-gate contracts."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import orjson
import pytest
from ditto_agent.evals.cases import (
    EvalCase,
    EvalCaseError,
    EvalObservation,
    GroundedCaseFamily,
    GroundedMetric,
    decode_eval_case,
    load_eval_cases,
)
from ditto_agent.evals.runner import FakeEvalProvider, LocalEvalRunner, main

GROUNDED_CASES = (
    Path(__file__).parents[3]
    / "src"
    / "ditto_agent"
    / "evals"
    / "datasets"
    / "grounded"
)


def test_grounded_dataset_has_41_versioned_cases_and_all_families() -> None:
    cases = load_eval_cases(GROUNDED_CASES)

    assert len(cases) == 41
    assert all(case.schema_version == 2 for case in cases)
    assert all(case.verify_hashes() for case in cases)
    assert {case.grounded_family for case in cases} == set(GroundedCaseFamily)
    assert all(GroundedMetric.EPISODE_REPLAY in case.required_metrics for case in cases)


def test_grounded_fake_gate_meets_fixed_quality_performance_and_replay_thresholds() -> (
    None
):
    cases = load_eval_cases(GROUNDED_CASES)
    runner = LocalEvalRunner(provider=FakeEvalProvider())

    reports = tuple(
        runner.run(
            suite="grounded",
            seed=20260816,
            cases=cases if index % 2 == 0 else tuple(reversed(cases)),
        )
        for index in range(10)
    )

    assert len({report.to_bytes() for report in reports}) == 1
    report = reports[0]
    summaries = {summary.metric: summary for summary in report.metric_summaries}
    assert report.passed
    assert report.minimum_case_count == 30
    assert set(summaries) == set(GroundedMetric)
    assert summaries[GroundedMetric.TOOL_CHOICE].threshold_basis_points == 9500
    assert summaries[GroundedMetric.EVIDENCE_COVERAGE].threshold_basis_points == 9500
    assert summaries[GroundedMetric.FACTUAL_CORRECTNESS].threshold_basis_points == 9000
    for metric in (
        GroundedMetric.REQUIRED_ABSTENTION,
        GroundedMetric.PIT_SAFETY,
        GroundedMetric.PROVIDER_DEGRADATION,
        GroundedMetric.EPISODE_REPLAY,
    ):
        assert summaries[metric].threshold_basis_points == 10_000
        assert summaries[metric].observed_basis_points == 10_000
    assert report.performance is not None
    assert report.performance.read_p95_ms <= 30_000
    assert report.performance.max_model_spend_usd <= Decimal("0.25")
    assert report.performance.passed


def test_grounded_runner_cli_uses_bundled_seed_and_cases_without_overrides(
    tmp_path: Path,
) -> None:
    output = tmp_path / "grounded-report.json"

    exit_code = main(
        (
            "--suite",
            "grounded",
            "--provider",
            "fake",
            "--output",
            str(output),
        )
    )

    payload = orjson.loads(output.read_bytes())
    assert exit_code == 0
    assert payload["passed"] is True
    assert payload["suite"] == "grounded"
    assert len(payload["results"]) == 41
    assert payload["minimum_case_count"] == 30


def test_grounded_gate_fails_closed_when_a_required_metric_is_missing() -> None:
    cases = load_eval_cases(GROUNDED_CASES)
    incomplete = tuple(
        case for case in cases if GroundedMetric.PIT_SAFETY not in case.required_metrics
    )

    report = LocalEvalRunner(provider=FakeEvalProvider()).run(
        suite="grounded",
        seed=20260816,
        cases=incomplete,
    )

    assert not report.passed
    summaries = {summary.metric: summary for summary in report.metric_summaries}
    assert summaries[GroundedMetric.PIT_SAFETY].total_cases == 0
    assert not summaries[GroundedMetric.PIT_SAFETY].passed


@pytest.mark.parametrize(
    "required_metrics",
    [
        ["tool_choice", "episode_replay", 7],
        ["episode_replay"],
    ],
)
def test_grounded_case_rejects_non_text_or_family_metric_omissions(
    required_metrics: list[object],
) -> None:
    payload = orjson.loads(
        (GROUNDED_CASES / "01-tool_choice-experiment.json").read_bytes()
    )
    payload["input_payload"]["required_metrics"] = required_metrics

    with pytest.raises(EvalCaseError) as info:
        decode_eval_case(orjson.dumps(payload))

    assert info.value.reason_code == "eval_case_content_invalid"


class _GroundedMutationProvider:
    provider_id = "grounded-mutation-provider"

    def __init__(
        self,
        *,
        wrong_tool_cases: frozenset[str] = frozenset(),
        wrong_factual_cases: frozenset[str] = frozenset(),
    ) -> None:
        self._wrong_tool_cases = wrong_tool_cases
        self._wrong_factual_cases = wrong_factual_cases

    def observe(self, case: EvalCase) -> EvalObservation:
        observed = case.observation
        actions = observed.attempted_actions
        if case.case_id in self._wrong_tool_cases:
            alternatives = tuple(
                action
                for action in observed.allowed_actions
                if action not in case.expected_actions
            )
            actions = alternatives[:1]
        assertions = dict(observed.rule_assertions)
        if case.case_id in self._wrong_factual_cases:
            assertions["factual_correctness"] = False
        return EvalObservation(
            attempted_actions=actions,
            allowed_actions=observed.allowed_actions,
            evidence_refs=observed.evidence_refs,
            replay_identities=observed.replay_identities,
            rule_assertions=assertions,
            latency_ms=observed.latency_ms,
            model_spend_usd=observed.model_spend_usd,
        )


def test_grounded_tool_choice_threshold_allows_one_of_37_but_not_two_failures() -> None:
    cases = load_eval_cases(GROUNDED_CASES)
    applicable = tuple(
        case.case_id
        for case in cases
        if GroundedMetric.TOOL_CHOICE in case.required_metrics
    )
    assert len(applicable) == 37

    passing = LocalEvalRunner(
        provider=_GroundedMutationProvider(wrong_tool_cases=frozenset(applicable[:1]))
    ).run(suite="grounded", seed=20260816, cases=cases)
    failing = LocalEvalRunner(
        provider=_GroundedMutationProvider(wrong_tool_cases=frozenset(applicable[:2]))
    ).run(suite="grounded", seed=20260816, cases=cases)

    passing_summary = {summary.metric: summary for summary in passing.metric_summaries}[
        GroundedMetric.TOOL_CHOICE
    ]
    failing_summary = {summary.metric: summary for summary in failing.metric_summaries}[
        GroundedMetric.TOOL_CHOICE
    ]
    assert passing_summary.observed_basis_points == 9_729
    assert passing_summary.passed
    assert passing.passed
    assert failing_summary.observed_basis_points == 9_459
    assert not failing_summary.passed
    assert not failing.passed


def test_grounded_factual_threshold_allows_one_of_19_but_not_two_failures() -> None:
    cases = load_eval_cases(GROUNDED_CASES)
    applicable = tuple(
        case.case_id
        for case in cases
        if GroundedMetric.FACTUAL_CORRECTNESS in case.required_metrics
    )
    assert len(applicable) == 19

    passing = LocalEvalRunner(
        provider=_GroundedMutationProvider(
            wrong_factual_cases=frozenset(applicable[:1])
        )
    ).run(suite="grounded", seed=20260816, cases=cases)
    failing = LocalEvalRunner(
        provider=_GroundedMutationProvider(
            wrong_factual_cases=frozenset(applicable[:2])
        )
    ).run(suite="grounded", seed=20260816, cases=cases)

    passing_summary = {summary.metric: summary for summary in passing.metric_summaries}[
        GroundedMetric.FACTUAL_CORRECTNESS
    ]
    failing_summary = {summary.metric: summary for summary in failing.metric_summaries}[
        GroundedMetric.FACTUAL_CORRECTNESS
    ]
    assert passing_summary.observed_basis_points == 9_473
    assert passing_summary.passed
    assert passing.passed
    assert failing_summary.observed_basis_points == 8_947
    assert not failing_summary.passed
    assert not failing.passed
