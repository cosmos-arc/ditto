"""Shared canonical value rules for R3 comparison evidence."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import date
from enum import StrEnum
from types import MappingProxyType
from typing import NoReturn, cast

from ditto_application.exceptions import AppProcessError

__all__ = [
    "canonical_text",
    "canonical_value",
    "comparison_error",
    "deep_freeze",
    "finite",
]


def comparison_error(reason: str, **details: object) -> NoReturn:
    """Raise the normalized comparison-boundary error."""
    raise AppProcessError(
        "candidate comparison evidence is invalid",
        details={"code": "SPEC_INVALID", "reason": reason, **details},
    )


def canonical_text(value: object, field_name: str) -> str:
    """Validate and return one non-empty, unpadded identity string."""
    if type(value) is not str or not value or value != value.strip():
        comparison_error("invalid_comparison_identity", field=field_name)
    return value


def finite(value: object) -> float | None:
    """Normalize a finite real scalar while rejecting booleans."""
    if (
        type(value) not in {int, float}
        or isinstance(value, bool)
        or not math.isfinite(cast("float", value))
    ):
        return None
    return float(cast("int | float", value))


def deep_freeze(value: object) -> object:
    """Recursively detach mappings and sequences from caller mutation."""
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                key: deep_freeze(item)
                for key, item in cast("Mapping[object, object]", value).items()
            }
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(deep_freeze(item) for item in cast("Sequence[object]", value))
    return value


def _canonical_mapping(value: Mapping[object, object]) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    for key in sorted(value, key=lambda item: (type(item).__name__, str(item))):
        if type(key) not in {int, str}:
            comparison_error("unsupported_canonical_mapping_key")
        entries.append(
            {
                "key_type": type(key).__name__,
                "key": key,
                "value": canonical_value(value[key]),
            }
        )
    return {"mapping_entries": entries}


def canonical_value(  # noqa: PLR0911 - explicit canonical type dispatcher
    value: object,
) -> object:
    """Encode nested diagnostic values without repr or mapping iteration drift."""
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            comparison_error("non_finite_canonical_evidence")
        return value
    if isinstance(value, StrEnum):
        return value.value
    if type(value) is date:
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "record_type": type(value).__name__,
            "fields": [
                [item.name, canonical_value(getattr(value, item.name))]
                for item in fields(value)
            ],
        }
    if isinstance(value, Mapping):
        return _canonical_mapping(cast("Mapping[object, object]", value))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [canonical_value(item) for item in cast("Sequence[object]", value)]
    comparison_error(
        "unsupported_canonical_evidence_value",
        value_type=type(value).__name__,
    )


# Transitional internal aliases keep the split core modules source-compatible.
_canonical_text = canonical_text
_canonical_value = canonical_value
_comparison_error = comparison_error
_deep_freeze = deep_freeze
_finite = finite
