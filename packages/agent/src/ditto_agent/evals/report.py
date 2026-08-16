"""Byte-stable local eval reports with traceable grader identities."""

from __future__ import annotations

from dataclasses import dataclass, field

from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.contracts._validation import normalized_text, sha256_hex
from ditto_agent.evals.graders import (
    EvalGrade,
    EvalGradeCategory,
    EvalVerdict,
)


@dataclass(frozen=True, slots=True)
class EvalCaseResult:
    """Host-authoritative grades and optional critic advice for one case."""

    case_id: str
    case_hash: str
    input_hash: str
    observation_hash: str
    grades: tuple[EvalGrade, ...]
    passed: bool = field(init=False)
    result_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Sort unique grades and derive the host-only verdict and result hash."""
        object.__setattr__(
            self, "case_id", normalized_text(self.case_id, field="case_id")
        )
        for field_name in ("case_hash", "input_hash", "observation_hash"):
            object.__setattr__(
                self,
                field_name,
                sha256_hex(getattr(self, field_name), field=field_name),
            )
        grades = tuple(sorted(self.grades, key=lambda grade: grade.grader_id))
        grade_ids = tuple(grade.grader_id for grade in grades)
        if len(grade_ids) != len(set(grade_ids)):
            raise ValueError("case grades must have unique grader IDs")
        host_grades = tuple(
            grade
            for grade in grades
            if grade.category is not EvalGradeCategory.MODEL_CRITIC
        )
        if not host_grades:
            raise ValueError("case result requires host grades")
        object.__setattr__(self, "grades", grades)
        object.__setattr__(
            self,
            "passed",
            all(grade.verdict is EvalVerdict.PASSED for grade in host_grades),
        )
        object.__setattr__(
            self, "result_hash", canonical_sha256(self.identity_payload())
        )

    def identity_payload(self) -> dict[str, object]:
        """Return the complete per-case report identity."""
        return {
            "case_id": self.case_id,
            "case_hash": self.case_hash,
            "input_hash": self.input_hash,
            "observation_hash": self.observation_hash,
            "grades": tuple(grade.identity_payload() for grade in self.grades),
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class EvalReport:
    """Deterministic report independent of wall-clock time and case ordering."""

    suite: str
    provider_id: str
    seed: int
    input_hash: str
    grader_manifest_hash: str
    results: tuple[EvalCaseResult, ...]
    schema_version: int = 1
    passed: bool = field(init=False)
    report_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Validate report identity and derive the aggregate host verdict."""
        if self.schema_version != 1:
            raise ValueError("eval report schema_version is not supported")
        object.__setattr__(self, "suite", normalized_text(self.suite, field="suite"))
        object.__setattr__(
            self,
            "provider_id",
            normalized_text(self.provider_id, field="provider_id"),
        )
        if isinstance(self.seed, bool) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        object.__setattr__(
            self, "input_hash", sha256_hex(self.input_hash, field="input_hash")
        )
        object.__setattr__(
            self,
            "grader_manifest_hash",
            sha256_hex(self.grader_manifest_hash, field="grader_manifest_hash"),
        )
        results = tuple(sorted(self.results, key=lambda result: result.case_id))
        result_ids = tuple(result.case_id for result in results)
        if not results or len(result_ids) != len(set(result_ids)):
            raise ValueError("eval report requires unique case results")
        object.__setattr__(self, "results", results)
        object.__setattr__(self, "passed", all(result.passed for result in results))
        object.__setattr__(
            self, "report_hash", canonical_sha256(self.identity_payload())
        )

    def identity_payload(self) -> dict[str, object]:
        """Return every field authenticated by the report hash."""
        return {
            "schema_version": self.schema_version,
            "suite": self.suite,
            "provider_id": self.provider_id,
            "seed": self.seed,
            "input_hash": self.input_hash,
            "grader_manifest_hash": self.grader_manifest_hash,
            "results": tuple(
                {**result.identity_payload(), "result_hash": result.result_hash}
                for result in self.results
            ),
            "passed": self.passed,
        }

    def verify_report_hash(self) -> bool:
        """Recompute the aggregate report identity."""
        return self.report_hash == canonical_sha256(self.identity_payload())

    def to_bytes(self) -> bytes:
        """Render canonical report JSON without unstable timestamps."""
        if not self.verify_report_hash():
            raise ValueError("eval report hash is invalid")
        return canonical_bytes(
            {**self.identity_payload(), "report_hash": self.report_hash}
        )


__all__ = ["EvalCaseResult", "EvalReport", "EvalVerdict"]
