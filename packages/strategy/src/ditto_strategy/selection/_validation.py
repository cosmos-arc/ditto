"""Shared validation primitives for selection-owned value objects."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, cast

from ditto_strategy.errors import StrategySpecError

__all__ = [
    "error",
    "finite",
    "optional_bool",
    "optional_finite",
    "optional_non_negative_int",
    "optional_text",
    "ordered_sequence",
    "positive_int",
    "text",
    "text_set",
    "unit",
    "validate_temporal_visibility",
]


class _TemporalVisibility(Protocol):
    @property
    def as_of(self) -> datetime: ...

    @property
    def knowledge_cutoff(self) -> datetime: ...

    @property
    def publication_cutoff(self) -> datetime: ...


def _error(message: str, *, reason: str, **details: object) -> StrategySpecError:
    return StrategySpecError(message, details={"reason": reason, **details})


def _validate_temporal_visibility(value: _TemporalVisibility) -> None:
    """Validate the shared PIT boundary on input and result contracts."""
    for field_name in ("as_of", "knowledge_cutoff", "publication_cutoff"):
        timestamp = getattr(value, field_name)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise _error(
                f"selection {field_name} must be timezone-aware",
                reason="invalid_selection_time",
                field_name=field_name,
            )
    if not value.publication_cutoff <= value.knowledge_cutoff <= value.as_of:
        raise _error(
            "selection cutoffs exceed their visibility boundary",
            reason="invalid_selection_cutoff",
        )


def _text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise _error(
            f"selection {field_name} must be normalized non-empty text",
            reason="invalid_selection_text",
            field_name=field_name,
        )
    return value


def _optional_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _text(value, field_name=field_name)


def _ordered_sequence[ItemT](
    value: object,
    *,
    item_type: type[ItemT],
    field_name: str,
) -> tuple[ItemT, ...]:
    if isinstance(value, str | bytes | bytearray) or not isinstance(value, Sequence):
        raise _error(
            f"selection {field_name} must be an ordered sequence",
            reason="invalid_selection_sequence",
            field_name=field_name,
        )
    copied = tuple(cast("Sequence[object]", value))
    if any(not isinstance(item, item_type) for item in copied):
        raise _error(
            f"selection {field_name} contains an invalid item",
            reason="invalid_selection_sequence_item",
            field_name=field_name,
        )
    return cast("tuple[ItemT, ...]", copied)


def _text_set(value: object, *, field_name: str) -> tuple[str, ...]:
    copied = _ordered_sequence(value, item_type=str, field_name=field_name)
    normalized = tuple(_text(item, field_name=field_name) for item in copied)
    if len(set(normalized)) != len(normalized):
        raise _error(
            f"selection {field_name} must be unique",
            reason="duplicate_selection_identity",
            field_name=field_name,
        )
    return tuple(sorted(normalized))


def _finite(value: object, *, field_name: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _error(
            f"selection {field_name} must be finite",
            reason="invalid_selection_number",
            field_name=field_name,
        )
    normalized = float(value)
    if not math.isfinite(normalized) or (minimum is not None and normalized < minimum):
        raise _error(
            f"selection {field_name} must be finite",
            reason="invalid_selection_number",
            field_name=field_name,
        )
    return 0.0 if normalized == 0.0 else normalized


def _optional_finite(
    value: object,
    *,
    field_name: str,
    minimum: float | None = None,
) -> float | None:
    if value is None:
        return None
    return _finite(value, field_name=field_name, minimum=minimum)


def _unit(value: object, *, field_name: str) -> float:
    normalized = _finite(value, field_name=field_name)
    if not -1.0 <= normalized <= 1.0:
        raise _error(
            f"selection {field_name} must be a finite unit score",
            reason="invalid_selection_unit_score",
            field_name=field_name,
        )
    return normalized


def _positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _error(
            f"selection {field_name} must be a positive integer",
            reason="invalid_selection_integer",
            field_name=field_name,
        )
    return value


def _optional_non_negative_int(value: object, *, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _error(
            f"selection {field_name} must be a non-negative integer",
            reason="invalid_selection_integer",
            field_name=field_name,
        )
    return value


def _optional_bool(value: object, *, field_name: str) -> bool | None:
    if value is not None and not isinstance(value, bool):
        raise _error(
            f"selection {field_name} must be bool or None",
            reason="invalid_selection_boolean",
            field_name=field_name,
        )
    return value


# Public aliases let sibling contract modules reuse one validation vocabulary
# without treating module-private implementation names as package APIs.
error = _error
validate_temporal_visibility = _validate_temporal_visibility
text = _text
optional_text = _optional_text
ordered_sequence = _ordered_sequence
text_set = _text_set
finite = _finite
optional_finite = _optional_finite
unit = _unit
positive_int = _positive_int
optional_non_negative_int = _optional_non_negative_int
optional_bool = _optional_bool
