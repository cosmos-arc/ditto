"""
Publication records for derived materialization.

因子物化发布的两个承重概念：兼容性 manifest（产物身份：输入快照与计算
身份的冻结记录）与最小 DQ 摘要（发布前的必要正确性验证）。shadow 双跑、
certification 两阶段等发布安全机器已按 #444 删除；产物身份的唯一载体是
artifact metadata 中的 publication 块。
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_kernel.time_semantics import DEFAULT_PIT_TIME_COLUMN, PIT_POLICY_FAIL_CLOSED
from ditto_platform.foundation.json_types import JsonDict

__all__ = [
    "CompatibilityManifest",
    "CompatibilityManifestRecord",
    "CompileFlagValue",
    "DerivedMinimalDQSummary",
    "DerivedMinimalDQSummaryRecord",
]

type CompileFlagValue = str | int | float | bool

_JUMP_RATE_THRESHOLD: float = 0.3
_DISTRIBUTION_DRIFT_THRESHOLD: float = 0.1
_COVERAGE_RATE_MINIMUM: float = 0.95


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
    pit_policy: str | None = PIT_POLICY_FAIL_CLOSED
    pit_time_column: str | None = DEFAULT_PIT_TIME_COLUMN
    unsafe_time_policy: str | None = ""
    source_snapshot_id: str | None = None
    source_snapshot_ids: tuple[str, ...] = ()
    python_version: str | None = None
    platform: str | None = None
    builder_version: str | None = None
    manifest_hash: str | None = None

    def __post_init__(self) -> None:
        """Normalize JSON-hydrated snapshot lists back to tuples."""
        object.__setattr__(
            self,
            "source_snapshot_ids",
            tuple(self.source_snapshot_ids),
        )

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
            ("pit_policy", self.pit_policy),
            ("pit_time_column", self.pit_time_column),
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
class CompatibilityManifestRecord:
    """Persisted manifest record embedded into artifact metadata."""

    derived_id: str
    version: int
    manifest_hash: str
    payload: JsonDict
    created_at: str


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
class DerivedMinimalDQSummaryRecord:
    """Persisted minimal DQ record embedded into artifact metadata."""

    derived_id: str
    version: int
    run_id: str
    passed: bool
    error_count: int
    payload: JsonDict
    created_at: str
