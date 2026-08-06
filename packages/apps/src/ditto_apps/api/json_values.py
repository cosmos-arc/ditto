"""Fail-closed JSON normalization at the HTTP transport boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from ditto_platform.foundation.json_types import JsonValue


def to_json_value(value: object) -> JsonValue:
    """Detach application values into JSON-native containers or reject drift."""
    if isinstance(value, Mapping):
        return to_json_mapping(cast("Mapping[object, object]", value))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sequence = cast("Sequence[object]", value)
        return [to_json_value(item) for item in sequence]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError("HTTP transport value must be JSON-compatible")


def to_json_mapping[K, V](value: Mapping[K, V]) -> dict[str, JsonValue]:
    """Normalize a JSON object while rejecting non-string keys."""
    result: dict[str, JsonValue] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError("HTTP transport mapping key must be str")
        result[key] = to_json_value(item)
    return result


def to_object_mapping(value: Mapping[str, JsonValue]) -> dict[str, object]:
    """Widen validated request JSON for legacy application command contracts."""
    result: dict[str, object] = {}
    for key, item in value.items():
        result[key] = item
    return result
