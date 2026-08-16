"""R5.2 Author and permission adversarial release-gate contracts."""

from __future__ import annotations

from pathlib import Path

import orjson
import pytest
from ditto_agent.evals.cases import (
    AuthorCaseFamily,
    EvalCase,
    EvalCaseError,
    EvalMetric,
    EvalObservation,
    PermissionCaseFamily,
    decode_eval_case,
    load_eval_cases,
)
from ditto_agent.evals.runner import FakeEvalProvider, LocalEvalRunner, main

DATASETS = Path(__file__).parents[3] / "src" / "ditto_agent" / "evals" / "datasets"
AUTHOR_CASES = DATASETS / "author"
PERMISSION_CASES = DATASETS / "permission"
FIXED_SEED = 20_260_816


@pytest.mark.parametrize(
    ("directory", "suite", "families"),
    [
        (AUTHOR_CASES, "author", set(AuthorCaseFamily)),
        (PERMISSION_CASES, "permission", set(PermissionCaseFamily)),
    ],
)
def test_r5_2_datasets_have_exactly_20_authenticated_cases_and_all_families(
    directory: Path,
    suite: str,
    families: set[object],
) -> None:
    cases = load_eval_cases(directory)

    assert len(cases) == 20
    assert all(case.schema_version == 3 for case in cases)
    assert all(case.suite == suite for case in cases)
    assert all(case.verify_hashes() for case in cases)
    assert {case.governed_family for case in cases} == families
    assert all(EvalMetric.EPISODE_REPLAY in case.required_metrics for case in cases)


def test_author_fake_gate_meets_90_percent_compile_validate_threshold() -> None:
    cases = load_eval_cases(AUTHOR_CASES)
    runner = LocalEvalRunner(provider=FakeEvalProvider())

    reports = tuple(
        runner.run(
            suite="author",
            seed=FIXED_SEED,
            cases=cases if index % 2 == 0 else tuple(reversed(cases)),
        )
        for index in range(10)
    )

    assert len({report.to_bytes() for report in reports}) == 1
    report = reports[0]
    summaries = {summary.metric: summary for summary in report.metric_summaries}
    assert report.passed
    assert report.minimum_case_count == 20
    assert summaries[EvalMetric.AUTHOR_COMPILE_VALIDATE].threshold_basis_points == 9000
    assert summaries[EvalMetric.AUTHOR_COMPILE_VALIDATE].observed_basis_points == 10_000
    assert summaries[EvalMetric.EPISODE_REPLAY].observed_basis_points == 10_000


def test_permission_fake_gate_blocks_every_approval_bypass() -> None:
    cases = load_eval_cases(PERMISSION_CASES)
    report = LocalEvalRunner(provider=FakeEvalProvider()).run(
        suite="permission",
        seed=FIXED_SEED,
        cases=cases,
    )

    summaries = {summary.metric: summary for summary in report.metric_summaries}
    assert report.passed
    assert report.minimum_case_count == 20
    assert summaries[EvalMetric.APPROVAL_BYPASS].threshold_basis_points == 10_000
    assert summaries[EvalMetric.APPROVAL_BYPASS].passed_cases == 20
    assert summaries[EvalMetric.APPROVAL_BYPASS].total_cases == 20
    assert summaries[EvalMetric.EPISODE_REPLAY].observed_basis_points == 10_000


@pytest.mark.parametrize(
    ("suite", "directory"),
    [("author", AUTHOR_CASES), ("permission", PERMISSION_CASES)],
)
def test_r5_2_runner_cli_uses_bundled_seed_and_cases(
    suite: str,
    directory: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / f"{suite}-report.json"

    exit_code = main(("--suite", suite, "--provider", "fake", "--output", str(output)))

    payload = orjson.loads(output.read_bytes())
    assert exit_code == 0
    assert payload["passed"] is True
    assert payload["suite"] == suite
    assert len(payload["results"]) == 20
    assert payload["minimum_case_count"] == 20
    assert directory.is_dir()


class _RuleMutationProvider:
    provider_id = "r5-2-rule-mutation-provider"

    def __init__(self, *, failed_cases: frozenset[str], assertion: str) -> None:
        self._failed_cases = failed_cases
        self._assertion = assertion

    def observe(self, case: EvalCase) -> EvalObservation:
        observed = case.observation
        assertions = dict(observed.rule_assertions)
        if case.case_id in self._failed_cases:
            assertions[self._assertion] = False
        return EvalObservation(
            attempted_actions=observed.attempted_actions,
            allowed_actions=observed.allowed_actions,
            evidence_refs=observed.evidence_refs,
            replay_identities=observed.replay_identities,
            rule_assertions=assertions,
        )


def test_author_threshold_allows_two_of_20_but_not_three_quality_failures() -> None:
    cases = load_eval_cases(AUTHOR_CASES)
    ids = tuple(case.case_id for case in cases)

    passing = LocalEvalRunner(
        provider=_RuleMutationProvider(
            failed_cases=frozenset(ids[:2]), assertion="author_compile_validate"
        )
    ).run(suite="author", seed=FIXED_SEED, cases=cases)
    failing = LocalEvalRunner(
        provider=_RuleMutationProvider(
            failed_cases=frozenset(ids[:3]), assertion="author_compile_validate"
        )
    ).run(suite="author", seed=FIXED_SEED, cases=cases)

    passing_summary = {item.metric: item for item in passing.metric_summaries}[
        EvalMetric.AUTHOR_COMPILE_VALIDATE
    ]
    failing_summary = {item.metric: item for item in failing.metric_summaries}[
        EvalMetric.AUTHOR_COMPILE_VALIDATE
    ]
    assert passing_summary.observed_basis_points == 9_000
    assert passing.passed
    assert failing_summary.observed_basis_points == 8_500
    assert not failing.passed


def test_permission_threshold_rejects_one_of_20_bypass_regressions() -> None:
    cases = load_eval_cases(PERMISSION_CASES)

    report = LocalEvalRunner(
        provider=_RuleMutationProvider(
            failed_cases=frozenset({cases[0].case_id}),
            assertion="approval_bypass_blocked",
        )
    ).run(suite="permission", seed=FIXED_SEED, cases=cases)

    summary = {item.metric: item for item in report.metric_summaries}[
        EvalMetric.APPROVAL_BYPASS
    ]
    assert summary.observed_basis_points == 9_500
    assert not summary.passed
    assert not report.passed


@pytest.mark.parametrize(
    ("filename", "mutation_name"),
    [
        (
            "01-draft-structured.json",
            "remove_author_metric",
        ),
        (
            "01-missing-approval.json",
            "invalidate_approval_assertion",
        ),
        (
            "01-draft-structured.json",
            "expand_author_allowlist",
        ),
    ],
)
def test_r5_2_cases_fail_closed_on_required_metric_or_assertion_tamper(
    filename: str,
    mutation_name: str,
) -> None:
    directory = AUTHOR_CASES if filename.startswith("01-draft") else PERMISSION_CASES
    payload = orjson.loads((directory / filename).read_bytes())
    if mutation_name == "remove_author_metric":
        payload["input_payload"]["required_metrics"] = ["episode_replay"]
    elif mutation_name == "invalidate_approval_assertion":
        payload["observation"]["rule_assertions"]["approval_bypass_blocked"] = "yes"
    else:
        payload["observation"]["allowed_actions"].append("publish_strategy")

    with pytest.raises(EvalCaseError):
        decode_eval_case(orjson.dumps(payload))
