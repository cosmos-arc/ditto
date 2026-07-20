"""Adversarial exact-type tests for the validation protocol graph."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date, timedelta
from typing import cast

import pytest
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
    ValidationProtocolRequest,
    canonical_validation_protocol_hash,
    canonical_validation_protocol_payload,
    compile_validation_protocol,
)


def _month_sessions(month: CalendarMonth) -> tuple[date, ...]:
    current = date(month.year, month.month, 1)
    following = month.next()
    stop = date(following.year, following.month, 1)
    sessions: list[date] = []
    while current < stop:
        if current.weekday() < 5:
            sessions.append(current)
        current += timedelta(days=1)
    return tuple(sessions)


def _calendar(
    months: tuple[CalendarMonth, ...],
) -> tuple[TradingCalendarEvidence, tuple[date, ...]]:
    closures = tuple(
        TradingCalendarMonthClosure.create(
            month=month,
            open_sessions=_month_sessions(month),
        )
        for month in months
    )
    return (
        TradingCalendarEvidence.create(
            calendar_id="sse-szse-a-share",
            version=1,
            source=TradingCalendarSourceIdentity(
                dataset_id="trade_cal",
                snapshot_id="calendar-provider",
                manifest_hash="c" * 64,
                certified_through=closures[-1].days[-1].calendar_date,
                authority_as_of=closures[-1].days[-1].calendar_date,
            ),
            month_closures=closures,
        ),
        tuple(session for closure in closures for session in closure.open_sessions),
    )


def _request() -> ValidationProtocolRequest:
    months = tuple(CalendarMonth(2020, month) for month in range(1, 13)) + tuple(
        CalendarMonth(2021, month) for month in range(1, 13)
    )
    calendar, sessions = _calendar(months)
    instrument = InstrumentEligibilityEvidence(
        instrument_id="000001.SZ",
        listing_date=sessions[0],
        base_data_eligible_start=sessions[0],
        warmup_sessions=0,
        eligible_from=sessions[0],
        membership_intervals=(PitUniverseMembershipInterval(months[0], months[-1]),),
    )
    return ValidationProtocolRequest(
        trading_sessions=sessions,
        strategy_eligible_start=sessions[0],
        last_complete_month=months[-1],
        coverage_policy=UniverseCoveragePolicy("a-share-core", 1),
        coverage_decisions=tuple(
            MonthCoverageDecision.create(
                month=month,
                eligibility=CoverageEligibility.ELIGIBLE,
                universe_instrument_ids=(instrument.instrument_id,),
                eligible_instrument_ids=(instrument.instrument_id,),
            )
            for month in months
        ),
        isolation=IsolationSemantics(2, 5, 1),
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


class _EvilRequest(ValidationProtocolRequest):
    pass


class _EvilTuple(tuple):
    pass


class _EvilStr(str):
    pass


class _EvilDate(date):
    pass


class _EvilMonth(CalendarMonth):
    pass


class _EvilPolicy(UniverseCoveragePolicy):
    pass


class _EvilDecision(MonthCoverageDecision):
    pass


class _EvilIsolation(IsolationSemantics):
    @property
    def width_sessions(self) -> int:
        """Attempt to erase required purge and embargo protection."""
        return 0


class _EvilCalendar(TradingCalendarEvidence):
    pass


class _EvilInstrument(InstrumentEligibilityEvidence):
    pass


def _request_subclass(value: ValidationProtocolRequest) -> ValidationProtocolRequest:
    return _EvilRequest(
        value.trading_sessions,
        value.strategy_eligible_start,
        value.last_complete_month,
        value.coverage_policy,
        value.coverage_decisions,
        value.isolation,
        value.trading_calendar,
        value.instrument_eligibility,
        value.required_input_start,
        value.membership_source,
        value.planning_decision_date,
    )


def _sessions_tuple_subclass(
    value: ValidationProtocolRequest,
) -> ValidationProtocolRequest:
    return replace(
        value,
        trading_sessions=cast("tuple[date, ...]", _EvilTuple(value.trading_sessions)),
    )


def _coverage_tuple_subclass(
    value: ValidationProtocolRequest,
) -> ValidationProtocolRequest:
    return replace(
        value,
        coverage_decisions=cast(
            "tuple[MonthCoverageDecision, ...]",
            _EvilTuple(value.coverage_decisions),
        ),
    )


def _session_date_subclass(
    value: ValidationProtocolRequest,
) -> ValidationProtocolRequest:
    first = value.trading_sessions[0]
    return replace(
        value,
        trading_sessions=(
            cast("date", _EvilDate(first.year, first.month, first.day)),
            *value.trading_sessions[1:],
        ),
    )


def _start_date_subclass(value: ValidationProtocolRequest) -> ValidationProtocolRequest:
    first = value.strategy_eligible_start
    return replace(
        value,
        strategy_eligible_start=cast(
            "date", _EvilDate(first.year, first.month, first.day)
        ),
    )


def _month_subclass(value: ValidationProtocolRequest) -> ValidationProtocolRequest:
    month = value.last_complete_month
    return replace(value, last_complete_month=_EvilMonth(month.year, month.month))


def _policy_subclass(value: ValidationProtocolRequest) -> ValidationProtocolRequest:
    policy = value.coverage_policy
    return replace(value, coverage_policy=_EvilPolicy(policy.policy_id, policy.version))


def _decision_subclass(value: ValidationProtocolRequest) -> ValidationProtocolRequest:
    first = value.coverage_decisions[0]
    return replace(
        value,
        coverage_decisions=(
            _EvilDecision(
                first.month,
                first.eligibility,
                first.universe_instrument_count,
                first.universe_instrument_hash,
                first.eligible_instrument_count,
                first.eligible_instrument_hash,
            ),
            *value.coverage_decisions[1:],
        ),
    )


def _decision_month_subclass(
    value: ValidationProtocolRequest,
) -> ValidationProtocolRequest:
    first = value.coverage_decisions[0]
    return replace(
        value,
        coverage_decisions=(
            MonthCoverageDecision(
                _EvilMonth(first.month.year, first.month.month),
                first.eligibility,
                first.universe_instrument_count,
                first.universe_instrument_hash,
                first.eligible_instrument_count,
                first.eligible_instrument_hash,
            ),
            *value.coverage_decisions[1:],
        ),
    )


def _mutated_eligibility(value: ValidationProtocolRequest) -> ValidationProtocolRequest:
    first = value.coverage_decisions[0]
    object.__setattr__(first, "eligibility", "eligible")
    return value


def _mutated_policy_id(value: ValidationProtocolRequest) -> ValidationProtocolRequest:
    object.__setattr__(value.coverage_policy, "policy_id", _EvilStr("a-share-core"))
    return value


def _mutated_month_number(
    value: ValidationProtocolRequest,
) -> ValidationProtocolRequest:
    object.__setattr__(value.last_complete_month, "month", True)
    return value


def _mutated_isolation_int(
    value: ValidationProtocolRequest,
) -> ValidationProtocolRequest:
    object.__setattr__(value.isolation, "holding_period_sessions", False)
    return value


def _calendar_subclass(
    value: ValidationProtocolRequest,
) -> ValidationProtocolRequest:
    calendar = value.trading_calendar
    return replace(
        value,
        trading_calendar=_EvilCalendar(
            calendar.calendar_id,
            calendar.version,
            calendar.dataset_id,
            calendar.snapshot_id,
            calendar.manifest_hash,
            calendar.certified_through,
            calendar.authority_as_of,
            calendar.month_closures,
            calendar.payload_hash,
        ),
    )


def _instrument_subclass(
    value: ValidationProtocolRequest,
) -> ValidationProtocolRequest:
    item = value.instrument_eligibility[0]
    return replace(
        value,
        instrument_eligibility=(
            _EvilInstrument(
                item.instrument_id,
                item.listing_date,
                item.base_data_eligible_start,
                item.warmup_sessions,
                item.eligible_from,
                item.membership_intervals,
            ),
        ),
    )


@pytest.mark.parametrize(
    "attack",
    [
        _request_subclass,
        _sessions_tuple_subclass,
        _coverage_tuple_subclass,
        _session_date_subclass,
        _start_date_subclass,
        _month_subclass,
        _policy_subclass,
        _decision_subclass,
        _decision_month_subclass,
        _mutated_eligibility,
        _mutated_policy_id,
        _mutated_month_number,
        _mutated_isolation_int,
        _calendar_subclass,
        _instrument_subclass,
    ],
)
def test_protocol_rejects_every_non_exact_graph_node(
    attack: Callable[[ValidationProtocolRequest], ValidationProtocolRequest],
) -> None:
    with pytest.raises(AppProcessError) as exc_info:
        compile_validation_protocol(attack(_request()))

    assert exc_info.value.details["code"] == "SPEC_INVALID"


def test_evil_isolation_cannot_override_width_to_zero_purge() -> None:
    request = _request()
    evil = _EvilIsolation(2, 5, 1)

    with pytest.raises(AppProcessError) as exc_info:
        compile_validation_protocol(replace(request, isolation=evil))

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "invalid_isolation_semantics",
    }


def test_ninety_six_one_session_months_cannot_claim_complete_history() -> None:
    """A self-consistent sparse tuple is not authoritative A-share month closure."""
    with pytest.raises(AppProcessError) as exc_info:
        TradingCalendarMonthClosure.create(
            month=CalendarMonth(2020, 1),
            open_sessions=(date(2020, 1, 2),),
        )

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "a_share_complete_month_open_session_sanity_failed",
        "month": "2020-01",
        "minimum_open_sessions": 10,
        "observed_open_sessions": 1,
    }


def test_scalar_strategy_start_cannot_precede_per_instrument_derivation() -> None:
    request = _request()

    with pytest.raises(AppProcessError) as exc_info:
        compile_validation_protocol(
            replace(request, strategy_eligible_start=date(2019, 12, 31))
        )

    assert exc_info.value.details["reason"] == (
        "strategy_eligible_start_not_derived_from_instruments"
    )


def test_sessions_after_authoritative_last_complete_month_are_rejected() -> None:
    request = _request()

    with pytest.raises(AppProcessError) as exc_info:
        compile_validation_protocol(
            replace(
                request,
                trading_sessions=(*request.trading_sessions, date(2022, 1, 3)),
            )
        )

    assert exc_info.value.details["reason"] == (
        "trading_sessions_calendar_evidence_mismatch"
    )


def test_monthly_membership_hash_tampering_is_recomputed_and_rejected() -> None:
    request = _request()
    first = request.coverage_decisions[0]
    object.__setattr__(first, "universe_instrument_hash", "f" * 64)

    with pytest.raises(AppProcessError) as exc_info:
        compile_validation_protocol(request)

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "coverage_instrument_set_identity_mismatch",
        "month": str(first.month),
    }


def test_pit_membership_intervals_reject_adjacent_noncanonical_ranges() -> None:
    request = _request()
    item = request.instrument_eligibility[0]

    with pytest.raises(AppProcessError) as exc_info:
        replace(
            item,
            membership_intervals=(
                PitUniverseMembershipInterval(
                    CalendarMonth(2020, 1), CalendarMonth(2020, 12)
                ),
                PitUniverseMembershipInterval(
                    CalendarMonth(2021, 1), CalendarMonth(2021, 12)
                ),
            ),
        )

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "adjacent_pit_membership_intervals_not_canonical",
    }


def test_pit_membership_interval_cannot_escape_calendar_evidence() -> None:
    request = _request()
    item = request.instrument_eligibility[0]
    escaped = replace(
        item,
        membership_intervals=(
            PitUniverseMembershipInterval(
                item.membership_intervals[0].start_month,
                CalendarMonth(2022, 1),
            ),
        ),
    )

    with pytest.raises(AppProcessError) as exc_info:
        compile_validation_protocol(replace(request, instrument_eligibility=(escaped,)))

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "pit_membership_interval_outside_calendar_evidence",
        "instrument_id": item.instrument_id,
    }


def test_coverage_decisions_outside_complete_month_domain_are_rejected() -> None:
    request = _request()
    instrument_id = request.instrument_eligibility[0].instrument_id
    extra = MonthCoverageDecision.create(
        month=CalendarMonth(2022, 1),
        eligibility=CoverageEligibility.ELIGIBLE,
        universe_instrument_ids=(instrument_id,),
        eligible_instrument_ids=(instrument_id,),
    )

    with pytest.raises(AppProcessError) as exc_info:
        compile_validation_protocol(
            replace(request, coverage_decisions=(*request.coverage_decisions, extra))
        )

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "coverage_decision_outside_complete_month_domain",
        "month": "2022-01",
    }


@pytest.mark.parametrize("policy_id", ["a-share\ncore", "a-share\x00core", "\ud800"])
def test_coverage_policy_reuses_strict_canonical_unicode_text(
    policy_id: str,
) -> None:
    with pytest.raises(AppProcessError) as exc_info:
        UniverseCoveragePolicy(policy_id, 1)

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "invalid_coverage_policy_id",
    }


def test_normal_chinese_coverage_policy_identity_remains_valid() -> None:
    assert UniverseCoveragePolicy("沪深A股核心池", 1).policy_id == "沪深A股核心池"


class _TupleClassSpoof:
    def __init__(self) -> None:
        self.iterations = 0

    @property
    def __class__(self) -> type[tuple[object, ...]]:
        return tuple

    def __iter__(self) -> object:
        self.iterations += 1
        return iter(())


def test_tuple_class_spoof_is_rejected_without_iteration() -> None:
    request = _request()
    spoof = _TupleClassSpoof()
    object.__setattr__(
        request,
        "trading_sessions",
        cast("tuple[date, ...]", spoof),
    )

    with pytest.raises(AppProcessError) as exc_info:
        canonical_validation_protocol_payload(request)

    assert exc_info.value.details["reason"] == (
        "trading_sessions_must_be_non_empty_tuple"
    )
    assert spoof.iterations == 0


def test_canonical_payload_is_stable_and_sessions_equal_calendar_open_dates() -> None:
    request = _request()

    first = canonical_validation_protocol_payload(request)
    second = canonical_validation_protocol_payload(request)
    expected_sessions = [
        session.isoformat()
        for closure in request.trading_calendar.month_closures
        for session in closure.open_sessions
    ]

    assert first == second
    assert first["trading_sessions"] == expected_sessions
    assert canonical_validation_protocol_hash(request) == (
        canonical_validation_protocol_hash(request)
    )


@pytest.mark.parametrize("field_name", ["certified_through", "authority_as_of"])
def test_calendar_cannot_close_beyond_certified_authority_range(
    field_name: str,
) -> None:
    calendar = _request().trading_calendar
    last_closed_date = calendar.month_closures[-1].days[-1].calendar_date
    changed = {
        "certified_through": last_closed_date,
        "authority_as_of": last_closed_date,
    }
    changed[field_name] = last_closed_date - timedelta(days=1)

    with pytest.raises(AppProcessError) as exc_info:
        TradingCalendarEvidence.create(
            calendar_id=calendar.calendar_id,
            version=calendar.version,
            source=TradingCalendarSourceIdentity(
                dataset_id=calendar.dataset_id,
                snapshot_id=calendar.snapshot_id,
                manifest_hash=calendar.manifest_hash,
                certified_through=changed["certified_through"],
                authority_as_of=changed["authority_as_of"],
            ),
            month_closures=calendar.month_closures,
        )

    assert exc_info.value.details["reason"] == (
        "trading_calendar_exceeds_certified_authority_range"
    )


def test_required_input_start_must_match_every_instrument_data_start() -> None:
    request = _request()
    item = request.instrument_eligibility[0]
    later_start = request.trading_sessions[1]
    changed = replace(
        item,
        base_data_eligible_start=later_start,
        warmup_sessions=0,
        eligible_from=later_start,
    )

    with pytest.raises(AppProcessError) as exc_info:
        compile_validation_protocol(
            replace(
                request,
                strategy_eligible_start=later_start,
                instrument_eligibility=(changed,),
            )
        )

    assert exc_info.value.details["reason"] == (
        "instrument_base_data_start_not_required_input_start"
    )


def test_coverage_policy_recomputes_large_universe_threshold_outcome() -> None:
    request = _request()
    sessions = request.trading_sessions
    interval = request.instrument_eligibility[0].membership_intervals
    instruments = tuple(
        InstrumentEligibilityEvidence(
            instrument_id=f"INSTRUMENT-{index:04d}",
            listing_date=sessions[0],
            base_data_eligible_start=sessions[0],
            warmup_sessions=0 if index == 0 else len(sessions) - 1,
            eligible_from=sessions[0] if index == 0 else sessions[-1],
            membership_intervals=interval,
        )
        for index in range(500)
    )
    universe_ids = tuple(item.instrument_id for item in instruments)
    eligible_ids = (instruments[0].instrument_id,)
    decisions = tuple(
        MonthCoverageDecision.create(
            month=decision.month,
            eligibility=CoverageEligibility.ELIGIBLE,
            universe_instrument_ids=universe_ids,
            eligible_instrument_ids=eligible_ids,
        )
        for decision in request.coverage_decisions
    )

    with pytest.raises(AppProcessError) as exc_info:
        compile_validation_protocol(
            replace(
                request,
                coverage_policy=UniverseCoveragePolicy(
                    "large-universe-minimum",
                    1,
                    min_eligible_instrument_count=2,
                    min_coverage_ratio_bps=1,
                ),
                coverage_decisions=decisions,
                instrument_eligibility=instruments,
            )
        )

    assert exc_info.value.details["reason"] == "coverage_policy_outcome_mismatch"


def test_coverage_policy_payload_binds_evaluator_parameters_and_hash() -> None:
    request = replace(
        _request(),
        coverage_policy=UniverseCoveragePolicy(
            "a-share-core",
            2,
            min_eligible_instrument_count=1,
            min_coverage_ratio_bps=5_000,
        ),
    )

    payload = canonical_validation_protocol_payload(request)

    assert payload["coverage_policy"] == {
        "policy_id": "a-share-core",
        "version": 2,
        "min_eligible_instrument_count": 1,
        "min_coverage_ratio_bps": 5_000,
        "evaluator_hash": request.coverage_policy.evaluator_hash,
    }


def _spaced_membership_intervals(
    count: int,
) -> tuple[PitUniverseMembershipInterval, ...]:
    intervals: list[PitUniverseMembershipInterval] = []
    month = CalendarMonth(2020, 1)
    for _ in range(count):
        intervals.append(PitUniverseMembershipInterval(month, month))
        month = month.next().next()
    return tuple(intervals)


def test_sixteen_membership_intervals_are_within_the_canonical_bound() -> None:
    request = _request()
    item = request.instrument_eligibility[0]

    evidence = replace(
        item,
        membership_intervals=_spaced_membership_intervals(16),
    )

    assert len(evidence.membership_intervals) == 16


def test_seventeen_membership_intervals_fail_with_remediation() -> None:
    item = _request().instrument_eligibility[0]

    with pytest.raises(AppProcessError) as exc_info:
        replace(item, membership_intervals=_spaced_membership_intervals(17))

    assert exc_info.value.details["reason"] == "MEMBERSHIP_EVIDENCE_TOO_LARGE"
    assert "remediation" in exc_info.value.details


def test_total_membership_evidence_bound_fails_before_canonical_hashing() -> None:
    request = _request()
    item = request.instrument_eligibility[0]
    intervals = _spaced_membership_intervals(16)
    instruments = tuple(
        replace(
            item,
            instrument_id=f"INSTRUMENT-{index:04d}",
            membership_intervals=intervals,
        )
        for index in range(513)
    )

    with pytest.raises(AppProcessError) as exc_info:
        canonical_validation_protocol_hash(
            replace(request, instrument_eligibility=instruments)
        )

    assert exc_info.value.details["reason"] == "MEMBERSHIP_EVIDENCE_TOO_LARGE"
    assert "remediation" in exc_info.value.details


def test_midmonth_listing_cannot_claim_membership_in_partial_month() -> None:
    request = _request()
    item = request.instrument_eligibility[0]
    listing_date = request.trading_sessions[1]
    changed = replace(
        item,
        listing_date=listing_date,
        base_data_eligible_start=listing_date,
        warmup_sessions=0,
        eligible_from=listing_date,
    )

    with pytest.raises(AppProcessError) as exc_info:
        compile_validation_protocol(
            replace(
                request,
                strategy_eligible_start=listing_date,
                instrument_eligibility=(changed,),
                required_input_start=listing_date,
            )
        )

    assert exc_info.value.details["reason"] == (
        "pit_membership_starts_in_partial_listing_month"
    )


def test_midmonth_listing_may_begin_membership_next_complete_month() -> None:
    request = _request()
    item = request.instrument_eligibility[0]
    listing_date = request.trading_sessions[1]
    first_membership = item.membership_intervals[0]
    changed = replace(
        item,
        listing_date=listing_date,
        base_data_eligible_start=listing_date,
        warmup_sessions=0,
        eligible_from=listing_date,
        membership_intervals=(
            PitUniverseMembershipInterval(
                first_membership.start_month.next(),
                first_membership.end_month,
            ),
        ),
    )

    plan = compile_validation_protocol(
        replace(
            request,
            strategy_eligible_start=listing_date,
            coverage_decisions=request.coverage_decisions[1:],
            instrument_eligibility=(changed,),
            required_input_start=listing_date,
        )
    )

    assert plan.calendar_complete_month_count == 23


def test_decomposed_unicode_identity_is_rejected_but_nfc_is_accepted() -> None:
    with pytest.raises(AppProcessError):
        UniverseCoveragePolicy("Cafe\u0301", 1)

    assert UniverseCoveragePolicy("Caf\u00e9", 1).policy_id == "Caf\u00e9"
