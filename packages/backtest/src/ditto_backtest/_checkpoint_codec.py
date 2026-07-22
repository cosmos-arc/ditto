"""Strict JSON payload readers shared by backtest checkpoint snapshots."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import cast


def finite_float(value: object, name: str) -> float:
    """Normalize one writer-side numeric value and reject non-finite data."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        msg = f"checkpoint field {name!r} must be numeric"
        raise ValueError(msg)
    resolved = float(value)
    if not math.isfinite(resolved):
        msg = f"checkpoint field {name!r} must be finite"
        raise ValueError(msg)
    return resolved


def optional_finite_float(value: object, name: str) -> float | None:
    """Normalize a nullable writer-side numeric checkpoint value."""
    if value is None:
        return None
    return finite_float(value, name)


def payload_mapping(payload: object) -> Mapping[str, object]:
    """Return payload as a string-keyed mapping or raise a checkpoint error."""
    if not isinstance(payload, Mapping):
        msg = "checkpoint payload must be an object"
        raise ValueError(msg)
    return cast(Mapping[str, object], payload)


def payload_sequence(
    payload: Mapping[str, object],
    key: str,
) -> tuple[object, ...]:
    """Read a list-like checkpoint field, defaulting missing fields to empty."""
    value = payload.get(key, ())
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        msg = f"checkpoint field {key!r} must be a sequence"
        raise ValueError(msg)
    return tuple(cast(Sequence[object], value))


def payload_str(payload: Mapping[str, object], key: str) -> str:
    """Read a required string checkpoint field."""
    value = payload_required(payload, key)
    if not isinstance(value, str):
        msg = f"checkpoint field {key!r} must be a string"
        raise ValueError(msg)
    return value


def payload_optional_str(payload: Mapping[str, object], key: str) -> str | None:
    """Read an optional string checkpoint field."""
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        msg = f"checkpoint field {key!r} must be a string or null"
        raise ValueError(msg)
    return value


def payload_int(payload: Mapping[str, object], key: str) -> int:
    """Read a required integer checkpoint field."""
    value = payload_required(payload, key)
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"checkpoint field {key!r} must be an integer"
        raise ValueError(msg)
    return value


def payload_optional_int(
    payload: Mapping[str, object],
    key: str,
    *,
    default: int = 0,
) -> int:
    """Read an optional integer checkpoint field with a safe default."""
    if key not in payload:
        return default
    return payload_int(payload, key)


def payload_float(payload: Mapping[str, object], key: str) -> float:
    """Read a required numeric checkpoint field."""
    value = payload_required(payload, key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        msg = f"checkpoint field {key!r} must be numeric"
        raise ValueError(msg)
    return finite_float(value, key)


def payload_optional_float(
    payload: Mapping[str, object],
    key: str,
) -> float | None:
    """Read an optional numeric checkpoint field."""
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        msg = f"checkpoint field {key!r} must be numeric or null"
        raise ValueError(msg)
    return finite_float(value, key)


def payload_required(payload: Mapping[str, object], key: str) -> object:
    """Read a required checkpoint field."""
    if key not in payload:
        msg = f"checkpoint field {key!r} is required"
        raise ValueError(msg)
    return payload[key]


def require_exact_keys(
    payload: object,
    keys: tuple[str, ...],
    *,
    subject: str = "runtime state",
) -> None:
    """Reject missing and unknown members in one versioned checkpoint object."""
    data = payload_mapping(payload)
    expected = frozenset(keys)
    missing = tuple(key for key in keys if key not in data)
    if missing:
        message = f"checkpoint {subject} is missing required fields: {missing!r}"
        raise ValueError(message)
    unexpected = tuple(sorted(set(data) - expected))
    if unexpected:
        raise ValueError(f"checkpoint {subject} has unexpected fields: {unexpected!r}")
