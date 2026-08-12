"""Stable EOD failure classification shared by the coordinator."""

from __future__ import annotations

from typing import Literal

from ditto_application.exceptions import AppProcessError

__all__ = ["RunLifecycleTransitionError", "failure_outcome"]


class RunLifecycleTransitionError(RuntimeError):
    """A lifecycle write failed, so completion must not be exposed."""


def failure_outcome(
    exc: Exception,
    *,
    stage: str,
) -> tuple[str, Literal["blocked", "failed"]]:
    """Compress internal exceptions into stable non-sensitive machine codes."""
    if isinstance(exc, AppProcessError):
        code = exc.details.get("code")
        blocked_code = {
            "ACCOUNT_BASELINE_MISSING": "ACCOUNT_BASELINE_MISSING",
            "PORTFOLIO_CONSTRUCTION_BLOCKED": "PORTFOLIO_CONSTRUCTION_BLOCKED",
        }.get(code if isinstance(code, str) else "")
        if blocked_code is not None:
            return blocked_code, "blocked"
    if isinstance(exc, RunLifecycleTransitionError) or stage.startswith("mark_"):
        return "RUN_LIFECYCLE_TRANSITION_FAILED", "failed"
    failure_code = {
        "construct_portfolio": "PORTFOLIO_CONSTRUCTION_FAILED",
        "create_run": "RUN_LIFECYCLE_CREATE_FAILED",
        "finalize_signals": "SIGNAL_PACKAGE_FINALIZE_FAILED",
        "publish_signals": "SIGNAL_PACKAGE_PUBLISH_FAILED",
    }.get(stage, "STRATEGY_EXECUTION_FAILED")
    return failure_code, "failed"
