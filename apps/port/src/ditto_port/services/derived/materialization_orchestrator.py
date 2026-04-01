"""Shim — 真实实现已迁移至 ditto_app.process.materialization."""

from ditto_app.process.materialization import (
    DerivedMaterializationOrchestrator,
    UniverseProvider,
)

__all__ = [
    "DerivedMaterializationOrchestrator",
    "UniverseProvider",
]
