"""Expression-layer compile contracts."""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

__all__ = [
    "Analysis",
    "AnalysisWarning",
    "CompileIdentity",
    "CompiledDerivedExpression",
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
    """Compiled expression plus semantic metadata."""

    derived_id: str
    version: int
    expr: pl.Expr
    analysis: Analysis
    compile_identity: CompileIdentity
