"""Application config helper utilities."""

from __future__ import annotations

from datetime import UTC, datetime


def now_iso() -> str:
    """
    Return current UTC timestamp in ISO 8601 format with microsecond precision.

    Format: ``2026-05-11T12:34:56.789012+00:00``
    Includes microseconds and UTC offset (``+00:00``).

    Use case: internal timestamps for materialization manifests, publication
    records, and research dataset metadata where full precision is desired.

    See also: ``ditto_strategy._internal.utc_now`` — RFC 3339 format without
    microseconds, used for SQLite storage where sub-second precision is
    unnecessary.
    """
    return datetime.now(UTC).isoformat()
