"""Private canonical JSON implementation shared by Agent subpackages."""

from __future__ import annotations

import hashlib
import math
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import cast

import orjson


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("canonical JSON does not support non-finite Decimal values")
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")


def _normalize(  # noqa: C901, PLR0911, PLR0912 - closed recursive type dispatch.
    value: object,
) -> object:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, Enum):
        return _normalize(value.value)
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON does not support non-finite float values")
        if value == 0.0:
            return 0
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("canonical JSON datetime must be offset-aware")
        return (
            value.astimezone(UTC)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _normalize(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        normalized: dict[str, object] = {}
        for key, item in mapping.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON mapping keys must be strings")
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in normalized:
                raise ValueError(
                    "canonical JSON keys collide after Unicode normalization"
                )
            normalized[normalized_key] = _normalize(item)
        return normalized
    if isinstance(value, (list, tuple)):
        sequence = cast(Sequence[object], value)
        return [_normalize(item) for item in sequence]
    raise TypeError(f"unsupported canonical JSON type: {type(value).__name__}")


def canonical_bytes(value: object) -> bytes:
    """Return deterministic UTF-8 JSON after semantic normalization."""
    return orjson.dumps(_normalize(value), option=orjson.OPT_SORT_KEYS)


def canonical_sha256(value: object) -> str:
    """Return the lowercase SHA-256 digest of canonical bytes."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


__all__ = ["canonical_bytes", "canonical_sha256"]
