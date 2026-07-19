"""Immutable canonical JSON value snapshots for strategy identity objects."""

from __future__ import annotations

import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import Literal, NoReturn, TypeGuard

from ditto_strategy.errors import StrategySpecError

__all__ = [
    "canonical_json_value",
    "canonicalize_float_identity",
    "freeze_json_mapping",
]

_CanonicalContainerMode = Literal["json", "frozen"]


def canonicalize_float_identity(value: float) -> float:
    """Collapse signed zero spellings that compare equal in domain identity."""
    return 0.0 if value == 0.0 else value


def _raise_canonical_value_error(
    message: str,
    *,
    field_name: str,
    value: object,
    reason: str = "invalid_canonical_json_value",
) -> NoReturn:
    raise StrategySpecError(
        message,
        details={
            "field_name": field_name,
            "reason": reason,
            "actual_type": type(value).__name__,
        },
    )


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_sequence(
    value: object,
) -> TypeGuard[tuple[object, ...] | list[object]]:
    return isinstance(value, (tuple, list))


def _canonical_json_value(
    value: object,
    *,
    field_name: str,
    active_container_ids: set[int],
    container_mode: _CanonicalContainerMode,
    invalid_reason: str,
) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _raise_canonical_value_error(
                (
                    f"{field_name} has no canonical JSON identity"
                    if invalid_reason == "non_canonical_value"
                    else f"{field_name} must be finite"
                ),
                field_name=field_name,
                value=value,
                reason=invalid_reason,
            )
        return canonicalize_float_identity(value)
    if _is_object_mapping(value):
        return _canonical_mapping(
            value,
            field_name=field_name,
            active_container_ids=active_container_ids,
            container_mode=container_mode,
            invalid_reason=invalid_reason,
        )
    if _is_object_sequence(value):
        return _canonical_sequence(
            value,
            field_name=field_name,
            active_container_ids=active_container_ids,
            container_mode=container_mode,
            invalid_reason=invalid_reason,
        )
    _raise_canonical_value_error(
        f"{field_name} is not a canonical JSON value",
        field_name=field_name,
        value=value,
        reason=invalid_reason,
    )


def _enter_container(
    value: object,
    *,
    field_name: str,
    active_container_ids: set[int],
) -> int:
    container_id = id(value)
    if container_id in active_container_ids:
        _raise_canonical_value_error(
            f"{field_name} contains a cyclic canonical JSON value",
            field_name=field_name,
            value=value,
            reason="cyclic_canonical_json_value",
        )
    active_container_ids.add(container_id)
    return container_id


def _canonical_mapping(
    value: Mapping[object, object],
    *,
    field_name: str,
    active_container_ids: set[int],
    container_mode: _CanonicalContainerMode,
    invalid_reason: str,
) -> Mapping[str, object]:
    container_id = _enter_container(
        value,
        field_name=field_name,
        active_container_ids=active_container_ids,
    )
    try:
        canonical: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                _raise_canonical_value_error(
                    f"{field_name} keys must be strings",
                    field_name=field_name,
                    value=key,
                    reason=invalid_reason,
                )
            canonical[key] = _canonical_json_value(
                item,
                field_name=f"{field_name}.{key}",
                active_container_ids=active_container_ids,
                container_mode=container_mode,
                invalid_reason=invalid_reason,
            )
        if container_mode == "frozen":
            return MappingProxyType(canonical)
        return canonical
    finally:
        active_container_ids.remove(container_id)


def _canonical_sequence(
    value: tuple[object, ...] | list[object],
    *,
    field_name: str,
    active_container_ids: set[int],
    container_mode: _CanonicalContainerMode,
    invalid_reason: str,
) -> tuple[object, ...] | list[object]:
    container_id = _enter_container(
        value,
        field_name=field_name,
        active_container_ids=active_container_ids,
    )
    try:
        canonical = [
            _canonical_json_value(
                item,
                field_name=f"{field_name}[{index}]",
                active_container_ids=active_container_ids,
                container_mode=container_mode,
                invalid_reason=invalid_reason,
            )
            for index, item in enumerate(value)
        ]
        if container_mode == "frozen":
            return tuple(canonical)
        return canonical
    finally:
        active_container_ids.remove(container_id)


def canonical_json_value(value: object, *, field_name: str) -> object:
    """Return a mutable-container canonical JSON value for stable codecs."""
    return _canonical_json_value(
        value,
        field_name=field_name,
        active_container_ids=set(),
        container_mode="json",
        invalid_reason="non_canonical_value",
    )


def freeze_json_mapping(value: object, *, field_name: str) -> Mapping[str, object]:
    """Validate and recursively snapshot a JSON object as immutable values."""
    if not _is_object_mapping(value):
        _raise_canonical_value_error(
            f"{field_name} must be a mapping",
            field_name=field_name,
            value=value,
        )
    return _canonical_mapping(
        value,
        field_name=field_name,
        active_container_ids=set(),
        container_mode="frozen",
        invalid_reason="invalid_canonical_json_value",
    )
