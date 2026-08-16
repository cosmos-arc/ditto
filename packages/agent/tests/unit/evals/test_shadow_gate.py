"""R5.4 DecisionOpinion shadow outcome release-gate contracts."""

from __future__ import annotations

from pathlib import Path

import orjson
import pytest
from ditto_agent.evals.cases import (
    EvalCase,
    EvalCaseError,
    EvalObservation,
    ShadowCaseFamily,
    ShadowMetric,
    decode_eval_case,
    load_eval_cases,
)
from ditto_agent.evals.runner import FakeEvalProvider, LocalEvalRunner, main

DATASETS = Path(__file__).parents[3] / "src" / "ditto_agent" / "evals" / "datasets"
SHADOW_CASES = DATASETS / "shadow"
EVIDENCE = Path(__file__).parents[5] / "docs" / "evidence" / "r5" / "r5.4"
FIXED_SEED = 20_260_816


def test_shadow_dataset_has_exactly_ten_authenticated_families() -> None:
    cases = load_eval_cases(SHADOW_CASES)

    assert len(cases) == 10
    assert all(case.schema_version == 5 for case in cases)
    assert all(case.suite == "shadow" for case in cases)
    assert all(case.verify_hashes() for case in cases)
    assert {case.shadow_family for case in cases} == set(ShadowCaseFamily)
    assert all(set(case.required_metrics) == set(ShadowMetric) for case in cases)


def test_shadow_fake_gate_is_byte_stable_and_every_metric_is_100_percent() -> None:
    cases = load_eval_cases(SHADOW_CASES)
    runner = LocalEvalRunner(provider=FakeEvalProvider())

    reports = tuple(
        runner.run(
            suite="shadow",
            seed=FIXED_SEED,
            cases=cases if index % 2 == 0 else tuple(reversed(cases)),
        )
        for index in range(10)
    )

    assert len({report.to_bytes() for report in reports}) == 1
    report = reports[0]
    assert report.passed
    assert report.minimum_case_count == 10
    assert {item.metric for item in report.metric_summaries} == set(ShadowMetric)
    assert all(
        item.threshold_basis_points == 10_000 for item in report.metric_summaries
    )
    assert all(item.observed_basis_points == 10_000 for item in report.metric_summaries)


def test_shadow_runner_cli_uses_bundled_cases(tmp_path: Path) -> None:
    output = tmp_path / "shadow-report.json"

    exit_code = main(
        ("--suite", "shadow", "--provider", "fake", "--output", str(output))
    )

    payload = orjson.loads(output.read_bytes())
    assert exit_code == 0
    assert payload["suite"] == "shadow"
    assert payload["passed"] is True
    assert len(payload["results"]) == 10


class _FutureLeakProvider:
    provider_id = "shadow-future-leak-provider"

    def observe(self, case: EvalCase) -> EvalObservation:
        observed = case.observation
        assertions = dict(observed.rule_assertions)
        if case.case_id == "shadow-03-future-known-at":
            assertions["future_sentinel_isolated"] = False
        return EvalObservation(
            attempted_actions=observed.attempted_actions,
            allowed_actions=observed.allowed_actions,
            evidence_refs=observed.evidence_refs,
            replay_identities=observed.replay_identities,
            rule_assertions=assertions,
        )


@pytest.mark.pit
def test_one_future_sentinel_leak_fails_the_whole_shadow_gate() -> None:
    report = LocalEvalRunner(provider=_FutureLeakProvider()).run(
        suite="shadow",
        seed=FIXED_SEED,
        cases=load_eval_cases(SHADOW_CASES),
    )

    summary = {item.metric: item for item in report.metric_summaries}[
        ShadowMetric.PIT_SAFETY
    ]
    assert summary.observed_basis_points < 10_000
    assert not report.passed


@pytest.mark.parametrize(
    "mutation", ["remove_metric", "expand_allowlist", "drop_assertion"]
)
def test_shadow_cases_fail_closed_on_governance_tamper(mutation: str) -> None:
    payload = orjson.loads((SHADOW_CASES / "01-v3-grounding.json").read_bytes())
    if mutation == "remove_metric":
        payload["input_payload"]["required_metrics"].pop()
    elif mutation == "expand_allowlist":
        payload["observation"]["allowed_actions"].append("publish_strategy")
    else:
        payload["observation"]["rule_assertions"].pop("future_sentinel_isolated")

    with pytest.raises(EvalCaseError):
        decode_eval_case(orjson.dumps(payload))


def test_shadow_evidence_identity_matches_the_canonical_report() -> None:
    report = LocalEvalRunner(provider=FakeEvalProvider()).run(
        suite="shadow",
        seed=FIXED_SEED,
        cases=load_eval_cases(SHADOW_CASES),
    )
    evidence = orjson.loads((EVIDENCE / "shadow-fake-gate.json").read_bytes())

    assert evidence["case_count"] == report.case_count
    assert evidence["minimum_case_count"] == report.minimum_case_count
    assert evidence["report_identity"] == {
        "report_hash": report.report_hash,
        "input_hash": report.input_hash,
        "grader_manifest_hash": report.grader_manifest_hash,
    }
    assert evidence["live_model_required"] is False
    assert evidence["downstream_mutation_observed"] is False
