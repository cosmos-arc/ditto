"""Calendar-derived workload shared by live planning and launch reconstruction."""

from __future__ import annotations

from datetime import date

from ditto_application.processes.experiments._process_error import (
    experiment_process_error,
)
from ditto_application.processes.experiments.planning import ValidationWorkload
from ditto_application.research_validation_protocol import (
    ValidationProtocolPlan,
    ValidationProtocolRequest,
)

__all__ = ["compile_validation_workload"]


def compile_validation_workload(
    protocol: ValidationProtocolRequest,
    plan: ValidationProtocolPlan,
) -> ValidationWorkload:
    """Count exact protocol sessions inside every compiled validation window."""
    if (
        type(protocol) is not ValidationProtocolRequest
        or type(plan) is not ValidationProtocolPlan
        or plan.reserved_holdout is None
    ):
        raise experiment_process_error(
            "launch workload requires exact protocol and holdout plan"
        )

    def session_count(start: date, end: date) -> int:
        return sum(start <= session <= end for session in protocol.trading_sessions)

    return ValidationWorkload(
        fold_session_counts=tuple(
            session_count(fold.test_window.start, fold.test_window.end)
            for fold in plan.folds
        ),
        holdout_session_count=session_count(
            plan.reserved_holdout.test_window.start,
            plan.reserved_holdout.test_window.end,
        ),
    )
