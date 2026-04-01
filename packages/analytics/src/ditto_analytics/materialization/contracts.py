"""Unified materialization contracts for Phase 3."""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl
from ditto_engine.engine.specs import MaterializationProfile

from ditto_analytics.materialization.models import (
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
class AnalysisWarning:
    """Lightweight compile-time warning produced during expression analysis."""

    message: str
    error_code: str


@dataclass(frozen=True)
class Analysis:
    """Semantic analysis metadata extracted from a derived expression."""

    dependencies: tuple[str, ...]
    operator_names: tuple[str, ...]
    lookback: int
    requires_full_day: bool
    scope: str
    output_schema: tuple[str, ...] = ("value",)
    warnings: tuple[AnalysisWarning, ...] = ()


@dataclass(frozen=True)
class CompileIdentity:
    """Stable compile identity for cache keys and artifact metadata."""

    compile_input_hash: str
    operator_fingerprint: str
    compiler_fingerprint: str
    cache_key: str
    engine_codegen_version: str
    analysis_version: str
    polars_version: str
    expr_serialization_format: str
    operator_versions: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    global_compile_flags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompiledDerivedExpression:
    """Compiled derived expression plus its semantic metadata."""

    derived_id: str
    version: int
    expr: pl.Expr
    analysis: Analysis
    compile_identity: CompileIdentity


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
