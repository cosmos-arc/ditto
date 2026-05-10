"""Internal shared utilities for ditto_strategy — NOT public API."""

from __future__ import annotations

from datetime import UTC, datetime

__all__ = ["utc_now"]


def utc_now() -> str:
    """Return RFC3339 UTC timestamp."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
