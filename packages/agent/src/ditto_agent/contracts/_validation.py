"""Pure validation and immutability helpers for Agent contracts."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import cast

_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def normalized_text(value: str, *, field: str, maximum: int = 512) -> str:
    normalized = unicodedata.normalize("NFC", value)
    if not normalized or normalized != normalized.strip():
        raise ValueError(f"{field} must be non-empty without surrounding whitespace")
    if len(normalized) > maximum:
        raise ValueError(f"{field} exceeds {maximum} characters")
    if any(unicodedata.category(character) == "Cc" for character in normalized):
        raise ValueError(f"{field} must not contain control characters")
    return normalized


def sha256_hex(value: str, *, field: str) -> str:
    if _HASH_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")
    return value


def utc_datetime(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field} must be an offset-aware datetime")
    try:
        offset = value.utcoffset()
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{field} must be an offset-aware datetime") from exc
    if offset is None:
        raise ValueError(f"{field} must be an offset-aware datetime")
    return value.astimezone(UTC)


def positive_int(value: int, *, field: str) -> int:
    if isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def nonnegative_decimal(value: Decimal, *, field: str) -> Decimal:
    if not value.is_finite() or value < 0:
        raise ValueError(f"{field} must be a finite non-negative Decimal")
    return value


def enum_value[EnumT: Enum](
    value: EnumT, enum_type: type[EnumT], *, field: str
) -> EnumT:
    if not isinstance(value, enum_type):
        raise ValueError(f"{field} must be a {enum_type.__name__} enum value")
    return value


def normalized_unique_tuple(
    values: tuple[str, ...], *, field: str, sort: bool = False
) -> tuple[str, ...]:
    if not values:
        raise ValueError(f"{field} must be a non-empty tuple")
    normalized = tuple(
        normalized_text(value, field=f"{field} item") for value in values
    )
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field} must not contain duplicates")
    return tuple(sorted(normalized)) if sort else normalized


def freeze_json(  # noqa: C901, PLR0911, PLR0912 - closed recursive type dispatch.
    value: object, *, field: str = "value"
) -> object:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, Enum):
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"{field} must not contain non-finite numbers")
        return value.normalize() if value != 0 else Decimal(0)
    if isinstance(value, datetime):
        return utc_datetime(value, field=field)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field} must not contain non-finite numbers")
        return 0 if value == 0.0 else value
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        frozen: dict[str, object] = {}
        for key, item in mapping.items():
            if not isinstance(key, str):
                raise TypeError(f"{field} mapping keys must be strings")
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in frozen:
                raise ValueError(
                    f"{field} contains keys that collide after normalization"
                )
            frozen[normalized_key] = freeze_json(
                item, field=f"{field}.{normalized_key}"
            )
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        sequence = cast(Sequence[object], value)
        return tuple(
            freeze_json(item, field=f"{field}[{index}]")
            for index, item in enumerate(sequence)
        )
    raise TypeError(f"{field} contains unsupported type {type(value).__name__}")
