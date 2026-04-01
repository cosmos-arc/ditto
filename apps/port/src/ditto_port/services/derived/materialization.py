"""Shim — 真实实现已迁移至 ditto_app.process.materialization."""

from ditto_app.process.materialization import (
    DerivedInputProvider,
    InMemoryDerivedInputProvider,
    InputContext,
    MissingDependencyError,
    UnavailableDerivedInputProvider,
    build_manifest_record,
    build_minimal_dq_record,
    dependency_refs,
    earliest_pending_start,
    hydrate_spec,
    prepare_input_frame,
    resolve_shadow_baseline,
)
from ditto_app.query._utils import now_iso

__all__ = [
    "DerivedInputProvider",
    "InMemoryDerivedInputProvider",
    "InputContext",
    "MissingDependencyError",
    "UnavailableDerivedInputProvider",
    "build_manifest_record",
    "build_minimal_dq_record",
    "dependency_refs",
    "earliest_pending_start",
    "hydrate_spec",
    "now_iso",
    "prepare_input_frame",
    "resolve_shadow_baseline",
]
