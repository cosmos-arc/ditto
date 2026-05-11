"""Application config helper utilities."""

from __future__ import annotations

from datetime import UTC, datetime


def now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(UTC).isoformat()
