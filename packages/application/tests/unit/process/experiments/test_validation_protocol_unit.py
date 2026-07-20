"""Unit tests for the pure R3 calendar-aware validation compiler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta

import pytest
from ditto_analysis.experiments.persistence import FoldRole
from ditto_application.exceptions import AppProcessError
from ditto_application.research_validation_protocol import (
    CalendarMonth,
    CoverageEligibility,
    InstrumentEligibilityEvidence,
    IsolationSemantics,
    MonthCoverageDecision,
    PitUniverseMembershipInterval,
    TradingCalendarEvidence,
    TradingCalendarMonthClosure,
    TradingCalendarSourceIdentity,
    UniverseCoveragePolicy,
    UniverseMembershipSource,
    ValidationEligibility,
    ValidationProtocolRequest,
    ValidationReasonCode,
    compile_validation_protocol,
)


def _next_month(month: CalendarMonth) -> CalendarMonth:
    if month.month == 12:
        return CalendarMonth(month.year + 1, 1)
    return CalendarMonth(month.year, month.month + 1)


def _months(count: int) -> tuple[CalendarMonth, ...]:
    result: list[CalendarMonth] = []
    current = CalendarMonth(2016, 1)
    for _ in range(count):
        result.append(current)
        current = _next_month(current)
    return tuple(result)


def _weekday_sessions(months: tuple[CalendarMonth, ...]) -> tuple[date, ...]:
    sessions: list[date] = []
    for month in months:
        current = date(month.year, month.month, 1)
        following = _next_month(month)
        stop = date(following.year, following.month, 1)
        while current < stop:
            if current.weekday() < 5:
                sessions.append(current)
            current += timedelta(days=1)
    return tuple(sessions)


def _request(
    month_count: int,
    *,
    ineligible_indexes: tuple[int, ...] = (),
    isolation: IsolationSemantics | None = None,
    strategy_eligible_start: date | None = None,
) -> tuple[ValidationProtocolRequest, tuple[CalendarMonth, ...], tuple[date, ...]]:
    months = _months(month_count)
    sessions = _weekday_sessions(months)
    ineligible = set(ineligible_indexes)
    start = strategy_eligible_start or sessions[0]
    warmup_sessions = sessions.index(start)
    membership_intervals: list[PitUniverseMembershipInterval] = []
    run_start: CalendarMonth | None = None
    for index, month in enumerate(months):
        if index not in ineligible and run_start is None:
            run_start = month
        if run_start is not None and (index in ineligible or index == len(months) - 1):
            run_end = months[index - 1] if index in ineligible else month
            membership_intervals.append(
                PitUniverseMembershipInterval(run_start, run_end)
            )
            run_start = None
    instrument = InstrumentEligibilityEvidence(
        instrument_id="000001.SZ",
        listing_date=sessions[0],
        base_data_eligible_start=sessions[0],
        warmup_sessions=warmup_sessions,
        eligible_from=start,
        membership_intervals=tuple(membership_intervals),
    )
    decision_months = (
        months[1:] if start > _month_sessions(sessions, months[0])[0] else months
    )
    closures = tuple(
        TradingCalendarMonthClosure.create(
            month=month,
            open_sessions=_month_sessions(sessions, month),
        )
        for month in months
    )
    certified_through = closures[-1].days[-1].calendar_date
    calendar = TradingCalendarEvidence.create(
        calendar_id="sse-szse-a-share",
        version=1,
        source=TradingCalendarSourceIdentity(
            dataset_id="trade_cal",
            snapshot_id="calendar-provider",
            manifest_hash="c" * 64,
            certified_through=certified_through,
            authority_as_of=certified_through,
        ),
        month_closures=closures,
    )
    request = ValidationProtocolRequest(
        trading_sessions=sessions,
        strategy_eligible_start=start,
        last_complete_month=months[-1],
        coverage_policy=UniverseCoveragePolicy(
            policy_id="a-share-core-coverage",
            version=1,
        ),
        coverage_decisions=tuple(
            MonthCoverageDecision.create(
                month=month,
                eligibility=(
                    CoverageEligibility.INELIGIBLE
                    if months.index(month) in ineligible
                    else CoverageEligibility.ELIGIBLE
                ),
                universe_instrument_ids=(
                    ()
                    if months.index(month) in ineligible
                    else (instrument.instrument_id,)
                ),
                eligible_instrument_ids=(
                    ()
                    if months.index(month) in ineligible
                    else (instrument.instrument_id,)
                ),
            )
            for month in decision_months
        ),
        isolation=isolation
        or IsolationSemantics(
            forward_horizon_sessions=2,
            holding_period_sessions=5,
            execution_lag_sessions=1,
        ),
        trading_calendar=calendar,
        instrument_eligibility=(instrument,),
        required_input_start=sessions[0],
        membership_source=UniverseMembershipSource(
            "test-universe",
            "membership",
            "membership-snapshot",
            "e" * 64,
        ),
        planning_decision_date=calendar.authority_as_of,
    )
    return request, months, sessions


def _month_sessions(
    sessions: tuple[date, ...],
    month: CalendarMonth,
) -> tuple[date, ...]:
    return tuple(
        session
        for session in sessions
        if (session.year, session.month) == (month.year, month.month)
    )


def test_exact_96_months_compile_promotion_protocol_with_inclusive_windows() -> None:
    """The minimum promotion history should compile 60+12+12+12 months."""
    request, months, sessions = _request(96)

    plan = compile_validation_protocol(request)

    assert plan.eligibility is ValidationEligibility.PROMOTION_ELIGIBLE
    assert plan.reason_codes == ()
    assert plan.coverage_policy == request.coverage_policy
    assert plan.eligible_months == months
    assert plan.isolation_width_sessions == 5
    assert tuple(fold.role for fold in plan.folds) == (
        FoldRole.EXPLORATION,
        FoldRole.WALK_FORWARD,
        FoldRole.WALK_FORWARD,
    )
    assert tuple(fold.ordinal for fold in plan.folds) == (1, 2, 3)

    exploration, first_walk_forward, second_walk_forward = plan.folds
    assert exploration.train_window is None
    assert exploration.test_window.start == sessions[0]
    assert exploration.test_window.end == _month_sessions(sessions, months[59])[-1]
    assert first_walk_forward.train_window == exploration.test_window
    assert (
        first_walk_forward.test_window.start == _month_sessions(sessions, months[60])[0]
    )
    assert (
        first_walk_forward.test_window.end == _month_sessions(sessions, months[71])[-1]
    )
    assert second_walk_forward.train_window is not None
    assert second_walk_forward.train_window.start == sessions[0]
    assert second_walk_forward.train_window.end == first_walk_forward.test_window.end
    assert (
        second_walk_forward.test_window.start
        == _month_sessions(sessions, months[72])[0]
    )
    assert (
        second_walk_forward.test_window.end == _month_sessions(sessions, months[83])[-1]
    )
    assert all(
        (fold.purge_sessions, fold.embargo_sessions) == (5, 5) for fold in plan.folds
    )

    holdout = plan.reserved_holdout
    assert holdout is not None
    assert holdout.train_window.start == sessions[0]
    assert holdout.train_window.end == second_walk_forward.test_window.end
    assert holdout.test_window.start == _month_sessions(sessions, months[84])[0]
    assert holdout.test_window.end == sessions[-1]
    assert (holdout.purge_sessions, holdout.embargo_sessions) == (5, 5)


def test_more_than_96_months_extend_exploration_without_truncation() -> None:
    """Every older eligible month should remain in the exploration window."""
    request, months, sessions = _request(104)

    plan = compile_validation_protocol(request)

    exploration = plan.folds[0]
    assert len(plan.eligible_months) == 104
    assert exploration.test_window.start == sessions[0]
    assert exploration.test_window.end == _month_sessions(sessions, months[67])[-1]


def test_pre_calendar_listing_uses_certified_data_start_for_96_month_history() -> None:
    """An old listing may predate evidence when certified data starts in-domain."""
    request, months, _ = _request(96)
    old_listing = replace(
        request.instrument_eligibility[0],
        listing_date=date(2010, 1, 4),
    )

    plan = compile_validation_protocol(
        replace(request, instrument_eligibility=(old_listing,))
    )

    assert plan.eligibility is ValidationEligibility.PROMOTION_ELIGIBLE
    assert plan.eligible_months == months


def test_listing_after_calendar_evidence_is_rejected_explicitly() -> None:
    request, _, _ = _request(96)
    future_month = request.last_complete_month.next()
    future_listing = replace(
        request.instrument_eligibility[0],
        listing_date=date(future_month.year, future_month.month, 1),
        membership_intervals=(
            PitUniverseMembershipInterval(future_month, future_month),
        ),
    )

    with pytest.raises(AppProcessError) as exc_info:
        compile_validation_protocol(
            replace(request, instrument_eligibility=(future_listing,))
        )

    assert exc_info.value.details["reason"] == "listing_date_after_calendar_evidence"


def test_calendar_authority_cannot_be_after_planning_decision_date() -> None:
    request, _, _ = _request(96)
    calendar = request.trading_calendar
    future_calendar = TradingCalendarEvidence.create(
        calendar_id=calendar.calendar_id,
        version=calendar.version,
        source=TradingCalendarSourceIdentity(
            dataset_id=calendar.dataset_id,
            snapshot_id=calendar.snapshot_id,
            manifest_hash=calendar.manifest_hash,
            certified_through=calendar.certified_through,
            authority_as_of=date(2099, 1, 1),
        ),
        month_closures=calendar.month_closures,
    )

    with pytest.raises(AppProcessError) as exc_info:
        compile_validation_protocol(
            replace(
                request,
                trading_calendar=future_calendar,
                planning_decision_date=calendar.authority_as_of,
            )
        )

    assert exc_info.value.details["reason"] == (
        "trading_calendar_authority_after_planning_decision"
    )


@pytest.mark.parametrize("month_count", [37, 95])
def test_37_to_95_months_compile_research_only_protocol(month_count: int) -> None:
    """Research-only work keeps three folds while reserving, not consuming, holdout."""
    request, months, sessions = _request(month_count)

    plan = compile_validation_protocol(request)

    assert plan.eligibility is ValidationEligibility.RESEARCH_ONLY
    assert plan.reason_codes == (ValidationReasonCode.PROMOTION_HISTORY_INSUFFICIENT,)
    assert len(plan.folds) == 3
    assert plan.folds[0].test_window.start == sessions[0]
    assert (
        plan.folds[0].test_window.end
        == _month_sessions(sessions, months[month_count - 37])[-1]
    )
    assert plan.reserved_holdout is not None
    assert (
        plan.reserved_holdout.test_window.start
        == _month_sessions(sessions, months[-12])[0]
    )
    assert plan.reserved_holdout.test_window.end == sessions[-1]


@pytest.mark.parametrize("month_count", [1, 36])
def test_less_than_37_months_block_without_launchable_folds(
    month_count: int,
) -> None:
    """A protocol without exploration plus the 36-month reserve must not launch."""
    request, _, _ = _request(month_count)

    plan = compile_validation_protocol(request)

    assert plan.eligibility is ValidationEligibility.BLOCKED
    assert plan.reason_codes == (ValidationReasonCode.INSUFFICIENT_HISTORY,)
    assert plan.folds == ()
    assert plan.reserved_holdout is None


def test_only_trailing_continuous_coverage_eligible_months_count() -> None:
    """One rejected coverage month should reset the continuous history clock."""
    request, months, _ = _request(100, ineligible_indexes=(50,))

    plan = compile_validation_protocol(request)

    assert plan.eligible_months == months[51:]
    assert plan.eligibility is ValidationEligibility.RESEARCH_ONLY
    assert plan.reason_codes == (
        ValidationReasonCode.COVERAGE_CONTINUITY_INTERRUPTED,
        ValidationReasonCode.PROMOTION_HISTORY_INSUFFICIENT,
    )


def test_partial_warmup_month_is_never_counted_as_complete() -> None:
    """Eligibility beginning after a month's first session must skip that month."""
    months = _months(37)
    sessions = _weekday_sessions(months)
    request, _, _ = _request(
        37,
        strategy_eligible_start=_month_sessions(sessions, months[0])[1],
    )

    plan = compile_validation_protocol(request)

    assert plan.eligible_months == months[1:]
    assert plan.eligibility is ValidationEligibility.BLOCKED
    assert plan.folds == ()


def test_isolation_width_is_the_maximum_registered_time_semantics() -> None:
    """Purge and embargo must use the true experiment-wide maximum in sessions."""
    request, _, _ = _request(
        96,
        isolation=IsolationSemantics(
            forward_horizon_sessions=9,
            holding_period_sessions=4,
            execution_lag_sessions=12,
        ),
    )

    plan = compile_validation_protocol(request)

    assert plan.isolation_width_sessions == 12
    assert all(fold.purge_sessions == 12 for fold in plan.folds)
    assert all(fold.embargo_sessions == 12 for fold in plan.folds)
    assert plan.reserved_holdout is not None
    assert plan.reserved_holdout.purge_sessions == 12
    assert plan.reserved_holdout.embargo_sessions == 12


def test_isolation_that_exhausts_training_fails_closed_as_window_leakage() -> None:
    """A purge wider than exploration must not leave a leak-prone empty train set."""
    request, _, _ = _request(
        37,
        isolation=IsolationSemantics(
            forward_horizon_sessions=500,
            holding_period_sessions=1,
            execution_lag_sessions=1,
        ),
    )

    with pytest.raises(AppProcessError) as exc_info:
        compile_validation_protocol(request)

    assert exc_info.value.details["code"] == "WINDOW_LEAKAGE"
    assert exc_info.value.details["reason"] == "isolation_exhausts_training_window"


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda values: values[::-1], "trading_sessions_not_strictly_increasing"),
        (
            lambda values: (values[0], values[0], *values[1:]),
            "trading_sessions_not_strictly_increasing",
        ),
        (
            lambda values: (datetime(2016, 1, 4), *values[1:]),
            "invalid_trading_session",
        ),
    ],
)
def test_calendar_sessions_must_be_typed_unique_and_stably_ordered(
    mutate: Callable[[tuple[date, ...]], tuple[date, ...]],
    reason: str,
) -> None:
    """The pure compiler must reject ambiguous calendar ordering."""
    request, _, sessions = _request(37)
    changed = mutate(sessions)

    with pytest.raises(AppProcessError) as exc_info:
        compile_validation_protocol(
            ValidationProtocolRequest(
                trading_sessions=changed,
                strategy_eligible_start=request.strategy_eligible_start,
                last_complete_month=request.last_complete_month,
                coverage_policy=request.coverage_policy,
                coverage_decisions=request.coverage_decisions,
                isolation=request.isolation,
                trading_calendar=request.trading_calendar,
                instrument_eligibility=request.instrument_eligibility,
                required_input_start=request.required_input_start,
                membership_source=request.membership_source,
                planning_decision_date=request.planning_decision_date,
            )
        )

    assert exc_info.value.details == {"code": "SPEC_INVALID", "reason": reason}


def test_every_complete_month_requires_explicit_policy_evaluation() -> None:
    """Missing coverage evidence must not silently become a made-up threshold."""
    request, months, _ = _request(37)

    with pytest.raises(AppProcessError) as exc_info:
        compile_validation_protocol(
            ValidationProtocolRequest(
                trading_sessions=request.trading_sessions,
                strategy_eligible_start=request.strategy_eligible_start,
                last_complete_month=request.last_complete_month,
                coverage_policy=request.coverage_policy,
                coverage_decisions=request.coverage_decisions[:-1],
                isolation=request.isolation,
                trading_calendar=request.trading_calendar,
                instrument_eligibility=request.instrument_eligibility,
                required_input_start=request.required_input_start,
                membership_source=request.membership_source,
                planning_decision_date=request.planning_decision_date,
            )
        )

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "coverage_decision_missing",
        "month": str(months[-1]),
    }


def test_missing_calendar_month_fails_closed() -> None:
    """An incomplete calendar input must not turn a gap into contiguous history."""
    request, months, sessions = _request(37)
    missing_month = months[10]

    with pytest.raises(AppProcessError) as exc_info:
        compile_validation_protocol(
            ValidationProtocolRequest(
                trading_sessions=tuple(
                    session
                    for session in sessions
                    if (session.year, session.month)
                    != (missing_month.year, missing_month.month)
                ),
                strategy_eligible_start=request.strategy_eligible_start,
                last_complete_month=request.last_complete_month,
                coverage_policy=request.coverage_policy,
                coverage_decisions=request.coverage_decisions,
                isolation=request.isolation,
                trading_calendar=request.trading_calendar,
                instrument_eligibility=request.instrument_eligibility,
                required_input_start=request.required_input_start,
                membership_source=request.membership_source,
                planning_decision_date=request.planning_decision_date,
            )
        )

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "trading_sessions_calendar_evidence_mismatch",
    }


@pytest.mark.parametrize(
    ("value", "field_name"),
    [
        (
            UniverseCoveragePolicy(policy_id="a-share-core-coverage", version=1),
            "policy_id",
        ),
        (IsolationSemantics(1, 2, 3), "holding_period_sessions"),
        (
            MonthCoverageDecision.create(
                month=CalendarMonth(2026, 1),
                eligibility=CoverageEligibility.ELIGIBLE,
                universe_instrument_ids=("000001.SZ",),
                eligible_instrument_ids=("000001.SZ",),
            ),
            "eligibility",
        ),
    ],
)
def test_protocol_inputs_are_frozen(value: object, field_name: str) -> None:
    """Pre-registered validation inputs must remain immutable after construction."""
    with pytest.raises(FrozenInstanceError):
        setattr(value, field_name, "drift")
