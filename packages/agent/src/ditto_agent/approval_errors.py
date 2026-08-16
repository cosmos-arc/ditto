"""Stable fail-closed errors for the governed approval lifecycle."""

from __future__ import annotations

from ditto_agent.runtime.orchestrator import ApprovalSuspensionError


class ApprovalRuntimeError(ApprovalSuspensionError):
    """Base approval lifecycle error with a stable machine reason code."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class ApprovalRuntimeViolation(ApprovalRuntimeError, PermissionError):
    """Persisted or current approval authority failed validation."""


class ApprovalRuntimeConflict(ApprovalRuntimeError):
    """Current run/request state cannot consume the persisted continuation."""


class ApprovalRuntimeUnavailable(ApprovalRuntimeError):
    """Provider or required persistence became unavailable during recovery."""


__all__ = [
    "ApprovalRuntimeConflict",
    "ApprovalRuntimeError",
    "ApprovalRuntimeUnavailable",
    "ApprovalRuntimeViolation",
]
