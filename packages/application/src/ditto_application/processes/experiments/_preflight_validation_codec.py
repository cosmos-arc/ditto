"""Strict scalar codec for the persisted validation-protocol preimage."""

from __future__ import annotations

from datetime import date
from typing import cast

import orjson

from ditto_application.processes.experiments._process_error import (
    experiment_process_error,
)
from ditto_application.research_validation_protocol import (
    CalendarMonth,
    CoverageEligibility,
    InstrumentEligibilityEvidence,
    IsolationSemantics,
    MonthCoverageDecision,
    PitUniverseMembershipInterval,
    TradingCalendarDay,
    TradingCalendarDayStatus,
    TradingCalendarEvidence,
    TradingCalendarMonthClosure,
    UniverseCoveragePolicy,
    UniverseMembershipSource,
    ValidationProtocolRequest,
    canonical_validation_protocol_payload,
)

__all__ = ["decode_validation_protocol"]

_CALENDAR_MONTH_PART_COUNT = 2


def _mapping(value: object, field_name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise experiment_process_error(f"{field_name} must be an object")
    return cast("dict[str, object]", value)


def _list(value: object, field_name: str) -> list[object]:
    if type(value) is not list:
        raise experiment_process_error(f"{field_name} must be a list")
    return cast("list[object]", value)


def _string(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise experiment_process_error(f"{field_name} must be a string")
    return value


def _integer(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise experiment_process_error(f"{field_name} must be an integer")
    return value


def _date(value: object, field_name: str) -> date:
    text = _string(value, field_name)
    parsed = date.fromisoformat(text)
    if parsed.isoformat() != text:
        raise experiment_process_error(f"{field_name} is not a canonical date")
    return parsed


def _month(value: object, field_name: str) -> CalendarMonth:
    text = _string(value, field_name)
    parts = text.split("-")
    if len(parts) != _CALENDAR_MONTH_PART_COUNT:
        raise experiment_process_error(f"{field_name} is not a calendar month")
    month = CalendarMonth(int(parts[0]), int(parts[1]))
    if str(month) != text:
        raise experiment_process_error(
            f"{field_name} is not a canonical calendar month"
        )
    return month


def _calendar_day(value: object) -> TradingCalendarDay:
    payload = _mapping(value, "validation.protocol.trading_calendar.day")
    return TradingCalendarDay(
        calendar_date=_date(
            payload.get("date"),
            "validation.protocol.trading_calendar.day.date",
        ),
        status=TradingCalendarDayStatus(
            _string(
                payload.get("status"),
                "validation.protocol.trading_calendar.day.status",
            )
        ),
    )


def _month_closure(value: object) -> TradingCalendarMonthClosure:
    payload = _mapping(value, "validation.protocol.trading_calendar.month_closure")
    return TradingCalendarMonthClosure(
        month=_month(
            payload.get("month"),
            "validation.protocol.trading_calendar.month_closure.month",
        ),
        days=tuple(
            _calendar_day(item)
            for item in _list(
                payload.get("days"),
                "validation.protocol.trading_calendar.month_closure.days",
            )
        ),
        content_hash=_string(
            payload.get("content_hash"),
            "validation.protocol.trading_calendar.month_closure.content_hash",
        ),
    )


def _trading_calendar(value: object) -> TradingCalendarEvidence:
    payload = _mapping(value, "validation.protocol.trading_calendar")
    source = _mapping(
        payload.get("source"),
        "validation.protocol.trading_calendar.source",
    )
    return TradingCalendarEvidence(
        calendar_id=_string(
            payload.get("calendar_id"),
            "validation.protocol.trading_calendar.calendar_id",
        ),
        version=_integer(
            payload.get("version"),
            "validation.protocol.trading_calendar.version",
        ),
        dataset_id=_string(
            source.get("dataset_id"),
            "validation.protocol.trading_calendar.source.dataset_id",
        ),
        snapshot_id=_string(
            source.get("snapshot_id"),
            "validation.protocol.trading_calendar.source.snapshot_id",
        ),
        manifest_hash=_string(
            source.get("manifest_hash"),
            "validation.protocol.trading_calendar.source.manifest_hash",
        ),
        certified_through=_date(
            source.get("certified_through"),
            "validation.protocol.trading_calendar.source.certified_through",
        ),
        authority_as_of=_date(
            source.get("authority_as_of"),
            "validation.protocol.trading_calendar.source.authority_as_of",
        ),
        month_closures=tuple(
            _month_closure(item)
            for item in _list(
                payload.get("month_closures"),
                "validation.protocol.trading_calendar.month_closures",
            )
        ),
        payload_hash=_string(
            payload.get("payload_hash"),
            "validation.protocol.trading_calendar.payload_hash",
        ),
    )


def _membership_interval(value: object) -> PitUniverseMembershipInterval:
    payload = _mapping(value, "validation.protocol.membership_interval")
    return PitUniverseMembershipInterval(
        start_month=_month(
            payload.get("start_month"),
            "validation.protocol.membership_interval.start_month",
        ),
        end_month=_month(
            payload.get("end_month"),
            "validation.protocol.membership_interval.end_month",
        ),
    )


def _instrument(value: object) -> InstrumentEligibilityEvidence:
    payload = _mapping(value, "validation.protocol.instrument_eligibility")
    return InstrumentEligibilityEvidence(
        instrument_id=_string(
            payload.get("instrument_id"),
            "validation.protocol.instrument_eligibility.instrument_id",
        ),
        listing_date=_date(
            payload.get("listing_date"),
            "validation.protocol.instrument_eligibility.listing_date",
        ),
        base_data_eligible_start=_date(
            payload.get("base_data_eligible_start"),
            "validation.protocol.instrument_eligibility.base_data_eligible_start",
        ),
        warmup_sessions=_integer(
            payload.get("warmup_sessions"),
            "validation.protocol.instrument_eligibility.warmup_sessions",
        ),
        eligible_from=_date(
            payload.get("eligible_from"),
            "validation.protocol.instrument_eligibility.eligible_from",
        ),
        membership_intervals=tuple(
            _membership_interval(item)
            for item in _list(
                payload.get("membership_intervals"),
                "validation.protocol.instrument_eligibility.membership_intervals",
            )
        ),
    )


def _coverage_decision(value: object) -> MonthCoverageDecision:
    payload = _mapping(value, "validation.protocol.coverage_decision")
    return MonthCoverageDecision(
        month=_month(
            payload.get("month"),
            "validation.protocol.coverage_decision.month",
        ),
        eligibility=CoverageEligibility(
            _string(
                payload.get("eligibility"),
                "validation.protocol.coverage_decision.eligibility",
            )
        ),
        universe_instrument_count=_integer(
            payload.get("universe_instrument_count"),
            "validation.protocol.coverage_decision.universe_instrument_count",
        ),
        universe_instrument_hash=_string(
            payload.get("universe_instrument_hash"),
            "validation.protocol.coverage_decision.universe_instrument_hash",
        ),
        eligible_instrument_count=_integer(
            payload.get("eligible_instrument_count"),
            "validation.protocol.coverage_decision.eligible_instrument_count",
        ),
        eligible_instrument_hash=_string(
            payload.get("eligible_instrument_hash"),
            "validation.protocol.coverage_decision.eligible_instrument_hash",
        ),
    )


def decode_validation_protocol(value: object) -> ValidationProtocolRequest:
    """Reconstruct and validate the exact canonical protocol payload."""
    payload = _mapping(value, "validation.protocol")
    isolation = _mapping(payload.get("isolation"), "validation.protocol.isolation")
    coverage_policy = _mapping(
        payload.get("coverage_policy"),
        "validation.protocol.coverage_policy",
    )
    membership_source = _mapping(
        payload.get("membership_source"),
        "validation.protocol.membership_source",
    )
    request = ValidationProtocolRequest(
        trading_sessions=tuple(
            _date(item, "validation.protocol.trading_session")
            for item in _list(
                payload.get("trading_sessions"),
                "validation.protocol.trading_sessions",
            )
        ),
        strategy_eligible_start=_date(
            payload.get("strategy_eligible_start"),
            "validation.protocol.strategy_eligible_start",
        ),
        last_complete_month=_month(
            payload.get("last_complete_month"),
            "validation.protocol.last_complete_month",
        ),
        coverage_policy=UniverseCoveragePolicy(
            _string(
                coverage_policy.get("policy_id"),
                "validation.protocol.coverage_policy.policy_id",
            ),
            _integer(
                coverage_policy.get("version"),
                "validation.protocol.coverage_policy.version",
            ),
            _integer(
                coverage_policy.get("min_eligible_instrument_count"),
                "validation.protocol.coverage_policy.min_eligible_instrument_count",
            ),
            _integer(
                coverage_policy.get("min_coverage_ratio_bps"),
                "validation.protocol.coverage_policy.min_coverage_ratio_bps",
            ),
            _string(
                coverage_policy.get("evaluator_hash"),
                "validation.protocol.coverage_policy.evaluator_hash",
            ),
        ),
        coverage_decisions=tuple(
            _coverage_decision(item)
            for item in _list(
                payload.get("coverage_decisions"),
                "validation.protocol.coverage_decisions",
            )
        ),
        isolation=IsolationSemantics(
            _integer(
                isolation.get("forward_horizon_sessions"),
                "validation.protocol.isolation.forward_horizon_sessions",
            ),
            _integer(
                isolation.get("holding_period_sessions"),
                "validation.protocol.isolation.holding_period_sessions",
            ),
            _integer(
                isolation.get("execution_lag_sessions"),
                "validation.protocol.isolation.execution_lag_sessions",
            ),
        ),
        trading_calendar=_trading_calendar(payload.get("trading_calendar")),
        instrument_eligibility=tuple(
            _instrument(item)
            for item in _list(
                payload.get("instrument_eligibility"),
                "validation.protocol.instrument_eligibility",
            )
        ),
        required_input_start=_date(
            payload.get("required_input_start"),
            "validation.protocol.required_input_start",
        ),
        membership_source=UniverseMembershipSource(
            universe_id=_string(
                membership_source.get("universe_id"),
                "validation.protocol.membership_source.universe_id",
            ),
            dataset_id=_string(
                membership_source.get("dataset_id"),
                "validation.protocol.membership_source.dataset_id",
            ),
            snapshot_id=_string(
                membership_source.get("snapshot_id"),
                "validation.protocol.membership_source.snapshot_id",
            ),
            manifest_hash=_string(
                membership_source.get("manifest_hash"),
                "validation.protocol.membership_source.manifest_hash",
            ),
        ),
        planning_decision_date=_date(
            payload.get("planning_decision_date"),
            "validation.protocol.planning_decision_date",
        ),
    )
    canonical = canonical_validation_protocol_payload(request)
    if orjson.dumps(payload, option=orjson.OPT_SORT_KEYS) != orjson.dumps(
        canonical,
        option=orjson.OPT_SORT_KEYS,
    ):
        raise experiment_process_error(
            "validation.protocol is not the canonical protocol payload"
        )
    return request
