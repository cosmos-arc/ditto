"""Internal shared utilities for ditto_strategy — NOT public API."""

from __future__ import annotations

from datetime import UTC, datetime

__all__ = ["utc_now"]


def utc_now() -> str:
    """
    Return current UTC timestamp in RFC 3339 format (second precision).

    Format: ``2026-05-11T12:34:56Z``
    No microseconds; uses ``Z`` suffix to denote UTC.

    Use case: SQLite row timestamps for strategy run lifecycle (started_at,
    finished_at) where second-level granularity is sufficient and compact
    storage is preferred.

    See also: ``ditto_application.config.helpers.now_iso`` — ISO 8601 format
    with microsecond precision, used for application-layer manifest and
    publication records.
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
