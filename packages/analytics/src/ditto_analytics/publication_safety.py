"""Publication safety models for derived release control."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ditto_kernel.specs import DerivedRole, MaterializationProfile

type CompileFlagValue = str | int | float | bool
type JsonPrimitive = None | bool | int | float | str
type JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]

__all__ = [
    "CertificationCheckResult",
    "CertificationPack",
    "CertificationReport",
    "CertificationStage",
    "CompatibilityManifest",
    "CompileFlagValue",
    "DerivedMinimalDQSummary",
    "DerivedRole",
    "MaterializationProfile",
    "PublicationSafetySeverity",
    "ShadowDiffReport",
    "ShadowTraceRecord",
]

_JUMP_RATE_THRESHOLD: float = 0.3
_DISTRIBUTION_DRIFT_THRESHOLD: float = 0.1
_COVERAGE_RATE_MINIMUM: float = 0.95


class PublicationSafetySeverity(StrEnum):
    """Severity levels for publication safety checks."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class CertificationStage(StrEnum):
    """Certification gate stages."""

    SHADOW_READY = "shadow_ready"
    PUBLISH_READY = "publish_ready"


@dataclass(frozen=True)
class CompatibilityManifest:
    """Release and replay compatibility contract."""

    engine_codegen_version: str | None
    analysis_version: str | None
    polars_version: str | None
    expr_serialization_format: str | None
    operator_fingerprint: str | None
    global_compile_flags: dict[str, CompileFlagValue] | None
    calendar_id: str | None
    timezone: str | None
    time_semantics_version: str | None
    python_version: str | None = None
    platform: str | None = None
    builder_version: str | None = None
    manifest_hash: str | None = None

    def missing_required_fields(self) -> tuple[str, ...]:
        """Return required fields that are missing."""
        required_values = (
            ("engine_codegen_version", self.engine_codegen_version),
            ("analysis_version", self.analysis_version),
            ("polars_version", self.polars_version),
            ("expr_serialization_format", self.expr_serialization_format),
            ("operator_fingerprint", self.operator_fingerprint),
            ("global_compile_flags", self.global_compile_flags),
            ("calendar_id", self.calendar_id),
            ("timezone", self.timezone),
            ("time_semantics_version", self.time_semantics_version),
        )
        missing = tuple(
            field_name
            for field_name, value in required_values
            if value is None or (isinstance(value, str) and value == "")
        )
        return missing

    def is_complete(self) -> bool:
        """Whether all required fields are present."""
        return len(self.missing_required_fields()) == 0


@dataclass(frozen=True)
class DerivedMinimalDQSummary:
    """Minimal DQ summary collected from one derived materialization output."""

    row_count: int
    primary_key_columns: tuple[str, ...]
    missing_primary_key_columns: tuple[str, ...] = ()
    null_primary_key_count: int = 0
    duplicate_key_count: int = 0
    null_value_count: int = 0
    nan_value_count: int = 0
    computable_value_count: int = 0
    failed_checks: tuple[str, ...] = ()
    coverage_rate: float = 0.0
    value_mean: float = 0.0
    value_std: float = 0.0
    value_skewness: float = 0.0
    distribution_drift: float | None = None
    value_jump_rate: float = 0.0
    max_consecutive_nulls: int = 0

    def is_passed(self) -> bool:
        """Return whether the minimal DQ summary has blocking errors."""
        return len(self.failed_checks) == 0

    def error_count(self) -> int:
        """Return the number of failed minimal DQ checks."""
        return len(self.failed_checks)

    def advanced_checks(self) -> tuple[str, ...]:
        """
        Run enhanced DQ constraint checks on the value distribution.

        Returns:
            Tuple of failed check names.  Empty tuple means all passed.

        """
        failed: list[str] = []
        if self.coverage_rate < _COVERAGE_RATE_MINIMUM:
            failed.append("coverage_rate_minimum")
        if (
            self.distribution_drift is not None
            and self.distribution_drift > _DISTRIBUTION_DRIFT_THRESHOLD
        ):
            failed.append("distribution_stability")
        if self.value_jump_rate > _JUMP_RATE_THRESHOLD:
            failed.append("value_continuity")
        return tuple(failed)


@dataclass(frozen=True)
class ShadowDiffReport:
    """Aggregated candidate/baseline diff result."""

    report_id: str
    derived_id: str
    candidate_version: int
    baseline_version: int
    request_count: int
    sample_count: int
    schema_match: bool
    value_diff_rate: float
    coverage_delta: float
    freshness_delta: float | None
    latency_p50_delta: float | None
    latency_p95_delta: float | None
    fallback_ratio_delta: float | None
    error_count: int
    warning_count: int
    info_count: int
    candidate_manifest_hash: str
    baseline_manifest_hash: str
    created_at: str

    def has_blocking_errors(self) -> bool:
        """Return whether the diff contains blocking errors."""
        return self.error_count > 0


@dataclass(frozen=True)
class ShadowTraceRecord:
    """Sampled trace record for shadow diff explainability."""

    trace_id: str
    report_id: str
    request_context: dict[str, JsonValue]
    candidate_value: JsonValue
    baseline_value: JsonValue
    diff_category: str
    candidate_manifest_hash: str
    baseline_manifest_hash: str
    sampled_at: str


@dataclass(frozen=True)
class CertificationCheckResult:
    """Single certification check result."""

    name: str
    severity: PublicationSafetySeverity
    passed: bool
    message: str
    metric_value: float | int | str | None = None
    threshold_value: float | int | str | None = None


@dataclass(frozen=True)
class CertificationPack:
    """Pack definition for a certification gate."""

    pack_id: str
    role: DerivedRole
    materialization_profile: MaterializationProfile
    stage: CertificationStage
    check_names: tuple[str, ...]


@dataclass(frozen=True)
class CertificationReport:
    """Resolved certification result for a candidate version."""

    report_id: str
    pack: CertificationPack
    derived_id: str
    version: int
    checks: tuple[CertificationCheckResult, ...]
    manifest_hash: str
    shadow_diff_report_id: str | None
    created_at: str

    def has_blocking_errors(self) -> bool:
        """Return whether any ERROR-level check failed."""
        return any(
            check.severity == PublicationSafetySeverity.ERROR and not check.passed
            for check in self.checks
        )

    def is_passed(self) -> bool:
        """Return whether the certification passes its gate."""
        return not self.has_blocking_errors()

    def check_counts(self) -> dict[PublicationSafetySeverity, int]:
        """Return failing check counts grouped by severity."""
        return {
            severity: sum(
                1
                for check in self.checks
                if check.severity == severity and not check.passed
            )
            for severity in PublicationSafetySeverity
        }
