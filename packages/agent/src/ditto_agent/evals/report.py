"""Byte-stable local eval reports with traceable grader identities."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import cast

from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.contracts._validation import (
    nonnegative_decimal,
    normalized_text,
    sha256_hex,
)
from ditto_agent.evals.cases import EvalMetric, GroundedMetric
from ditto_agent.evals.graders import (
    EvalGrade,
    EvalGradeCategory,
    EvalVerdict,
)
from ditto_agent.evals.r5_3 import R53Metric
from ditto_agent.evals.r5_4 import ShadowMetric

_BASIS_POINT_SCALE = 10_000


@dataclass(frozen=True, slots=True)
class EvalMetricResult:
    """One deterministic per-case grounded metric outcome."""

    metric: GroundedMetric | EvalMetric | R53Metric | ShadowMetric
    passed: bool
    details_hash: str

    def __post_init__(self) -> None:
        """Validate the exact metric identity and immutable outcome."""
        if not isinstance(
            cast(object, self.metric),
            (GroundedMetric, EvalMetric, R53Metric, ShadowMetric),
        ):
            raise ValueError("metric is invalid")
        if not isinstance(cast(object, self.passed), bool):
            raise TypeError("metric result passed must be bool")
        object.__setattr__(
            self,
            "details_hash",
            sha256_hex(self.details_hash, field="details_hash"),
        )

    def identity_payload(self) -> dict[str, object]:
        """Return every per-case metric field authenticated by the report."""
        return {
            "metric": self.metric,
            "passed": self.passed,
            "details_hash": self.details_hash,
        }


@dataclass(frozen=True, slots=True)
class EvalMetricSummary:
    """Exact basis-point aggregate for one non-overridable release metric."""

    metric: GroundedMetric | EvalMetric | R53Metric | ShadowMetric
    passed_cases: int
    total_cases: int
    threshold_basis_points: int
    observed_basis_points: int = field(init=False)
    passed: bool = field(init=False)

    def __post_init__(self) -> None:
        """Derive an exact integer rate without floating-point rounding."""
        if not isinstance(
            cast(object, self.metric),
            (GroundedMetric, EvalMetric, R53Metric, ShadowMetric),
        ):
            raise ValueError("metric is invalid")
        for field_name in ("passed_cases", "total_cases", "threshold_basis_points"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.passed_cases > self.total_cases:
            raise ValueError("metric summary requires a valid denominator")
        if self.threshold_basis_points > _BASIS_POINT_SCALE:
            raise ValueError("metric threshold cannot exceed 10000 basis points")
        observed = (
            self.passed_cases * _BASIS_POINT_SCALE // self.total_cases
            if self.total_cases
            else 0
        )
        object.__setattr__(self, "observed_basis_points", observed)
        object.__setattr__(self, "passed", observed >= self.threshold_basis_points)

    def identity_payload(self) -> dict[str, object]:
        """Return the exact numerator, denominator, threshold, and verdict."""
        return {
            "metric": self.metric,
            "passed_cases": self.passed_cases,
            "total_cases": self.total_cases,
            "threshold_basis_points": self.threshold_basis_points,
            "observed_basis_points": self.observed_basis_points,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class EvalPerformanceSummary:
    """Offline read-path latency and model-spend envelope."""

    read_p95_ms: int
    max_model_spend_usd: Decimal
    latency_limit_ms: int = 30_000
    spend_limit_usd: Decimal = Decimal("0.25")
    passed: bool = field(init=False)

    def __post_init__(self) -> None:
        """Validate limits and derive the deterministic performance verdict."""
        read_p95_ms = cast(object, self.read_p95_ms)
        if (
            isinstance(read_p95_ms, bool)
            or not isinstance(read_p95_ms, int)
            or read_p95_ms < 0
        ):
            raise ValueError("read_p95_ms must be a non-negative integer")
        latency_limit_ms = cast(object, self.latency_limit_ms)
        if (
            isinstance(latency_limit_ms, bool)
            or not isinstance(latency_limit_ms, int)
            or latency_limit_ms <= 0
        ):
            raise ValueError("latency_limit_ms must be a positive integer")
        if not isinstance(
            cast(object, self.max_model_spend_usd), Decimal
        ) or not isinstance(cast(object, self.spend_limit_usd), Decimal):
            raise TypeError("performance spend values must be Decimal")
        nonnegative_decimal(self.max_model_spend_usd, field="max_model_spend_usd")
        nonnegative_decimal(self.spend_limit_usd, field="spend_limit_usd")
        object.__setattr__(
            self,
            "passed",
            self.read_p95_ms <= self.latency_limit_ms
            and self.max_model_spend_usd <= self.spend_limit_usd,
        )

    def identity_payload(self) -> dict[str, object]:
        """Return the latency/spend envelope authenticated by the report."""
        return {
            "read_p95_ms": self.read_p95_ms,
            "max_model_spend_usd": self.max_model_spend_usd,
            "latency_limit_ms": self.latency_limit_ms,
            "spend_limit_usd": self.spend_limit_usd,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class EvalCaseResult:
    """Host-authoritative grades and optional critic advice for one case."""

    case_id: str
    case_hash: str
    input_hash: str
    observation_hash: str
    grades: tuple[EvalGrade, ...]
    metric_results: tuple[EvalMetricResult, ...] = ()
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
        metric_results = tuple(
            sorted(self.metric_results, key=lambda result: result.metric.value)
        )
        metric_ids = tuple(result.metric for result in metric_results)
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("case metric results must have unique metrics")
        object.__setattr__(self, "metric_results", metric_results)
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
            "metric_results": tuple(
                result.identity_payload() for result in self.metric_results
            ),
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
    minimum_case_count: int = 1
    metric_summaries: tuple[EvalMetricSummary, ...] = ()
    performance: EvalPerformanceSummary | None = None
    schema_version: int = 1
    case_count: int = field(init=False)
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
        seed = cast(object, self.seed)
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise ValueError("seed must be a non-negative integer")
        minimum_case_count = cast(object, self.minimum_case_count)
        if (
            isinstance(minimum_case_count, bool)
            or not isinstance(minimum_case_count, int)
            or minimum_case_count <= 0
        ):
            raise ValueError("minimum_case_count must be a positive integer")
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
        object.__setattr__(self, "case_count", len(results))
        summaries = tuple(
            sorted(self.metric_summaries, key=lambda summary: summary.metric.value)
        )
        summary_ids = tuple(summary.metric for summary in summaries)
        if len(summary_ids) != len(set(summary_ids)):
            raise ValueError("metric summaries must have unique metrics")
        object.__setattr__(self, "metric_summaries", summaries)
        object.__setattr__(
            self,
            "passed",
            len(results) >= self.minimum_case_count
            and all(result.passed for result in results)
            and all(summary.passed for summary in summaries)
            and (self.performance is None or self.performance.passed),
        )
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
            "minimum_case_count": self.minimum_case_count,
            "case_count": self.case_count,
            "results": tuple(
                {**result.identity_payload(), "result_hash": result.result_hash}
                for result in self.results
            ),
            "metric_summaries": tuple(
                summary.identity_payload() for summary in self.metric_summaries
            ),
            "performance": (
                None
                if self.performance is None
                else self.performance.identity_payload()
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


__all__ = [
    "EvalCaseResult",
    "EvalMetricResult",
    "EvalMetricSummary",
    "EvalPerformanceSummary",
    "EvalReport",
    "EvalVerdict",
]
