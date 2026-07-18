"""Immutable canonical JSON value snapshots for strategy identity objects."""

from __future__ import annotations

import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import NoReturn, TypeGuard

from ditto_strategy.errors import StrategySpecError

__all__ = ["freeze_json_mapping"]


def _raise_canonical_value_error(
    message: str,
    *,
    field_name: str,
    value: object,
) -> NoReturn:
    raise StrategySpecError(
        message,
        details={
            "field_name": field_name,
            "reason": "invalid_canonical_json_value",
            "actual_type": type(value).__name__,
        },
    )


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_sequence(
    value: object,
) -> TypeGuard[tuple[object, ...] | list[object]]:
    return isinstance(value, (tuple, list))


def _freeze_json_value(value: object, *, field_name: str) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _raise_canonical_value_error(
                f"{field_name} must be finite",
                field_name=field_name,
                value=value,
            )
        return value
    if _is_object_mapping(value):
        return _freeze_mapping(value, field_name=field_name)
    if _is_object_sequence(value):
        return tuple(
            _freeze_json_value(item, field_name=f"{field_name}[{index}]")
            for index, item in enumerate(value)
        )
    _raise_canonical_value_error(
        f"{field_name} is not a canonical JSON value",
        field_name=field_name,
        value=value,
    )


def _freeze_mapping(
    value: Mapping[object, object],
    *,
    field_name: str,
) -> Mapping[str, object]:
    frozen: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            _raise_canonical_value_error(
                f"{field_name} keys must be strings",
                field_name=field_name,
                value=key,
            )
        frozen[key] = _freeze_json_value(
            item,
            field_name=f"{field_name}.{key}",
        )
    return MappingProxyType(frozen)


def freeze_json_mapping(value: object, *, field_name: str) -> Mapping[str, object]:
    """Validate and recursively snapshot a JSON object as immutable values."""
    if not _is_object_mapping(value):
        _raise_canonical_value_error(
            f"{field_name} must be a mapping",
            field_name=field_name,
            value=value,
        )
    return _freeze_mapping(value, field_name=field_name)
