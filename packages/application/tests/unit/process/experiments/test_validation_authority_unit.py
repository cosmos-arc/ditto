"""Fail-closed contracts for the production validation authority boundary."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest
from ditto_application.builders.research_validation_authority import (
    ProductionResearchValidationAuthorityProbe,
    SnapshotValidationAuthorityFacts,
)
from ditto_application.research_certification_contracts import (
    ExperimentSnapshotIdentity,
    ResearchDatasetRequirement,
)
from ditto_application.research_validation_contracts import (
    ResearchValidationAuthorityEvidence,
    ResearchValidationAuthorityRequest,
    RuntimeValidationEvidence,
    validation_authority_facts_match,
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


def _weekday_sessions(months: tuple[CalendarMonth, ...]) -> tuple[date, ...]:
    sessions: list[date] = []
    for month in months:
        current = date(month.year, month.month, 1)
        following = month.next()
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
    closures = tuple(
        TradingCalendarMonthClosure.create(
            month=month,
            open_sessions=_month_sessions(sessions, month),
        )
        for month in months
    )
    calendar = TradingCalendarEvidence.create(
        calendar_id="sse-szse-a-share",
        version=1,
        source=TradingCalendarSourceIdentity(
            dataset_id="trade_cal",
            snapshot_id="provider-1",
            manifest_hash="d" * 64,
            certified_through=closures[-1].days[-1].calendar_date,
            authority_as_of=closures[-1].days[-1].calendar_date,
        ),
        month_closures=closures,
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
        trading_calendar=calendar,
        instrument_eligibility=(instrument,),
        required_input_start=sessions[0],
        membership_source=UniverseMembershipSource(
            "csi_etf_broad",
            "etf_daily",
            "provider-1",
            "d" * 64,
        ),
        planning_decision_date=calendar.authority_as_of,
    )


def _runtime(
    *,
    forward: int | None = None,
    holding: int | None = None,
    lag: int | None = None,
) -> RuntimeValidationEvidence:
    return RuntimeValidationEvidence(
        lane="etf_rotation",
        universe_id="csi_etf_broad",
        required_datasets=("etf_daily",),
        max_lookback_sessions=21,
        requires_pit_universe=True,
        forward_horizon_sessions=forward,
        holding_period_sessions=holding,
        execution_lag_sessions=lag,
    )


def _request(
    runtime: RuntimeValidationEvidence,
    *,
    declared_protocol: ValidationProtocolRequest | None = None,
) -> ResearchValidationAuthorityRequest:
    return ResearchValidationAuthorityRequest(
        snapshot_identity=ExperimentSnapshotIdentity("snapshot-1", "d" * 64),
        runtime_validation=runtime,
        declared_protocol=declared_protocol or _protocol(),
        declared_requirements=(
            ResearchDatasetRequirement(
                "etf_daily",
                ("provider-1",),
                requires_pit_universe=True,
                certified_from=date(2026, 1, 1),
            ),
        ),
    )


def test_production_authority_rejects_unregistered_isolation_without_caller_echo() -> (
    None
):
    authority = ProductionResearchValidationAuthorityProbe()
    request = _request(_runtime())

    original = authority.probe(request)
    forged = authority.probe(
        replace(
            request,
            declared_protocol=_protocol(isolation=IsolationSemantics(0, 0, 0)),
        )
    )

    assert original == forged
    assert original.ready is False
    assert original.code == "VALIDATION_SEMANTICS_UNREGISTERED"
    assert original.evidence is None


def test_registered_zero_isolation_still_cannot_fake_missing_pit_universe() -> None:
    result = ProductionResearchValidationAuthorityProbe().probe(
        _request(_runtime(forward=0, holding=0, lag=0))
    )

    assert result.ready is False
    assert result.code == "PIT_UNIVERSE_UNRESOLVED"
    assert result.evidence is None


def test_production_authority_signs_only_snapshot_backed_facts() -> None:
    request = _request(_runtime(forward=2, holding=5, lag=1))

    class _SnapshotSource:
        def resolve(
            self,
            request: ResearchValidationAuthorityRequest,
        ) -> SnapshotValidationAuthorityFacts:
            assert request is authority_request
            return SnapshotValidationAuthorityFacts(
                protocol=_protocol(),
                universe_membership_hash="9" * 64,
                dataset_bindings=authority_request.declared_requirements,
            )

    authority_request = request
    result = ProductionResearchValidationAuthorityProbe(_SnapshotSource()).probe(
        authority_request
    )

    assert result.ready is True
    assert result.code is None
    assert result.reason is None
    assert result.remediation is None
    assert result.evidence is not None
    assert result.evidence.protocol == _protocol()
    assert result.evidence.universe_membership_hash == "9" * 64
    runtime = authority_request.runtime_validation
    assert runtime is not None
    assert result.evidence.runtime_evidence_hash == runtime.payload_hash


def test_authority_evidence_canonicalizes_semantic_identifier_permutations() -> None:
    runtime = _runtime(forward=2, holding=5, lag=1)
    first = ResearchValidationAuthorityEvidence.create(
        protocol=_protocol(),
        snapshot_identity=ExperimentSnapshotIdentity("research-1", "d" * 64),
        runtime_evidence_hash=runtime.payload_hash,
        universe_membership_hash="e" * 64,
        requires_pit_universe=True,
        dataset_bindings=(
            ResearchDatasetRequirement(
                "trade_cal", ("provider-2", "provider-1"), True, date(2026, 1, 1)
            ),
            ResearchDatasetRequirement(
                "etf_daily", ("provider-2", "provider-1"), True, date(2026, 1, 1)
            ),
        ),
    )
    second = ResearchValidationAuthorityEvidence.create(
        protocol=_protocol(),
        snapshot_identity=ExperimentSnapshotIdentity("research-1", "d" * 64),
        runtime_evidence_hash=runtime.payload_hash,
        universe_membership_hash="e" * 64,
        requires_pit_universe=True,
        dataset_bindings=(
            ResearchDatasetRequirement(
                "etf_daily", ("provider-1", "provider-2"), True, date(2026, 1, 1)
            ),
            ResearchDatasetRequirement(
                "trade_cal", ("provider-1", "provider-2"), True, date(2026, 1, 1)
            ),
        ),
    )

    assert first.payload_hash == second.payload_hash
    assert tuple(binding.dataset_id for binding in first.dataset_bindings) == (
        "etf_daily",
        "trade_cal",
    )
    assert first.snapshot_identity == ExperimentSnapshotIdentity("research-1", "d" * 64)
    assert first.summaries["semantics"] == {
        "execution_lag_sessions": 1,
        "forward_horizon_sessions": 2,
        "holding_period_sessions": 5,
    }
    assert first.summaries["calendar"]["session_count"] == len(
        _protocol().trading_sessions
    )


def test_authority_fact_replay_does_not_trust_dataclass_equality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = RuntimeValidationEvidence(
        lane="etf_rotation",
        universe_id="csi_etf_broad",
        required_datasets=("etf_daily", "trade_cal"),
        max_lookback_sessions=21,
        requires_pit_universe=True,
        forward_horizon_sessions=2,
        holding_period_sessions=5,
        execution_lag_sessions=1,
    )
    snapshot = ExperimentSnapshotIdentity("research-1", "d" * 64)
    requirements = (
        ResearchDatasetRequirement(
            "etf_daily", ("provider-1",), True, date(2026, 1, 1)
        ),
        ResearchDatasetRequirement(
            "trade_cal", ("provider-1",), False, date(2026, 1, 1)
        ),
    )
    evidence = ResearchValidationAuthorityEvidence.create(
        protocol=_protocol(),
        snapshot_identity=snapshot,
        runtime_evidence_hash=runtime.payload_hash,
        universe_membership_hash="e" * 64,
        requires_pit_universe=True,
        dataset_bindings=requirements,
    )

    assert validation_authority_facts_match(
        evidence,
        runtime,
        snapshot_identity=snapshot,
        dataset_requirements=requirements,
    )

    monkeypatch.setattr(ExperimentSnapshotIdentity, "__eq__", lambda *_: True)
    monkeypatch.setattr(ResearchDatasetRequirement, "__eq__", lambda *_: True)

    assert not validation_authority_facts_match(
        evidence,
        runtime,
        snapshot_identity=ExperimentSnapshotIdentity("other-snapshot", "d" * 64),
        dataset_requirements=requirements,
    )
    drifted_requirements = (
        replace(requirements[0], expected_snapshot_ids=("other-provider",)),
        requirements[1],
    )
    assert not validation_authority_facts_match(
        evidence,
        runtime,
        snapshot_identity=snapshot,
        dataset_requirements=drifted_requirements,
    )
