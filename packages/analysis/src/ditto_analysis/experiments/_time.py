"""Lossless UTC microsecond conversion shared by experiment persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ditto_analysis.experiments._validation import require_utc_datetime

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECONDS_PER_SECOND = 1_000_000
_SECONDS_PER_DAY = 86_400


def epoch_us(value: datetime) -> int:
    """Encode UTC datetime without a floating-point timestamp round trip."""
    require_utc_datetime(value, "datetime")
    delta = value - _EPOCH
    return (
        delta.days * _SECONDS_PER_DAY + delta.seconds
    ) * _MICROSECONDS_PER_SECOND + delta.microseconds


def datetime_from_epoch_us(value: int) -> datetime:
    """Decode an epoch-microsecond integer without floating-point division."""
    return _EPOCH + timedelta(microseconds=value)
