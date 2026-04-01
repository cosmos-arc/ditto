"""Shim — 真实实现已迁移至 ditto_app.process.materialization."""

from ditto_app.process.materialization import (
    build_manifest_record,
    dependency_refs,
    resolve_shadow_baseline,
)

__all__ = [
    "build_manifest_record",
    "dependency_refs",
    "resolve_shadow_baseline",
]
