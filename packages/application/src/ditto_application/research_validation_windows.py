"""Leakage-safe deterministic window construction for research validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from ditto_analysis.experiments.persistence import DateWindow, FoldRole

from ditto_application.research_validation_calendar import (
    CalendarMonth,
)
from ditto_application.research_validation_calendar import (
    fail_validation as _fail,
)

__all__ = [
    "ReservedHoldoutPlan",
    "ValidationEligibility",
    "ValidationFoldPlan",
    "ValidationReasonCode",
]

_VALIDATION_RESERVE_MONTHS = 36
_WALK_FORWARD_MONTHS = 12
_MIN_RESEARCH_MONTHS = _VALIDATION_RESERVE_MONTHS + 1
_MIN_PROMOTION_MONTHS = 96


class ValidationEligibility(StrEnum):
    """Governance capability granted by the continuous eligible history."""

    PROMOTION_ELIGIBLE = "promotion_eligible"
    RESEARCH_ONLY = "research_only"
    BLOCKED = "blocked"


class ValidationReasonCode(StrEnum):
    """Stable explanations for a downgraded validation protocol."""

    COVERAGE_CONTINUITY_INTERRUPTED = "COVERAGE_CONTINUITY_INTERRUPTED"
    PROMOTION_HISTORY_INSUFFICIENT = "PROMOTION_HISTORY_INSUFFICIENT"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"


def _classify_history(
    month_count: int,
    *,
    coverage_interrupted: bool,
) -> tuple[ValidationEligibility, tuple[ValidationReasonCode, ...]]:
    reasons: list[ValidationReasonCode] = []
    if coverage_interrupted:
        reasons.append(ValidationReasonCode.COVERAGE_CONTINUITY_INTERRUPTED)
    if month_count >= _MIN_PROMOTION_MONTHS:
        return ValidationEligibility.PROMOTION_ELIGIBLE, tuple(reasons)
    if month_count >= _MIN_RESEARCH_MONTHS:
        reasons.append(ValidationReasonCode.PROMOTION_HISTORY_INSUFFICIENT)
        return ValidationEligibility.RESEARCH_ONLY, tuple(reasons)
    reasons.append(ValidationReasonCode.INSUFFICIENT_HISTORY)
    return ValidationEligibility.BLOCKED, tuple(reasons)


@dataclass(frozen=True, slots=True)
class ValidationFoldPlan:
    """One launchable exploration or walk-forward fold."""

    ordinal: int
    role: FoldRole
    train_window: DateWindow | None
    test_window: DateWindow
    purge_sessions: int
    embargo_sessions: int


@dataclass(frozen=True, slots=True)
class ReservedHoldoutPlan:
    """A sealed holdout window pre-registered as an immutable fold by Task 8."""

    train_window: DateWindow
    test_window: DateWindow
    purge_sessions: int
    embargo_sessions: int


def _date_window(
    months: tuple[CalendarMonth, ...],
    session_months: dict[CalendarMonth, tuple[date, ...]],
) -> DateWindow:
    return DateWindow(
        start=session_months[months[0]][0],
        end=session_months[months[-1]][-1],
    )


def _session_count(
    months: tuple[CalendarMonth, ...],
    session_months: dict[CalendarMonth, tuple[date, ...]],
) -> int:
    return sum(len(session_months[month]) for month in months)


def _require_safe_boundary(
    *,
    train_months: tuple[CalendarMonth, ...],
    test_months: tuple[CalendarMonth, ...],
    train_window: DateWindow,
    test_window: DateWindow,
    session_months: dict[CalendarMonth, tuple[date, ...]],
    isolation_width: int,
) -> None:
    if train_window.end >= test_window.start:
        _fail("WINDOW_LEAKAGE", "train_test_windows_overlap")
    train_sessions = _session_count(train_months, session_months)
    if isolation_width >= train_sessions:
        _fail(
            "WINDOW_LEAKAGE",
            "isolation_exhausts_training_window",
            isolation_width_sessions=isolation_width,
            training_session_count=train_sessions,
        )
    if not test_months:
        _fail("WINDOW_LEAKAGE", "empty_test_window")


def _compile_windows(
    *,
    eligible_months: tuple[CalendarMonth, ...],
    session_months: dict[CalendarMonth, tuple[date, ...]],
    isolation_width: int,
) -> tuple[tuple[ValidationFoldPlan, ...], ReservedHoldoutPlan]:
    reserve_start = len(eligible_months) - _VALIDATION_RESERVE_MONTHS
    exploration_months = eligible_months[:reserve_start]
    first_test_months = eligible_months[
        reserve_start : reserve_start + _WALK_FORWARD_MONTHS
    ]
    second_test_months = eligible_months[
        reserve_start + _WALK_FORWARD_MONTHS : reserve_start
        + (2 * _WALK_FORWARD_MONTHS)
    ]
    holdout_months = eligible_months[-_WALK_FORWARD_MONTHS:]

    exploration_window = _date_window(exploration_months, session_months)
    first_test_window = _date_window(first_test_months, session_months)
    first_train_months = exploration_months
    second_train_months = (*exploration_months, *first_test_months)
    second_train_window = _date_window(second_train_months, session_months)
    second_test_window = _date_window(second_test_months, session_months)
    holdout_train_months = (*second_train_months, *second_test_months)
    holdout_train_window = _date_window(holdout_train_months, session_months)
    holdout_window = _date_window(holdout_months, session_months)

    for train_months, test_months, train_window, test_window in (
        (
            first_train_months,
            first_test_months,
            exploration_window,
            first_test_window,
        ),
        (
            second_train_months,
            second_test_months,
            second_train_window,
            second_test_window,
        ),
        (
            holdout_train_months,
            holdout_months,
            holdout_train_window,
            holdout_window,
        ),
    ):
        _require_safe_boundary(
            train_months=train_months,
            test_months=test_months,
            train_window=train_window,
            test_window=test_window,
            session_months=session_months,
            isolation_width=isolation_width,
        )

    folds = (
        ValidationFoldPlan(
            ordinal=1,
            role=FoldRole.EXPLORATION,
            train_window=None,
            test_window=exploration_window,
            purge_sessions=isolation_width,
            embargo_sessions=isolation_width,
        ),
        ValidationFoldPlan(
            ordinal=2,
            role=FoldRole.WALK_FORWARD,
            train_window=exploration_window,
            test_window=first_test_window,
            purge_sessions=isolation_width,
            embargo_sessions=isolation_width,
        ),
        ValidationFoldPlan(
            ordinal=3,
            role=FoldRole.WALK_FORWARD,
            train_window=second_train_window,
            test_window=second_test_window,
            purge_sessions=isolation_width,
            embargo_sessions=isolation_width,
        ),
    )
    return folds, ReservedHoldoutPlan(
        train_window=holdout_train_window,
        test_window=holdout_window,
        purge_sessions=isolation_width,
        embargo_sessions=isolation_width,
    )


classify_history = _classify_history
compile_validation_windows = _compile_windows
