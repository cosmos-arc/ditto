"""Offline eval runner using local cases and host-authoritative graders."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Protocol, cast

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts._validation import normalized_text
from ditto_agent.evals.cases import (
    EvalCase,
    EvalObservation,
    GroundedMetric,
    load_eval_cases,
)
from ditto_agent.evals.graders import (
    EvalGrade,
    EvalGradeCategory,
    EvalVerdict,
    HostGrader,
    ModelCritic,
    RequiredEvidenceGrader,
    default_host_graders,
    grounded_metric_results,
)
from ditto_agent.evals.report import (
    EvalCaseResult,
    EvalMetricResult,
    EvalMetricSummary,
    EvalPerformanceSummary,
    EvalReport,
)

_GROUNDED_SEED = 20_260_816
_GROUNDED_MINIMUM_CASES = 30
_GROUNDED_SPEND_FAILURE = Decimal("0.26")
_GROUNDED_THRESHOLDS = MappingProxyType(
    {
        GroundedMetric.TOOL_CHOICE: 9_500,
        GroundedMetric.EVIDENCE_COVERAGE: 9_500,
        GroundedMetric.FACTUAL_CORRECTNESS: 9_000,
        GroundedMetric.REQUIRED_ABSTENTION: 10_000,
        GroundedMetric.PIT_SAFETY: 10_000,
        GroundedMetric.PROVIDER_DEGRADATION: 10_000,
        GroundedMetric.EPISODE_REPLAY: 10_000,
    }
)


class EvalRunnerError(RuntimeError):
    """The local runner rejected inconsistent or unauthenticated inputs."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.details = MappingProxyType(dict(details or {}))


class EvalProvider(Protocol):
    """Local provider of normalized observations for eval cases."""

    provider_id: str

    def observe(self, case: EvalCase) -> EvalObservation:
        """Return the observation associated with one case."""
        ...


class FakeEvalProvider:
    """Zero-network provider that replays exact fixture observations."""

    provider_id = "fake-eval-provider-v1"

    def observe(self, case: EvalCase) -> EvalObservation:
        """Return only an authenticated fixture observation."""
        if not case.observation.verify_observation_hash():
            raise EvalRunnerError(
                "Eval observation hash verification failed",
                reason_code="eval_observation_hash_invalid",
            )
        return case.observation


class LocalEvalRunner:
    """Generate byte-stable reports without cloud evals or trace storage."""

    def __init__(
        self,
        *,
        provider: EvalProvider,
        host_graders: tuple[HostGrader, ...] | None = None,
        model_critic: ModelCritic | None = None,
    ) -> None:
        self._provider = provider
        self._host_graders = host_graders or default_host_graders()
        self._model_critic = model_critic
        self._validate_graders()

    def _validate_graders(self) -> None:
        grader_ids = tuple(grader.grader_id for grader in self._host_graders)
        if not grader_ids or len(grader_ids) != len(set(grader_ids)):
            raise ValueError("host graders must have unique IDs")
        if any(
            grader.category is EvalGradeCategory.MODEL_CRITIC
            for grader in self._host_graders
        ):
            raise ValueError("host grader manifest cannot include model critics")

    def _active_host_graders(self, *, suite: str) -> tuple[HostGrader, ...]:
        if suite != "grounded":
            return self._host_graders
        return tuple(
            grader
            for grader in self._host_graders
            if not isinstance(grader, RequiredEvidenceGrader)
        )

    def _grader_manifest(
        self,
        host_graders: tuple[HostGrader, ...],
    ) -> tuple[dict[str, object], ...]:
        manifest: tuple[dict[str, object], ...] = tuple(
            {
                "grader_id": grader.grader_id,
                "grader_version": grader.version,
                "category": grader.category,
            }
            for grader in host_graders
        )
        if self._model_critic is not None:
            manifest = (
                *manifest,
                {
                    "grader_id": normalized_text(
                        self._model_critic.critic_id, field="critic_id"
                    ),
                    "grader_version": normalized_text(
                        self._model_critic.version, field="critic_version"
                    ),
                    "category": EvalGradeCategory.MODEL_CRITIC,
                },
            )
        return tuple(sorted(manifest, key=lambda item: str(item["grader_id"])))

    def _critic_grade(self, case: EvalCase) -> EvalGrade | None:
        if self._model_critic is None:
            return None
        critique = self._model_critic.evaluate(case)
        return EvalGrade(
            grader_id=self._model_critic.critic_id,
            grader_version=self._model_critic.version,
            category=EvalGradeCategory.MODEL_CRITIC,
            verdict=EvalVerdict.ADVISORY,
            reason_code=(
                "critic_suggested_pass"
                if critique.suggested_pass
                else "critic_suggested_fail"
            ),
            details_hash=critique.rationale_hash,
        )

    def run(
        self,
        *,
        suite: str,
        seed: int,
        cases: tuple[EvalCase, ...],
    ) -> EvalReport:
        """Grade authenticated local cases and derive one deterministic report."""
        suite = normalized_text(suite, field="suite")
        if isinstance(seed, bool) or seed < 0:
            raise ValueError("seed must be a non-negative integer")
        ordered = tuple(sorted(cases, key=lambda case: case.case_id))
        if not ordered:
            raise EvalRunnerError(
                "Eval run requires at least one case",
                reason_code="eval_cases_empty",
            )
        case_ids = tuple(case.case_id for case in ordered)
        if len(case_ids) != len(set(case_ids)):
            raise EvalRunnerError(
                "Eval run has duplicate case IDs",
                reason_code="eval_case_duplicate_id",
            )
        results: list[EvalCaseResult] = []
        observations: list[EvalObservation] = []
        host_graders = self._active_host_graders(suite=suite)
        for case in ordered:
            self._validate_case(case, suite=suite, seed=seed)
            observation = self._provider.observe(case)
            if not isinstance(cast(object, observation), EvalObservation) or not (
                observation.verify_observation_hash()
            ):
                raise EvalRunnerError(
                    "Eval provider returned an invalid observation",
                    reason_code="eval_observation_hash_invalid",
                )
            observations.append(observation)
            grades = tuple(grader.grade(case, observation) for grader in host_graders)
            critic_grade = self._critic_grade(case)
            if critic_grade is not None:
                grades = (*grades, critic_grade)
            metric_results = (
                tuple(
                    EvalMetricResult(
                        metric=metric,
                        passed=passed,
                        details_hash=canonical_sha256(
                            {
                                "case_hash": case.case_hash,
                                "observation_hash": observation.observation_hash,
                                "metric": metric,
                                "passed": passed,
                            }
                        ),
                    )
                    for metric, passed in grounded_metric_results(case, observation)
                )
                if suite == "grounded"
                else ()
            )
            results.append(
                EvalCaseResult(
                    case_id=case.case_id,
                    case_hash=case.case_hash,
                    input_hash=case.input_hash,
                    observation_hash=observation.observation_hash,
                    grades=grades,
                    metric_results=metric_results,
                )
            )
        grader_manifest = self._grader_manifest(host_graders)
        metric_summaries = self._metric_summaries(tuple(results), suite=suite)
        performance = self._performance(tuple(observations), suite=suite)
        return EvalReport(
            suite=suite,
            provider_id=self._provider.provider_id,
            seed=seed,
            input_hash=canonical_sha256(
                {
                    "suite": suite,
                    "seed": seed,
                    "provider_id": self._provider.provider_id,
                    "cases": tuple(
                        (case.case_id, case.input_hash, case.case_hash)
                        for case in ordered
                    ),
                }
            ),
            grader_manifest_hash=canonical_sha256(grader_manifest),
            results=tuple(results),
            minimum_case_count=(_GROUNDED_MINIMUM_CASES if suite == "grounded" else 1),
            metric_summaries=metric_summaries,
            performance=performance,
        )

    @staticmethod
    def _metric_summaries(
        results: tuple[EvalCaseResult, ...],
        *,
        suite: str,
    ) -> tuple[EvalMetricSummary, ...]:
        if suite != "grounded":
            return ()
        summaries: list[EvalMetricSummary] = []
        for metric, threshold in _GROUNDED_THRESHOLDS.items():
            outcomes = tuple(
                outcome.passed
                for result in results
                for outcome in result.metric_results
                if outcome.metric is metric
            )
            summaries.append(
                EvalMetricSummary(
                    metric=metric,
                    passed_cases=sum(outcomes),
                    total_cases=len(outcomes),
                    threshold_basis_points=threshold,
                )
            )
        return tuple(summaries)

    @staticmethod
    def _performance(
        observations: tuple[EvalObservation, ...],
        *,
        suite: str,
    ) -> EvalPerformanceSummary | None:
        if suite != "grounded":
            return None
        latencies = tuple(sorted(item.latency_ms for item in observations))
        if not latencies:
            return EvalPerformanceSummary(
                read_p95_ms=30_001,
                max_model_spend_usd=_GROUNDED_SPEND_FAILURE,
            )
        rank = (95 * len(latencies) + 99) // 100
        return EvalPerformanceSummary(
            read_p95_ms=latencies[rank - 1],
            max_model_spend_usd=max(item.model_spend_usd for item in observations),
        )

    @staticmethod
    def _validate_case(case: EvalCase, *, suite: str, seed: int) -> None:
        if not case.verify_hashes():
            raise EvalRunnerError(
                "Eval case hash verification failed",
                reason_code="eval_case_hash_invalid",
            )
        if case.suite != suite:
            raise EvalRunnerError(
                "Eval case belongs to a different suite",
                reason_code="eval_suite_mismatch",
            )
        if case.seed != seed:
            raise EvalRunnerError(
                "Eval case seed differs from the fixed run seed",
                reason_code="eval_seed_mismatch",
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run offline governed Agent evals")
    parser.add_argument("--suite", required=True)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--provider", choices=("fake",), default="fake")
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def bundled_eval_cases(suite: str) -> tuple[int, Path]:
    """Resolve only repository-shipped deterministic suites."""
    if suite != "grounded":
        raise EvalRunnerError(
            "Eval suite requires explicit seed and cases",
            reason_code="eval_suite_not_bundled",
        )
    directory = Path(__file__).with_name("datasets") / "grounded"
    return _GROUNDED_SEED, directory


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local Fake-provider eval CLI and optionally write canonical JSON."""
    arguments = _parser().parse_args(argv)
    suite = str(arguments.suite)
    seed = arguments.seed
    cases_path = arguments.cases
    if seed is None or cases_path is None:
        bundled_seed, bundled_cases = bundled_eval_cases(suite)
        seed = bundled_seed if seed is None else seed
        cases_path = bundled_cases if cases_path is None else cases_path
    report = LocalEvalRunner(provider=FakeEvalProvider()).run(
        suite=suite,
        seed=int(seed),
        cases=load_eval_cases(Path(cases_path)),
    )
    payload = report.to_bytes()
    if arguments.output is None:
        sys.stdout.buffer.write(payload + b"\n")
    else:
        Path(arguments.output).write_bytes(payload)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "EvalProvider",
    "EvalRunnerError",
    "FakeEvalProvider",
    "LocalEvalRunner",
    "bundled_eval_cases",
    "main",
]
