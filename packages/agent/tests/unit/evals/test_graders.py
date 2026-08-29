from __future__ import annotations

from pathlib import Path

from ditto_agent.evals.cases import EvalCase, load_eval_cases
from ditto_agent.evals.graders import (
    EvalGradeCategory,
    ModelCritique,
    default_host_graders,
)
from ditto_agent.evals.report import EvalVerdict
from ditto_agent.evals.runner import FakeEvalProvider, LocalEvalRunner

FIXTURES = Path(__file__).parents[2] / "fixtures" / "evals"


class _AlwaysPermissiveCritic:
    critic_id = "permissive-stub"
    version = "1.0.0"

    def evaluate(self, case: EvalCase) -> ModelCritique:
        return ModelCritique(
            suggested_pass=True,
            rationale_hash=case.input_hash,
        )


def test_host_graders_classify_three_minimum_security_failures() -> None:
    cases = {case.case_id: case for case in load_eval_cases(FIXTURES)}
    graders = default_host_graders()

    failures = {
        case_id: {
            grade.reason_code
            for grader in graders
            if (grade := grader.grade(case)).verdict is EvalVerdict.FAILED
        }
        for case_id, case in cases.items()
    }

    assert failures["baseline-passing"] == set()
    assert failures["baseline-forbidden-action"] == {"forbidden_action"}
    assert failures["baseline-missing-evidence"] == {"required_evidence_missing"}
    assert failures["baseline-nondeterministic-replay"] == {"nondeterministic_replay"}


def test_optional_model_critic_is_advisory_and_cannot_override_host_failure() -> None:
    case = next(
        item
        for item in load_eval_cases(FIXTURES)
        if item.case_id == "baseline-forbidden-action"
    )
    report = LocalEvalRunner(
        provider=FakeEvalProvider(),
        model_critic=_AlwaysPermissiveCritic(),
    ).run(suite="baseline", seed=1729, cases=(case,))

    assert not report.passed
    assert not report.results[0].passed
    critic_grade = next(
        grade
        for grade in report.results[0].grades
        if grade.category is EvalGradeCategory.MODEL_CRITIC
    )
    assert critic_grade.verdict is EvalVerdict.ADVISORY
    assert critic_grade.reason_code == "critic_suggested_pass"
