"""Spec validation helpers for ditto_features."""

from __future__ import annotations

from ditto_features.derived_types import DerivedSpec
from ditto_features.errors import DerivedNotImplementedError

__all__ = ["validate_derived_spec"]


def validate_derived_spec(spec: DerivedSpec) -> None:
    """Validate current v1 boundaries. Raises DerivedNotImplementedError."""
    if len(spec.entity_keys) != 1:
        raise DerivedNotImplementedError(
            feature=f"复合键已预留、暂未实现: entity_keys={spec.entity_keys}",
            derived_id=spec.id,
        )

    if spec.grain == "1m":
        raise DerivedNotImplementedError(
            feature="grain='1m' 已预留、暂未实现",
            derived_id=spec.id,
        )
