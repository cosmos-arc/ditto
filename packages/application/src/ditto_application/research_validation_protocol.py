"""Neutral pure compiler for the R3 complete-month validation protocol."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import cast

from ditto_application.research_validation_calendar import (
    CalendarMonth,
    TradingCalendarDay,
    TradingCalendarDayStatus,
    TradingCalendarEvidence,
    TradingCalendarMonthClosure,
    TradingCalendarSourceIdentity,
    seal_trading_calendar,
)
from ditto_application.research_validation_calendar import (
    calendar_evidence_payload as _calendar_evidence_payload,
)
from ditto_application.research_validation_calendar import (
    canonical_payload_hash as _payload_hash,
)
from ditto_application.research_validation_calendar import (
    complete_months as _complete_months,
)
from ditto_application.research_validation_calendar import (
    fail_validation as _fail,
)
from ditto_application.research_validation_calendar import (
    sessions_by_month as _sessions_by_month,
)
from ditto_application.research_validation_calendar import (
    validate_calendar_month as _validated_calendar_month,
)
from ditto_application.research_validation_calendar import (
    validate_sessions as _validated_sessions,
)
from ditto_application.research_validation_calendar import (
    validate_trading_calendar as _validated_trading_calendar,
)
from ditto_application.research_validation_eligibility import (
    CoverageEligibility,
    InstrumentEligibilityEvidence,
    IsolationSemantics,
    MonthCoverageDecision,
    PitUniverseMembershipInterval,
    UniverseCoveragePolicy,
    UniverseMembershipSource,
    seal_coverage_decisions,
    seal_coverage_policy,
    seal_instrument_eligibility,
    seal_isolation,
)
from ditto_application.research_validation_eligibility import (
    continuous_eligible_suffix as _continuous_eligible_suffix,
)
from ditto_application.research_validation_eligibility import (
    require_coverage_decisions as _require_coverage_decisions,
)
from ditto_application.research_validation_eligibility import (
    validate_coverage_decisions as _validated_coverage_decisions,
)
from ditto_application.research_validation_eligibility import (
    validate_coverage_policy as _validated_coverage_policy,
)
from ditto_application.research_validation_eligibility import (
    validate_instrument_eligibility as _validated_instrument_eligibility,
)
from ditto_application.research_validation_eligibility import (
    validate_isolation as _validated_isolation,
)
from ditto_application.research_validation_windows import (
    ReservedHoldoutPlan,
    ValidationEligibility,
    ValidationFoldPlan,
    ValidationReasonCode,
)
from ditto_application.research_validation_windows import (
    classify_history as _classify_history,
)
from ditto_application.research_validation_windows import (
    compile_validation_windows as _compile_windows,
)

__all__ = [
    "CalendarMonth",
    "CoverageEligibility",
    "InstrumentEligibilityEvidence",
    "IsolationSemantics",
    "MonthCoverageDecision",
    "PitUniverseMembershipInterval",
    "ReservedHoldoutPlan",
    "TradingCalendarDay",
    "TradingCalendarDayStatus",
    "TradingCalendarEvidence",
    "TradingCalendarMonthClosure",
    "TradingCalendarSourceIdentity",
    "UniverseCoveragePolicy",
    "UniverseMembershipSource",
    "ValidationEligibility",
    "ValidationFoldPlan",
    "ValidationProtocolPlan",
    "ValidationProtocolRequest",
    "ValidationReasonCode",
    "canonical_validation_protocol_hash",
    "canonical_validation_protocol_payload",
    "compile_validation_protocol",
]


@dataclass(frozen=True, slots=True)
class ValidationProtocolRequest:
    """All deterministic inputs required to compile validation windows."""

    trading_sessions: tuple[date, ...]
    strategy_eligible_start: date
    last_complete_month: CalendarMonth
    coverage_policy: UniverseCoveragePolicy
    coverage_decisions: tuple[MonthCoverageDecision, ...]
    isolation: IsolationSemantics
    trading_calendar: TradingCalendarEvidence
    instrument_eligibility: tuple[InstrumentEligibilityEvidence, ...]
    required_input_start: date
    membership_source: UniverseMembershipSource
    planning_decision_date: date


@dataclass(frozen=True, slots=True)
class ValidationProtocolPlan:
    """Compiled governance decision and its deterministic calendar windows."""

    eligibility: ValidationEligibility
    reason_codes: tuple[ValidationReasonCode, ...]
    coverage_policy: UniverseCoveragePolicy
    calendar_complete_month_count: int
    eligible_months: tuple[CalendarMonth, ...]
    isolation_width_sessions: int
    folds: tuple[ValidationFoldPlan, ...]
    reserved_holdout: ReservedHoldoutPlan | None

    @property
    def promotion_eligible(self) -> bool:
        """Return whether later governance may unlock the reserved holdout."""
        return self.eligibility is ValidationEligibility.PROMOTION_ELIGIBLE

    @property
    def launchable(self) -> bool:
        """Return whether Task 8 produced executable non-holdout folds."""
        return self.eligibility is not ValidationEligibility.BLOCKED


def _sealed_date(raw_value: object, *, reason: str) -> date:
    if type(raw_value) is not date:
        _fail("SPEC_INVALID", reason)
    return raw_value


def _sealed_month(raw_value: object, *, reason: str) -> CalendarMonth:
    if type(raw_value) is not CalendarMonth:
        _fail("SPEC_INVALID", reason)
    return CalendarMonth(raw_value.year, raw_value.month)


def _sealed_membership_source(raw_value: object) -> UniverseMembershipSource:
    if type(raw_value) is not UniverseMembershipSource:
        _fail("SPEC_INVALID", "invalid_membership_source_identity")
    return UniverseMembershipSource(
        raw_value.universe_id,
        raw_value.dataset_id,
        raw_value.snapshot_id,
        raw_value.manifest_hash,
    )


def _seal_validation_protocol(raw_request: object) -> ValidationProtocolRequest:
    """Read each untrusted field once and return one exact immutable snapshot."""
    if type(raw_request) is not ValidationProtocolRequest:
        _fail("SPEC_INVALID", "invalid_validation_protocol_request")
    raw_sessions = raw_request.trading_sessions
    raw_start = raw_request.strategy_eligible_start
    raw_last_month = raw_request.last_complete_month
    raw_policy = raw_request.coverage_policy
    raw_decisions = raw_request.coverage_decisions
    raw_isolation = raw_request.isolation
    raw_calendar = raw_request.trading_calendar
    raw_instruments = raw_request.instrument_eligibility
    raw_required_input_start = raw_request.required_input_start
    raw_membership_source = raw_request.membership_source
    raw_planning_decision_date = raw_request.planning_decision_date

    sessions = _validated_sessions(raw_sessions)
    return ValidationProtocolRequest(
        trading_sessions=sessions,
        strategy_eligible_start=_sealed_date(
            raw_start,
            reason="invalid_strategy_eligible_start",
        ),
        last_complete_month=_sealed_month(
            raw_last_month,
            reason="invalid_last_complete_month",
        ),
        coverage_policy=seal_coverage_policy(raw_policy),
        coverage_decisions=seal_coverage_decisions(raw_decisions),
        isolation=seal_isolation(raw_isolation),
        trading_calendar=seal_trading_calendar(raw_calendar),
        instrument_eligibility=seal_instrument_eligibility(
            raw_instruments,
            sessions=sessions,
        ),
        required_input_start=_sealed_date(
            raw_required_input_start,
            reason="invalid_required_input_start",
        ),
        membership_source=_sealed_membership_source(raw_membership_source),
        planning_decision_date=_sealed_date(
            raw_planning_decision_date,
            reason="invalid_planning_decision_date",
        ),
    )


def canonical_validation_protocol_payload(
    request: ValidationProtocolRequest,
) -> Mapping[str, object]:
    """Return the exact, fully validated scalar protocol preimage."""
    sealed = _seal_validation_protocol(request)
    _compile_validation_protocol_snapshot(sealed)
    return _canonical_payload_from_snapshot(sealed)


def _canonical_payload_from_snapshot(
    request: ValidationProtocolRequest,
) -> Mapping[str, object]:
    """Serialize only a graph sealed by ``_seal_validation_protocol``."""
    instruments = request.instrument_eligibility
    calendar = request.trading_calendar
    return {
        "trading_sessions": [
            session.isoformat() for session in request.trading_sessions
        ],
        "trading_calendar": {
            **_calendar_evidence_payload(
                calendar_id=calendar.calendar_id,
                version=calendar.version,
                source=TradingCalendarSourceIdentity(
                    calendar.dataset_id,
                    calendar.snapshot_id,
                    calendar.manifest_hash,
                    calendar.certified_through,
                    calendar.authority_as_of,
                ),
                month_closures=calendar.month_closures,
            ),
            "payload_hash": calendar.payload_hash,
        },
        "instrument_eligibility": [
            {
                "instrument_id": item.instrument_id,
                "listing_date": item.listing_date.isoformat(),
                "base_data_eligible_start": (item.base_data_eligible_start.isoformat()),
                "warmup_sessions": item.warmup_sessions,
                "eligible_from": item.eligible_from.isoformat(),
                "membership_intervals": [
                    {
                        "start_month": str(interval.start_month),
                        "end_month": str(interval.end_month),
                    }
                    for interval in item.membership_intervals
                ],
            }
            for item in instruments
        ],
        "strategy_eligible_start": request.strategy_eligible_start.isoformat(),
        "required_input_start": request.required_input_start.isoformat(),
        "membership_source": {
            "universe_id": request.membership_source.universe_id,
            "dataset_id": request.membership_source.dataset_id,
            "snapshot_id": request.membership_source.snapshot_id,
            "manifest_hash": request.membership_source.manifest_hash,
        },
        "planning_decision_date": request.planning_decision_date.isoformat(),
        "last_complete_month": str(request.last_complete_month),
        "coverage_policy": {
            "policy_id": request.coverage_policy.policy_id,
            "version": request.coverage_policy.version,
            "min_eligible_instrument_count": (
                request.coverage_policy.min_eligible_instrument_count
            ),
            "min_coverage_ratio_bps": (request.coverage_policy.min_coverage_ratio_bps),
            "evaluator_hash": request.coverage_policy.evaluator_hash,
        },
        "coverage_decisions": [
            {
                "month": str(decision.month),
                "eligibility": decision.eligibility.value,
                "universe_instrument_count": decision.universe_instrument_count,
                "universe_instrument_hash": decision.universe_instrument_hash,
                "eligible_instrument_count": decision.eligible_instrument_count,
                "eligible_instrument_hash": decision.eligible_instrument_hash,
            }
            for decision in request.coverage_decisions
        ],
        "isolation": {
            "forward_horizon_sessions": (request.isolation.forward_horizon_sessions),
            "holding_period_sessions": request.isolation.holding_period_sessions,
            "execution_lag_sessions": request.isolation.execution_lag_sessions,
        },
    }


def canonical_validation_protocol_hash(request: ValidationProtocolRequest) -> str:
    """Return SHA-256 over the exact validated protocol preimage."""
    return _payload_hash(canonical_validation_protocol_payload(request))


def compile_validation_protocol(
    request: ValidationProtocolRequest,
) -> ValidationProtocolPlan:
    """Compile complete-month folds without I/O or implicit coverage policy."""
    return _compile_validation_protocol_snapshot(_seal_validation_protocol(request))


def _compile_validation_protocol_snapshot(
    request: ValidationProtocolRequest,
) -> ValidationProtocolPlan:
    """Compile one exact snapshot without rereading the untrusted source graph."""
    sessions = _validated_sessions(request.trading_sessions)
    calendar = _validated_trading_calendar(request.trading_calendar)
    calendar_sessions = tuple(
        session
        for closure in calendar.month_closures
        for session in closure.open_sessions
    )
    if sessions != calendar_sessions:
        _fail("SPEC_INVALID", "trading_sessions_calendar_evidence_mismatch")
    planning_decision_date = _sealed_date(
        request.planning_decision_date,
        reason="invalid_planning_decision_date",
    )
    if calendar.authority_as_of > planning_decision_date:
        _fail(
            "SPEC_INVALID",
            "trading_calendar_authority_after_planning_decision",
            authority_as_of=calendar.authority_as_of.isoformat(),
            planning_decision_date=planning_decision_date.isoformat(),
        )
    start = _validated_date(
        request.strategy_eligible_start,
        reason="invalid_strategy_eligible_start",
    )
    last_complete_month = _validated_calendar_month(
        cast("object", request.last_complete_month),
        reason="invalid_last_complete_month",
    )
    coverage_policy = _validated_coverage_policy(request.coverage_policy)
    isolation_values = _validated_isolation(request.isolation)
    if calendar.month_closures[-1].month != last_complete_month:
        _fail(
            "SPEC_INVALID",
            "last_complete_month_calendar_evidence_mismatch",
        )
    instruments = _validated_instrument_eligibility(
        request.instrument_eligibility,
        sessions=sessions,
    )
    required_input_start = _sealed_date(
        request.required_input_start,
        reason="invalid_required_input_start",
    )
    if any(
        item.base_data_eligible_start != required_input_start for item in instruments
    ):
        _fail(
            "SPEC_INVALID",
            "instrument_base_data_start_not_required_input_start",
            required_input_start=required_input_start.isoformat(),
        )
    calendar_first_month = calendar.month_closures[0].month
    calendar_last_month = calendar.month_closures[-1].month
    for item in instruments:
        for interval in item.membership_intervals:
            if (
                interval.start_month < calendar_first_month
                or interval.end_month > calendar_last_month
            ):
                _fail(
                    "SPEC_INVALID",
                    "pit_membership_interval_outside_calendar_evidence",
                    instrument_id=item.instrument_id,
                )
    derived_start = min(item.eligible_from for item in instruments)
    if start != derived_start:
        _fail(
            "SPEC_INVALID",
            "strategy_eligible_start_not_derived_from_instruments",
            expected=derived_start.isoformat(),
            observed=start.isoformat(),
        )

    session_months = _sessions_by_month(sessions, last_complete_month)
    complete_months = _complete_months(
        session_months=session_months,
        strategy_eligible_start=start,
        last_complete_month=last_complete_month,
    )
    decisions = _validated_coverage_decisions(request.coverage_decisions)
    _require_coverage_decisions(
        complete_months,
        decisions,
        instruments=instruments,
        session_months=session_months,
        policy=coverage_policy,
    )
    eligible_months, coverage_interrupted = _continuous_eligible_suffix(
        complete_months,
        decisions,
    )
    eligibility, reason_codes = _classify_history(
        len(eligible_months),
        coverage_interrupted=coverage_interrupted,
    )
    width = max(isolation_values)
    if eligibility is ValidationEligibility.BLOCKED:
        return ValidationProtocolPlan(
            eligibility=eligibility,
            reason_codes=reason_codes,
            coverage_policy=coverage_policy,
            calendar_complete_month_count=len(complete_months),
            eligible_months=eligible_months,
            isolation_width_sessions=width,
            folds=(),
            reserved_holdout=None,
        )

    folds, holdout = _compile_windows(
        eligible_months=eligible_months,
        session_months=session_months,
        isolation_width=width,
    )
    return ValidationProtocolPlan(
        eligibility=eligibility,
        reason_codes=reason_codes,
        coverage_policy=coverage_policy,
        calendar_complete_month_count=len(complete_months),
        eligible_months=eligible_months,
        isolation_width_sessions=width,
        folds=folds,
        reserved_holdout=holdout,
    )


def _validated_date(raw_value: object, *, reason: str) -> date:
    if type(raw_value) is not date:
        _fail("SPEC_INVALID", reason)
    return raw_value
