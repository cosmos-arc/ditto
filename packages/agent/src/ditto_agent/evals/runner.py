"""Offline eval runner using local cases and host-authoritative graders."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts._validation import normalized_text
from ditto_agent.evals.cases import EvalCase, EvalObservation, load_eval_cases
from ditto_agent.evals.graders import (
    EvalGrade,
    EvalGradeCategory,
    EvalVerdict,
    HostGrader,
    ModelCritic,
    default_host_graders,
)
from ditto_agent.evals.report import EvalCaseResult, EvalReport


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

    def _grader_manifest(self) -> tuple[dict[str, object], ...]:
        manifest: tuple[dict[str, object], ...] = tuple(
            {
                "grader_id": grader.grader_id,
                "grader_version": grader.version,
                "category": grader.category,
            }
            for grader in self._host_graders
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
        for case in ordered:
            self._validate_case(case, suite=suite, seed=seed)
            observation = self._provider.observe(case)
            grades = tuple(grader.grade(case) for grader in self._host_graders)
            critic_grade = self._critic_grade(case)
            if critic_grade is not None:
                grades = (*grades, critic_grade)
            results.append(
                EvalCaseResult(
                    case_id=case.case_id,
                    case_hash=case.case_hash,
                    input_hash=case.input_hash,
                    observation_hash=observation.observation_hash,
                    grades=grades,
                )
            )
        grader_manifest = self._grader_manifest()
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
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--provider", choices=("fake",), default="fake")
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local Fake-provider eval CLI and optionally write canonical JSON."""
    arguments = _parser().parse_args(argv)
    report = LocalEvalRunner(provider=FakeEvalProvider()).run(
        suite=str(arguments.suite),
        seed=int(arguments.seed),
        cases=load_eval_cases(Path(arguments.cases)),
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
    "main",
]
