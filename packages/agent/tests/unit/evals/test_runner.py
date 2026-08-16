from __future__ import annotations

from pathlib import Path

import pytest
from ditto_agent.evals.cases import load_eval_cases
from ditto_agent.evals.runner import EvalRunnerError, FakeEvalProvider, LocalEvalRunner

FIXTURES = Path(__file__).parents[2] / "fixtures" / "evals"


def test_fake_provider_report_is_byte_stable_and_traceable_across_100_runs() -> None:
    cases = load_eval_cases(FIXTURES)
    runner = LocalEvalRunner(provider=FakeEvalProvider())

    reports = tuple(
        runner.run(
            suite="baseline",
            seed=1729,
            cases=cases if index % 2 == 0 else tuple(reversed(cases)),
        )
        for index in range(100)
    )
    payloads = {report.to_bytes() for report in reports}

    assert len(payloads) == 1
    report = reports[0]
    assert not report.passed
    assert report.provider_id == "fake-eval-provider-v1"
    assert len(report.input_hash) == 64
    assert len(report.grader_manifest_hash) == 64
    assert len(report.report_hash) == 64
    assert report.verify_report_hash()
    assert tuple(result.case_id for result in report.results) == tuple(
        sorted(case.case_id for case in cases)
    )


def test_runner_fails_closed_on_seed_suite_or_case_hash_drift() -> None:
    cases = load_eval_cases(FIXTURES)
    runner = LocalEvalRunner(provider=FakeEvalProvider())

    with pytest.raises(EvalRunnerError) as seed_info:
        runner.run(suite="baseline", seed=42, cases=cases)
    assert seed_info.value.reason_code == "eval_seed_mismatch"

    with pytest.raises(EvalRunnerError) as suite_info:
        runner.run(suite="different", seed=1729, cases=cases)
    assert suite_info.value.reason_code == "eval_suite_mismatch"

    object.__setattr__(cases[0], "case_hash", "0" * 64)
    with pytest.raises(EvalRunnerError) as hash_info:
        runner.run(suite="baseline", seed=1729, cases=cases)
    assert hash_info.value.reason_code == "eval_case_hash_invalid"
