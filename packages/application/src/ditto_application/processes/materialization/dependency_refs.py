"""Dependency reference classification for durable persistence."""

from __future__ import annotations

from ditto_features.materialization.dependency_registry import (
    dependency_refs as _dependency_refs,
)

__all__ = ["dependency_refs"]


def dependency_refs(
    dependencies: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    """Classify each dependency into (kind, ref) pairs for persistence."""
    return tuple((ref.kind, ref.ref) for ref in _dependency_refs(dependencies))
