"""Shared time-semantics constants for manifest and audit records."""

from __future__ import annotations

__all__ = [
    "DEFAULT_PIT_TIME_COLUMN",
    "PIT_POLICY_FAIL_CLOSED",
]

DEFAULT_PIT_TIME_COLUMN = "knowledge_date"
PIT_POLICY_FAIL_CLOSED = "knowledge_date_fail_closed"
