"""Stable event reason selection without importing analysis-owned contracts."""

from __future__ import annotations

from enum import StrEnum


def attempt_reason(status: StrEnum, failure_code: StrEnum | None) -> str:
    """Map an attempt transition to its canonical event reason."""
    if str(status) == "running":
        return "first_attempt_started"
    if str(status) == "completed":
        return "first_attempt_completed"
    if failure_code is not None and str(failure_code) == "candidate_failed":
        return "candidate_attempt_failed"
    return "system_attempt_failed"


def fold_reason(status: StrEnum, failure_code: StrEnum | None) -> str:
    """Map a fold transition to its canonical event reason."""
    if str(status) == "completed":
        return "fold_completed"
    if str(status) == "cancelled":
        return "candidate_isolated_after_failure"
    if failure_code is not None and str(failure_code) == "candidate_failed":
        return "candidate_fold_failed"
    return "system_fold_failed"
