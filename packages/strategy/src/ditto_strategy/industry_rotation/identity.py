"""Canonical identity functions for industry-rotation artifacts."""

from __future__ import annotations

from ditto_strategy.industry_rotation.contracts import (
    IndustryRotationInputBundle,
    IndustryRotationSnapshot,
    canonical_input_hash,
    canonical_snapshot_hash,
)

__all__ = [
    "canonical_industry_rotation_input_hash",
    "canonical_industry_rotation_snapshot_hash",
]


def canonical_industry_rotation_input_hash(
    value: IndustryRotationInputBundle,
) -> str:
    """Hash all temporal, lineage, membership, algorithm, and factor inputs."""
    return canonical_input_hash(value)


def canonical_industry_rotation_snapshot_hash(
    value: IndustryRotationSnapshot,
) -> str:
    """Hash the complete ordered ranked result without self-reference."""
    return canonical_snapshot_hash(value)
