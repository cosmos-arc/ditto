"""Shim — 真实实现已迁移至 ditto_app.process.materialization."""

from ditto_app.process.materialization import (
    DerivedInputProvider,
    InMemoryDerivedInputProvider,
    InputContext,
    MissingDependencyError,
    UnavailableDerivedInputProvider,
    earliest_pending_start,
    hydrate_spec,
    prepare_input_frame,
)

__all__ = [
    "DerivedInputProvider",
    "InMemoryDerivedInputProvider",
    "InputContext",
    "MissingDependencyError",
    "UnavailableDerivedInputProvider",
    "earliest_pending_start",
    "hydrate_spec",
    "prepare_input_frame",
]
