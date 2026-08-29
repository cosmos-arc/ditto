"""Strict scalar codecs for Agent SQLite rows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ditto_agent.contracts._validation import normalized_text, utc_datetime


def epoch_us(value: datetime, *, field: str) -> int:
    """Encode an aware datetime as exact UTC epoch microseconds."""
    normalized = utc_datetime(value, field=field)
    offset = normalized - datetime(1970, 1, 1, tzinfo=UTC)
    return (
        offset.days * 86_400_000_000 + offset.seconds * 1_000_000 + offset.microseconds
    )


def datetime_from_epoch_us(value: int, *, field: str) -> datetime:
    """Decode a positive epoch-microsecond database value."""
    if isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} must be a positive epoch-microsecond integer")
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=value)


def optional_datetime_from_epoch_us(
    value: int | None, *, field: str
) -> datetime | None:
    """Decode one nullable epoch-microsecond value."""
    return None if value is None else datetime_from_epoch_us(value, field=field)


def decimal_text(value: Decimal) -> str:
    """Encode a finite Decimal without exponent or signed zero drift."""
    if not value.is_finite() or value < 0:
        raise ValueError("decimal value must be finite and non-negative")
    normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


def text(value: str, *, field: str, maximum: int = 512) -> str:
    """Normalize an identifier or bounded human-readable field."""
    return normalized_text(value, field=field, maximum=maximum)


__all__ = [
    "datetime_from_epoch_us",
    "decimal_text",
    "epoch_us",
    "optional_datetime_from_epoch_us",
    "text",
]
