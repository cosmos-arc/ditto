"""Adversarial tests for the untrusted validation-authority boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date, timedelta
from typing import cast

import pytest
from ditto_application.processes.experiments import _validation_authority
from ditto_application.processes.experiments._validation_authority import (
    assess_validation_authority,
)
from ditto_application.research_certification_contracts import (
    ExperimentSnapshotIdentity,
    ResearchDatasetRequirement,
)
from ditto_application.research_validation_contracts import (
    ResearchValidationAuthorityEvidence,
    ResearchValidationAuthorityRequest,
    ResearchValidationAuthorityResult,
    RuntimeValidationEvidence,
)
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
)


def _next_month(month: CalendarMonth) -> CalendarMonth:
    return month.next()


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


def _month_sessions(
    sessions: tuple[date, ...], month: CalendarMonth
) -> tuple[date, ...]:
    return tuple(
        session
        for session in sessions
        if (session.year, session.month) == (month.year, month.month)
    )


def _calendar(
    months: tuple[CalendarMonth, ...], sessions: tuple[date, ...]
) -> TradingCalendarEvidence:
    closures = tuple(
        TradingCalendarMonthClosure.create(
            month=month,
            open_sessions=_month_sessions(sessions, month),
        )
        for month in months
    )
    return TradingCalendarEvidence.create(
        calendar_id="sse-szse-a-share",
        version=1,
        source=TradingCalendarSourceIdentity(
            dataset_id="trade_cal",
            snapshot_id="calendar-provider",
            manifest_hash="d" * 64,
            certified_through=closures[-1].days[-1].calendar_date,
            authority_as_of=closures[-1].days[-1].calendar_date,
        ),
        month_closures=closures,
    )


def _protocol(
    *, isolation: IsolationSemantics | None = None
) -> ValidationProtocolRequest:
    months = (CalendarMonth(2026, 1), CalendarMonth(2026, 2))
    sessions = _weekday_sessions(months)
    instrument = InstrumentEligibilityEvidence(
        instrument_id="510300.SH",
        listing_date=sessions[0],
        base_data_eligible_start=sessions[0],
        warmup_sessions=21,
        eligible_from=sessions[21],
        membership_intervals=(PitUniverseMembershipInterval(months[0], months[-1]),),
    )
    return ValidationProtocolRequest(
        trading_sessions=sessions,
        strategy_eligible_start=instrument.eligible_from,
        last_complete_month=months[-1],
        coverage_policy=UniverseCoveragePolicy("a-share-core", 1),
        coverage_decisions=(
            MonthCoverageDecision.create(
                month=CalendarMonth(2026, 2),
                eligibility=CoverageEligibility.ELIGIBLE,
                universe_instrument_ids=(instrument.instrument_id,),
                eligible_instrument_ids=(instrument.instrument_id,),
            ),
        ),
        isolation=isolation or IsolationSemantics(2, 5, 1),
        trading_calendar=_calendar(months, sessions),
        instrument_eligibility=(instrument,),
        required_input_start=sessions[0],
        membership_source=UniverseMembershipSource(
            "csi_etf_broad",
            "etf_daily",
            "etf-provider",
            "d" * 64,
        ),
        planning_decision_date=_calendar(months, sessions).authority_as_of,
    )


def _runtime() -> RuntimeValidationEvidence:
    return RuntimeValidationEvidence(
        lane="etf_rotation",
        universe_id="csi_etf_broad",
        required_datasets=("etf_daily", "trade_cal"),
        max_lookback_sessions=21,
        requires_pit_universe=True,
        forward_horizon_sessions=2,
        holding_period_sessions=5,
        execution_lag_sessions=1,
    )


def _requirements() -> tuple[ResearchDatasetRequirement, ...]:
    return (
        ResearchDatasetRequirement(
            "etf_daily", ("etf-provider",), True, date(2026, 1, 1)
        ),
        ResearchDatasetRequirement(
            "trade_cal", ("calendar-provider",), False, date(2026, 1, 1)
        ),
    )


def _request(
    runtime: RuntimeValidationEvidence | None = None,
) -> ResearchValidationAuthorityRequest:
    return ResearchValidationAuthorityRequest(
        snapshot_identity=ExperimentSnapshotIdentity("snapshot-1", "d" * 64),
        runtime_validation=runtime or _runtime(),
        declared_protocol=_protocol(),
        declared_requirements=_requirements(),
    )


def _evidence(
    request: ResearchValidationAuthorityRequest,
    *,
    protocol: ValidationProtocolRequest | None = None,
    bindings: tuple[ResearchDatasetRequirement, ...] | None = None,
) -> ResearchValidationAuthorityEvidence:
    runtime = request.runtime_validation
    assert type(runtime) is RuntimeValidationEvidence
    return ResearchValidationAuthorityEvidence.create(
        protocol=protocol or request.declared_protocol,
        snapshot_identity=request.snapshot_identity,
        runtime_evidence_hash=runtime.payload_hash,
        universe_membership_hash="e" * 64,
        requires_pit_universe=runtime.requires_pit_universe,
        dataset_bindings=bindings or request.declared_requirements,
    )


class _ReadyProbe:
    def __init__(self, evidence: ResearchValidationAuthorityEvidence) -> None:
        self._evidence = evidence
        self.calls = 0

    def probe(
        self, request: ResearchValidationAuthorityRequest
    ) -> ResearchValidationAuthorityResult:
        self.calls += 1
        return ResearchValidationAuthorityResult(
            True,
            None,
            None,
            None,
            self._evidence,
        )


class _EvilDate(date):
    pass


class _EvilTuple(tuple):
    pass


class _EvilStr(str):
    pass


def _evil_declared_start(
    request: ResearchValidationAuthorityRequest,
) -> ResearchValidationAuthorityRequest:
    start = request.declared_protocol.strategy_eligible_start
    return replace(
        request,
        declared_protocol=replace(
            request.declared_protocol,
            strategy_eligible_start=_EvilDate(start.year, start.month, start.day),
        ),
    )


def _evil_declared_sessions(
    request: ResearchValidationAuthorityRequest,
) -> ResearchValidationAuthorityRequest:
    return replace(
        request,
        declared_protocol=replace(
            request.declared_protocol,
            trading_sessions=cast(
                "tuple[date, ...]",
                _EvilTuple(request.declared_protocol.trading_sessions),
            ),
        ),
    )


def _evil_declared_policy(
    request: ResearchValidationAuthorityRequest,
) -> ResearchValidationAuthorityRequest:
    object.__setattr__(
        request.declared_protocol.coverage_policy,
        "policy_id",
        _EvilStr("a-share-core"),
    )
    return request


def _evil_declared_month(
    request: ResearchValidationAuthorityRequest,
) -> ResearchValidationAuthorityRequest:
    object.__setattr__(request.declared_protocol.last_complete_month, "month", True)
    return request


def _evil_declared_eligibility(
    request: ResearchValidationAuthorityRequest,
) -> ResearchValidationAuthorityRequest:
    object.__setattr__(
        request.declared_protocol.coverage_decisions[0],
        "eligibility",
        "eligible",
    )
    return request


def _evil_declared_isolation(
    request: ResearchValidationAuthorityRequest,
) -> ResearchValidationAuthorityRequest:
    object.__setattr__(
        request.declared_protocol.isolation,
        "execution_lag_sessions",
        True,
    )
    return request


@pytest.mark.parametrize(
    "attack",
    [
        _evil_declared_start,
        _evil_declared_sessions,
        _evil_declared_policy,
        _evil_declared_month,
        _evil_declared_eligibility,
        _evil_declared_isolation,
    ],
)
def test_invalid_declared_protocol_graph_blocks_before_authority_probe(
    attack: Callable[
        [ResearchValidationAuthorityRequest], ResearchValidationAuthorityRequest
    ],
) -> None:
    request = _request()
    legal_authority_request = replace(request, declared_protocol=_protocol())
    probe = _ReadyProbe(_evidence(legal_authority_request))

    assessment = assess_validation_authority(probe, attack(request))

    assert assessment.check.code == "VALIDATION_AUTHORITY_INVALID"
    assert assessment.evidence is None
    assert assessment.validation is None
    assert probe.calls == 0


def test_protocol_comparison_uses_canonical_hash_not_dataclass_equality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    authority_protocol = replace(
        _protocol(),
        coverage_policy=UniverseCoveragePolicy("a-share-core", 2),
    )
    probe = _ReadyProbe(_evidence(request, protocol=authority_protocol))
    monkeypatch.setattr(
        ValidationProtocolRequest,
        "__eq__",
        lambda _self, _other: True,
    )

    assessment = assess_validation_authority(probe, request)

    assert assessment.check.code == "VALIDATION_AUTHORITY_MISMATCH"
    assert assessment.evidence is None
    assert assessment.validation is None


def test_probe_cannot_mutate_request_to_another_matching_legal_identity() -> None:
    request = _request()

    class _MutatingProbe:
        calls = 0

        def probe(
            self,
            mutable_request: ResearchValidationAuthorityRequest,
        ) -> ResearchValidationAuthorityResult:
            self.calls += 1
            protocol = replace(
                _protocol(),
                coverage_policy=UniverseCoveragePolicy("a-share-mutated", 2),
                isolation=IsolationSemantics(3, 4, 2),
            )
            runtime = RuntimeValidationEvidence(
                lane="stock_selection",
                universe_id="csi300",
                required_datasets=("stock_daily",),
                max_lookback_sessions=63,
                requires_pit_universe=True,
                forward_horizon_sessions=3,
                holding_period_sessions=4,
                execution_lag_sessions=2,
            )
            requirements = (
                ResearchDatasetRequirement(
                    "stock_daily",
                    ("stock-provider",),
                    True,
                    date(2026, 1, 1),
                ),
            )
            snapshot = ExperimentSnapshotIdentity("snapshot-mutated", "f" * 64)
            object.__setattr__(mutable_request, "snapshot_identity", snapshot)
            object.__setattr__(mutable_request, "runtime_validation", runtime)
            object.__setattr__(
                mutable_request,
                "declared_requirements",
                requirements,
            )
            object.__setattr__(mutable_request, "declared_protocol", protocol)
            evidence = ResearchValidationAuthorityEvidence.create(
                protocol=protocol,
                snapshot_identity=snapshot,
                runtime_evidence_hash=runtime.payload_hash,
                universe_membership_hash="9" * 64,
                requires_pit_universe=True,
                dataset_bindings=requirements,
            )
            return ResearchValidationAuthorityResult(
                True,
                None,
                None,
                None,
                evidence,
            )

    probe = _MutatingProbe()

    assessment = assess_validation_authority(probe, request)

    assert assessment.check.code == "VALIDATION_AUTHORITY_INVALID"
    assert assessment.evidence is None
    assert assessment.validation is None
    assert probe.calls == 1


def test_authority_factory_rejects_legacy_flattened_binding_arguments() -> None:
    request = _request()
    runtime = request.runtime_validation
    assert type(runtime) is RuntimeValidationEvidence

    with pytest.raises(TypeError):
        ResearchValidationAuthorityEvidence.create(
            protocol=request.declared_protocol,
            snapshot_identity=request.snapshot_identity,
            runtime_evidence_hash=runtime.payload_hash,
            universe_membership_hash="e" * 64,
            requires_pit_universe=True,
            dataset_ids=("etf_daily", "trade_cal"),  # type: ignore[call-arg]
            snapshot_ids=("calendar-provider", "etf-provider"),  # type: ignore[call-arg]
        )


def test_runtime_subclass_is_not_accepted_as_authoritative_evidence() -> None:
    class _RuntimeSubclass(RuntimeValidationEvidence):
        pass

    base = _runtime()
    runtime = _RuntimeSubclass(
        lane=base.lane,
        universe_id=base.universe_id,
        required_datasets=base.required_datasets,
        max_lookback_sessions=base.max_lookback_sessions,
        requires_pit_universe=base.requires_pit_universe,
        forward_horizon_sessions=base.forward_horizon_sessions,
        holding_period_sessions=base.holding_period_sessions,
        execution_lag_sessions=base.execution_lag_sessions,
    )
    request = _request(runtime)
    evidence = ResearchValidationAuthorityEvidence.create(
        protocol=request.declared_protocol,
        snapshot_identity=request.snapshot_identity,
        runtime_evidence_hash=runtime.payload_hash,
        universe_membership_hash="e" * 64,
        requires_pit_universe=True,
        dataset_bindings=request.declared_requirements,
    )

    assessment = assess_validation_authority(_ReadyProbe(evidence), request)

    assert assessment.check.code == "VALIDATION_AUTHORITY_INVALID"
    assert assessment.evidence is None
    assert assessment.validation is None


def test_registered_isolation_requires_all_three_exact_non_negative_ints() -> None:
    runtime = _runtime()
    object.__setattr__(runtime, "holding_period_sessions", None)

    assert runtime.has_registered_isolation is False


def test_runtime_isolation_must_exactly_match_authority_protocol() -> None:
    request = _request()
    evidence = _evidence(
        request,
        protocol=replace(
            request.declared_protocol,
            isolation=IsolationSemantics(5, 2, 1),
        ),
    )
    request = replace(request, declared_protocol=evidence.protocol)

    assessment = assess_validation_authority(_ReadyProbe(evidence), request)

    assert assessment.check.code == "VALIDATION_AUTHORITY_MISMATCH"
    assert assessment.evidence is None
    assert assessment.validation is None


def test_runtime_max_lookback_must_match_every_instrument_warmup() -> None:
    runtime = replace(_runtime(), max_lookback_sessions=20)
    request = _request(runtime)
    evidence = _evidence(request)

    assessment = assess_validation_authority(_ReadyProbe(evidence), request)

    assert assessment.check.code == "VALIDATION_AUTHORITY_MISMATCH"
    assert assessment.evidence is None
    assert assessment.validation is None


def test_per_dataset_snapshot_binding_swap_cannot_hide_behind_flat_sets() -> None:
    request = _request()
    swapped = (
        ResearchDatasetRequirement(
            "etf_daily", ("calendar-provider",), True, date(2026, 1, 1)
        ),
        ResearchDatasetRequirement(
            "trade_cal", ("etf-provider",), False, date(2026, 1, 1)
        ),
    )
    evidence = _evidence(request, bindings=swapped)

    assessment = assess_validation_authority(_ReadyProbe(evidence), request)

    assert assessment.check.code == "VALIDATION_AUTHORITY_MISMATCH"


def test_authority_exposes_only_lossless_dataset_bindings() -> None:
    evidence = _evidence(_request())

    assert not hasattr(evidence, "dataset_ids")
    assert not hasattr(evidence, "snapshot_ids")
    assert tuple(binding.dataset_id for binding in evidence.dataset_bindings) == (
        "etf_daily",
        "trade_cal",
    )


def test_per_dataset_pit_binding_is_hashed_and_compared_exactly() -> None:
    request = _request()
    changed_pit = (
        ResearchDatasetRequirement(
            "etf_daily", ("etf-provider",), False, date(2026, 1, 1)
        ),
        ResearchDatasetRequirement(
            "trade_cal", ("calendar-provider",), True, date(2026, 1, 1)
        ),
    )
    expected = _evidence(request)
    drifted = _evidence(request, bindings=changed_pit)

    assessment = assess_validation_authority(_ReadyProbe(drifted), request)

    assert expected.payload_hash != drifted.payload_hash
    assert assessment.check.code == "VALIDATION_AUTHORITY_MISMATCH"


def test_membership_projection_is_cross_bound_to_source_artifact_hash() -> None:
    request = _request()
    evidence = _evidence(request)
    original_projection_hash = evidence.membership_projection_hash
    object.__setattr__(evidence, "universe_membership_hash", "a" * 64)

    assessment = assess_validation_authority(_ReadyProbe(evidence), request)

    assert evidence.membership_projection_hash == original_projection_hash
    assert assessment.check.code == "VALIDATION_AUTHORITY_INVALID"
    assert assessment.evidence is None


def test_membership_source_manifest_must_match_umbrella_snapshot() -> None:
    protocol = replace(
        _protocol(),
        membership_source=replace(
            _protocol().membership_source,
            manifest_hash="f" * 64,
        ),
    )
    request = replace(_request(), declared_protocol=protocol)
    runtime = request.runtime_validation
    assert type(runtime) is RuntimeValidationEvidence
    evidence = ResearchValidationAuthorityEvidence.create(
        protocol=protocol,
        snapshot_identity=request.snapshot_identity,
        runtime_evidence_hash=runtime.payload_hash,
        universe_membership_hash="e" * 64,
        requires_pit_universe=True,
        dataset_bindings=request.declared_requirements,
    )

    assessment = assess_validation_authority(_ReadyProbe(evidence), request)

    assert assessment.check.code == "VALIDATION_AUTHORITY_MISMATCH"


def test_calendar_source_manifest_must_match_umbrella_snapshot() -> None:
    protocol = _protocol()
    calendar = protocol.trading_calendar
    changed_calendar = TradingCalendarEvidence.create(
        calendar_id=calendar.calendar_id,
        version=calendar.version,
        source=TradingCalendarSourceIdentity(
            dataset_id=calendar.dataset_id,
            snapshot_id=calendar.snapshot_id,
            manifest_hash="f" * 64,
            certified_through=calendar.certified_through,
            authority_as_of=calendar.authority_as_of,
        ),
        month_closures=calendar.month_closures,
    )
    protocol = replace(protocol, trading_calendar=changed_calendar)
    request = replace(_request(), declared_protocol=protocol)
    evidence = _evidence(request, protocol=protocol)

    assessment = assess_validation_authority(_ReadyProbe(evidence), request)

    assert assessment.check.code == "VALIDATION_AUTHORITY_MISMATCH"


def test_runtime_universe_must_match_membership_source_universe() -> None:
    protocol = replace(
        _protocol(),
        membership_source=replace(
            _protocol().membership_source,
            universe_id="another-universe",
        ),
    )
    request = replace(_request(), declared_protocol=protocol)
    evidence = _evidence(request, protocol=protocol)

    assessment = assess_validation_authority(_ReadyProbe(evidence), request)

    assert assessment.check.code == "VALIDATION_AUTHORITY_MISMATCH"


@pytest.mark.parametrize("source_kind", ["calendar", "membership"])
def test_protocol_source_snapshot_must_belong_to_dataset_binding(
    source_kind: str,
) -> None:
    protocol = _protocol()
    if source_kind == "calendar":
        calendar = protocol.trading_calendar
        changed_calendar = TradingCalendarEvidence.create(
            calendar_id=calendar.calendar_id,
            version=calendar.version,
            source=TradingCalendarSourceIdentity(
                dataset_id=calendar.dataset_id,
                snapshot_id="unbound-calendar-snapshot",
                manifest_hash=calendar.manifest_hash,
                certified_through=calendar.certified_through,
                authority_as_of=calendar.authority_as_of,
            ),
            month_closures=calendar.month_closures,
        )
        protocol = replace(protocol, trading_calendar=changed_calendar)
    else:
        protocol = replace(
            protocol,
            membership_source=replace(
                protocol.membership_source,
                snapshot_id="unbound-membership-snapshot",
            ),
        )
    request = replace(_request(), declared_protocol=protocol)
    evidence = _evidence(request, protocol=protocol)

    assessment = assess_validation_authority(_ReadyProbe(evidence), request)

    assert assessment.check.code == "VALIDATION_AUTHORITY_MISMATCH"


def test_required_input_start_must_equal_latest_dataset_certification_start() -> None:
    requirements = (
        ResearchDatasetRequirement(
            "etf_daily", ("etf-provider",), True, date(2026, 1, 2)
        ),
        ResearchDatasetRequirement(
            "trade_cal", ("calendar-provider",), False, date(2026, 1, 1)
        ),
    )
    request = replace(_request(), declared_requirements=requirements)
    evidence = _evidence(request, bindings=requirements)

    assessment = assess_validation_authority(_ReadyProbe(evidence), request)

    assert assessment.check.code == "VALIDATION_AUTHORITY_MISMATCH"


def test_persisted_authority_summary_uses_compiled_continuous_eligible_suffix() -> None:
    months: list[CalendarMonth] = []
    year = 2016
    month = 1
    for _ in range(100):
        months.append(CalendarMonth(year, month))
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    typed_months = tuple(months)
    sessions = _weekday_sessions(typed_months)
    instrument = InstrumentEligibilityEvidence(
        instrument_id="510300.SH",
        listing_date=sessions[0],
        base_data_eligible_start=sessions[0],
        warmup_sessions=21,
        eligible_from=sessions[21],
        membership_intervals=(
            PitUniverseMembershipInterval(months[0], months[49]),
            PitUniverseMembershipInterval(months[51], months[-1]),
        ),
    )
    protocol = ValidationProtocolRequest(
        trading_sessions=sessions,
        strategy_eligible_start=instrument.eligible_from,
        last_complete_month=months[-1],
        coverage_policy=UniverseCoveragePolicy("a-share-core", 1),
        coverage_decisions=tuple(
            MonthCoverageDecision.create(
                month=calendar_month,
                eligibility=(
                    CoverageEligibility.INELIGIBLE
                    if index == 50
                    else CoverageEligibility.ELIGIBLE
                ),
                universe_instrument_ids=(
                    () if index == 50 else (instrument.instrument_id,)
                ),
                eligible_instrument_ids=(
                    () if index == 50 else (instrument.instrument_id,)
                ),
            )
            for index, calendar_month in enumerate(months)
            if index > 0
        ),
        isolation=IsolationSemantics(2, 5, 1),
        trading_calendar=_calendar(typed_months, sessions),
        instrument_eligibility=(instrument,),
        required_input_start=sessions[0],
        membership_source=UniverseMembershipSource(
            "csi_etf_broad",
            "etf_daily",
            "etf-provider",
            "d" * 64,
        ),
        planning_decision_date=_calendar(typed_months, sessions).authority_as_of,
    )
    requirements = (
        ResearchDatasetRequirement("etf_daily", ("etf-provider",), True, sessions[0]),
        ResearchDatasetRequirement(
            "trade_cal", ("calendar-provider",), False, sessions[0]
        ),
    )
    request = replace(
        _request(),
        declared_protocol=protocol,
        declared_requirements=requirements,
    )
    evidence = _evidence(request, protocol=protocol)

    assessment = assess_validation_authority(_ReadyProbe(evidence), request)

    assert assessment.check.outcome.value == "pass"
    summaries = assessment.check.observed["summaries"]
    assert summaries["eligibility"]["eligible_month_count"] == 49
    assert summaries["eligibility"]["instrument_eligibility"] == [
        {
            "instrument_id": instrument.instrument_id,
            "listing_date": instrument.listing_date.isoformat(),
            "base_data_eligible_start": (
                instrument.base_data_eligible_start.isoformat()
            ),
            "warmup_sessions": 21,
            "eligible_from": instrument.eligible_from.isoformat(),
            "membership_intervals": [
                {
                    "start_month": str(months[0]),
                    "end_month": str(months[49]),
                },
                {
                    "start_month": str(months[51]),
                    "end_month": str(months[-1]),
                },
            ],
        }
    ]


def test_compile_failure_is_caught_before_authority_summaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    evidence = _evidence(request)
    summaries_touched = False

    def _raise_compile(_: object) -> None:
        raise ValueError("malformed protocol")

    def _raise_summaries(_: object) -> object:
        nonlocal summaries_touched
        summaries_touched = True
        raise AssertionError("summaries must not be read before compilation")

    monkeypatch.setattr(
        _validation_authority,
        "compile_validation_protocol",
        _raise_compile,
    )
    monkeypatch.setattr(
        ResearchValidationAuthorityEvidence,
        "summaries",
        property(_raise_summaries),
    )

    assessment = assess_validation_authority(_ReadyProbe(evidence), request)

    assert assessment.check.code == "VALIDATION_AUTHORITY_INVALID"
    assert summaries_touched is False


@pytest.mark.parametrize(
    ("field_name", "forged_value"),
    [
        ("payload_hash", "not-a-hash"),
        ("protocol", object()),
        ("dataset_bindings", (object(),)),
    ],
)
def test_malformed_evidence_fields_fail_closed_as_authority_invalid(
    field_name: str,
    forged_value: object,
) -> None:
    request = _request()
    evidence = _evidence(request)
    object.__setattr__(evidence, field_name, forged_value)

    assessment = assess_validation_authority(_ReadyProbe(evidence), request)

    assert assessment.check.code == "VALIDATION_AUTHORITY_INVALID"
    assert assessment.evidence is None
    assert assessment.validation is None
