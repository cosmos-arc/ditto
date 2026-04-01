"""Shared utilities for app query services."""

from __future__ import annotations

from datetime import UTC, datetime

__all__ = ["now_iso"]


def now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(UTC).isoformat()
