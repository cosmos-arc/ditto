"""Unified materialization contracts for Phase 3."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_features.derived_types import MaterializationProfile
from ditto_features.expression.contracts import (
    Analysis,
    AnalysisWarning,
    CompiledDerivedExpression,
    CompileIdentity,
)
from ditto_features.materialization.models import (
    DerivedRunMode,
    DerivedRunStatus,
    DerivedRunTrigger,
)

__all__ = [
    "Analysis",
    "AnalysisWarning",
    "CompileIdentity",
    "CompiledDerivedExpression",
    "DerivedExecutionPlan",
    "DerivedInvalidationEvent",
    "DerivedMaterializationRequest",
    "DerivedMaterializationResult",
]


@dataclass(frozen=True)
class DerivedExecutionPlan:
    """Resolved execution window and output partitions for one run."""

    derived_id: str
    version: int
    profile: MaterializationProfile
    mode: DerivedRunMode
    request_start: str
    request_end: str
    compute_start: str
    compute_end: str
    partitions: tuple[str, ...]
    lookback: int
    requires_full_day: bool


@dataclass(frozen=True)
class DerivedMaterializationRequest:
    """Public request DTO for one materialization run."""

    derived_id: str
    version: int
    mode: DerivedRunMode
    request_start: str
    request_end: str
    trigger: DerivedRunTrigger
    source_snapshot_id: str | None
    force_recompile: bool = False


@dataclass(frozen=True)
class DerivedMaterializationResult:
    """Stable result DTO returned by the materialization service."""

    run_id: str
    derived_id: str
    version: int
    profile: MaterializationProfile
    status: DerivedRunStatus
    rows_written: int
    partitions_written: tuple[str, ...]
    coverage_start: str | None
    coverage_end: str | None


@dataclass(frozen=True)
class DerivedInvalidationEvent:
    """Source change event that fans out into downstream repair work."""

    source_domain: str
    source_dataset: str
    change_date: str
    affected_start: str
    affected_end: str
    source_snapshot_id: str | None
    root_dependency_ref: str
