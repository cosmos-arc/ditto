"""Production validation authority derived from immutable research artifacts."""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from typing import Protocol, cast

import polars as pl

from ditto_application.builders.research_artifact_loader import (
    IndexedResearchArtifactLoader,
)
from ditto_application.builders.research_validation_authority import (
    SnapshotValidationAuthorityFacts,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.execution_bundle import (
    ContentAddressedResearchInput,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
)
from ditto_application.processes.experiments.research_snapshot_manifest import (
    VerifiedResearchSnapshotManifest,
)
from ditto_application.research_certification_contracts import (
    ExperimentSnapshotIdentity,
    ResearchDatasetRequirement,
)
from ditto_application.research_validation_calendar import complete_months
from ditto_application.research_validation_contracts import (
    ResearchValidationAuthorityRequest,
    RuntimeValidationEvidence,
)
from ditto_application.research_validation_eligibility import (
    project_month_membership,
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
    compile_validation_protocol,
)

__all__ = [
    "IndexedSnapshotValidationAuthoritySource",
    "SnapshotValidationAuthorityRequest",
]

_PRIMARY_DATASET_BY_LANE = {
    "etf_rotation": "etf_daily",
    "stock_selection": "stock_daily",
}
_REQUIRED_INPUT_KINDS = ("bars", "calendar", "membership", "instrument_rules")


class _ArtifactReader(Protocol):
    def read_frozen_research_input_bytes(self, artifact_id: str) -> bytes:
        """Return verified bytes for one immutable planning input."""
        ...


@dataclass(frozen=True, slots=True)
class SnapshotValidationAuthorityRequest:
    """Inputs measured by the snapshot source before a caller declares a protocol."""

    snapshot_identity: ExperimentSnapshotIdentity
    runtime_validation: RuntimeValidationEvidence
    declared_requirements: tuple[ResearchDatasetRequirement, ...]
    planning_decision_date: date


def _error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        "snapshot validation authority evidence is invalid",
        details={
            "code": "VALIDATION_AUTHORITY_INVALID",
            "reason": reason,
            **details,
        },
    )


def _exact_date(value: object, *, field: str) -> date:
    if type(value) is date:
        return value
    if type(value) is str:
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            pass
        else:
            if parsed.isoformat() == value:
                return parsed
    raise _error("invalid_snapshot_authority_date", field=field)


def _months(start: CalendarMonth, end: CalendarMonth) -> tuple[CalendarMonth, ...]:
    values: list[CalendarMonth] = []
    current = start
    while current <= end:
        values.append(current)
        current = current.next()
    return tuple(values)


def _compress_months(
    values: tuple[CalendarMonth, ...],
) -> tuple[PitUniverseMembershipInterval, ...]:
    if not values:
        return ()
    intervals: list[PitUniverseMembershipInterval] = []
    start = values[0]
    end = start
    for current in values[1:]:
        if current == end.next():
            end = current
            continue
        intervals.append(PitUniverseMembershipInterval(start, end))
        start = current
        end = current
    intervals.append(PitUniverseMembershipInterval(start, end))
    return tuple(intervals)


def _select_input(
    manifest: VerifiedResearchSnapshotManifest,
    kind: str,
) -> ContentAddressedResearchInput:
    matches = tuple(
        item for item in manifest.snapshot_binding.inputs if item.artifact_kind == kind
    )
    if len(matches) != 1:
        raise _error(
            "snapshot_authority_input_missing_or_ambiguous",
            artifact_kind=kind,
            observed_count=len(matches),
        )
    return matches[0]


def _runtime(request: SnapshotValidationAuthorityRequest) -> RuntimeValidationEvidence:
    runtime = request.runtime_validation
    if type(runtime) is not RuntimeValidationEvidence or not runtime.is_valid():
        raise _error("snapshot_authority_runtime_invalid")
    return runtime


def _primary_binding(
    request: SnapshotValidationAuthorityRequest,
    runtime: RuntimeValidationEvidence,
) -> ResearchDatasetRequirement:
    primary_dataset = _PRIMARY_DATASET_BY_LANE.get(runtime.lane)
    if primary_dataset is None:
        raise _error("snapshot_authority_lane_unsupported", lane=runtime.lane)
    if tuple(item.dataset_id for item in request.declared_requirements) != (
        runtime.required_datasets
    ):
        raise _error("snapshot_authority_dataset_binding_mismatch")
    matches = tuple(
        item
        for item in request.declared_requirements
        if item.dataset_id == primary_dataset
    )
    if len(matches) != 1:
        raise _error("snapshot_authority_primary_dataset_missing")
    binding = matches[0]
    if binding.certified_from is None or not binding.requires_pit_universe:
        raise _error("snapshot_authority_primary_dataset_uncertified")
    return binding


def _calendar_facts(
    frame: pl.DataFrame,
) -> tuple[
    tuple[date, ...],
    tuple[CalendarMonth, ...],
    dict[CalendarMonth, tuple[date, ...]],
    tuple[TradingCalendarMonthClosure, ...],
    date,
]:
    rows = frame.select("trade_date", "is_open").iter_rows()
    all_dates: list[date] = []
    sessions: list[date] = []
    for raw_date, raw_open in rows:
        observed = _exact_date(raw_date, field="calendar.trade_date")
        if type(raw_open) is not bool:
            raise _error("snapshot_authority_calendar_status_invalid")
        all_dates.append(observed)
        if raw_open:
            sessions.append(observed)
    if (
        not all_dates
        or len(set(all_dates)) != len(all_dates)
        or any(current >= following for current, following in pairwise(all_dates))
        or not sessions
    ):
        raise _error("snapshot_authority_calendar_invalid")
    first = all_dates[0]
    last = all_dates[-1]
    if first.day != 1 or last.day != monthrange(last.year, last.month)[1]:
        raise _error("snapshot_authority_calendar_partial_month")
    months = _months(CalendarMonth.from_date(first), CalendarMonth.from_date(last))
    session_months = {
        month: tuple(
            session
            for session in sessions
            if (session.year, session.month) == (month.year, month.month)
        )
        for month in months
    }
    if any(not values for values in session_months.values()):
        raise _error("snapshot_authority_calendar_month_missing")
    closures = tuple(
        TradingCalendarMonthClosure.create(
            month=month,
            open_sessions=session_months[month],
        )
        for month in months
    )
    return tuple(sessions), months, session_months, closures, last


def _membership_by_instrument(frame: pl.DataFrame) -> dict[int, dict[date, bool]]:
    result: dict[int, dict[date, bool]] = {}
    for raw_date, raw_id, raw_member, raw_known_at in frame.select(
        "trade_date", "instrument_id", "is_member", "known_at"
    ).iter_rows():
        trade_date = _exact_date(raw_date, field="membership.trade_date")
        known_at = _exact_date(raw_known_at, field="membership.known_at")
        if (
            type(raw_id) is not int
            or raw_id <= 0
            or type(raw_member) is not bool
            or known_at > trade_date
        ):
            raise _error("snapshot_authority_membership_row_invalid")
        rows = result.setdefault(raw_id, {})
        if trade_date in rows:
            raise _error("snapshot_authority_membership_duplicate")
        rows[trade_date] = raw_member
    if not result:
        raise _error("snapshot_authority_membership_empty")
    return result


def _bar_keys(frame: pl.DataFrame) -> set[tuple[date, int]]:
    keys: set[tuple[date, int]] = set()
    for raw_date, raw_id in frame.select("trade_date", "instrument_id").iter_rows():
        trade_date = _exact_date(raw_date, field="bars.trade_date")
        if type(raw_id) is not int or raw_id <= 0:
            raise _error("snapshot_authority_bar_row_invalid")
        key = (trade_date, raw_id)
        if key in keys:
            raise _error("snapshot_authority_bar_duplicate")
        keys.add(key)
    return keys


def _listing_dates(frame: pl.DataFrame) -> dict[int, date | None]:
    result: dict[int, date | None] = {}
    for raw_id, raw_ipo in frame.select("instrument_id", "ipo_date").iter_rows():
        if type(raw_id) is not int or raw_id <= 0:
            raise _error("snapshot_authority_rule_row_invalid")
        ipo = None if raw_ipo is None else _exact_date(raw_ipo, field="rules.ipo_date")
        existing = result.get(raw_id)
        if raw_id in result and existing != ipo:
            raise _error("snapshot_authority_listing_date_ambiguous")
        result[raw_id] = ipo
    return result


@dataclass(frozen=True, slots=True)
class _InstrumentEvidenceContext:
    membership: dict[int, dict[date, bool]]
    bar_keys: set[tuple[date, int]]
    listing_dates: dict[int, date | None]
    sessions: tuple[date, ...]
    months: tuple[CalendarMonth, ...]
    session_months: Mapping[CalendarMonth, tuple[date, ...]]
    required_start: date
    warmup_sessions: int


def _instrument_evidence(
    context: _InstrumentEvidenceContext,
) -> tuple[InstrumentEligibilityEvidence, ...]:
    """Derive instrument eligibility from one complete authority context."""
    membership = context.membership
    bar_keys = context.bar_keys
    listing_dates = context.listing_dates
    sessions = context.sessions
    months = context.months
    session_months = context.session_months
    required_start = context.required_start
    warmup_sessions = context.warmup_sessions
    evidence: list[InstrumentEligibilityEvidence] = []
    for instrument_id in sorted(membership):
        if instrument_id not in listing_dates:
            raise _error("snapshot_authority_instrument_rules_missing")
        rows = membership[instrument_id]
        active_months = tuple(
            month
            for month in months
            if all(rows.get(session) is True for session in session_months[month])
        )
        if not active_months:
            continue
        listing_date = listing_dates[instrument_id] or sessions[0]
        listing_month = CalendarMonth.from_date(listing_date)
        listing_month_sessions = session_months.get(listing_month, ())
        if listing_month_sessions and listing_date != listing_month_sessions[0]:
            active_months = tuple(
                month for month in active_months if month != listing_month
            )
        if not active_months:
            continue
        active_sessions = tuple(
            session for month in active_months for session in session_months[month]
        )
        if any((session, instrument_id) not in bar_keys for session in active_sessions):
            raise _error(
                "snapshot_authority_member_bar_missing",
                instrument_id=instrument_id,
            )
        eligible_sessions = tuple(
            session
            for session in sessions
            if session >= max(listing_date, required_start)
        )
        if len(eligible_sessions) <= warmup_sessions:
            continue
        evidence.append(
            InstrumentEligibilityEvidence(
                instrument_id=str(instrument_id),
                listing_date=listing_date,
                base_data_eligible_start=required_start,
                warmup_sessions=warmup_sessions,
                eligible_from=eligible_sessions[warmup_sessions],
                membership_intervals=_compress_months(active_months),
            )
        )
    if not evidence:
        raise _error("snapshot_authority_no_eligible_instruments")
    return tuple(evidence)


def _coverage_decisions(
    *,
    months: tuple[CalendarMonth, ...],
    instruments: tuple[InstrumentEligibilityEvidence, ...],
    session_months: Mapping[CalendarMonth, tuple[date, ...]],
    policy: UniverseCoveragePolicy,
) -> tuple[MonthCoverageDecision, ...]:
    decisions: list[MonthCoverageDecision] = []
    for month in months:
        universe_ids, eligible_ids, _consumed = project_month_membership(
            month=month,
            first_session=session_months[month][0],
            instruments=instruments,
        )
        eligible = (
            len(eligible_ids) >= policy.min_eligible_instrument_count
            and bool(universe_ids)
            and len(eligible_ids) * 10_000
            >= len(universe_ids) * policy.min_coverage_ratio_bps
        )
        decisions.append(
            MonthCoverageDecision.create(
                month=month,
                eligibility=(
                    CoverageEligibility.ELIGIBLE
                    if eligible
                    else CoverageEligibility.INELIGIBLE
                ),
                universe_instrument_ids=universe_ids,
                eligible_instrument_ids=eligible_ids,
            )
        )
    return tuple(decisions)


class IndexedSnapshotValidationAuthoritySource:
    """Measure validation facts from verified manifest, frame, and rule bytes."""

    def __init__(self, artifact_service: _ArtifactReader) -> None:
        self._artifacts = artifact_service

    def resolve(
        self,
        request: ResearchValidationAuthorityRequest,
    ) -> SnapshotValidationAuthorityFacts:
        """Resolve facts while preserving the validated caller decision date."""
        runtime = request.runtime_validation
        if type(runtime) is not RuntimeValidationEvidence:
            raise _error("snapshot_authority_runtime_invalid")
        return self.resolve_snapshot(
            SnapshotValidationAuthorityRequest(
                snapshot_identity=request.snapshot_identity,
                runtime_validation=runtime,
                declared_requirements=request.declared_requirements,
                planning_decision_date=(
                    request.declared_protocol.planning_decision_date
                ),
            )
        )

    def resolve_snapshot(
        self,
        request: SnapshotValidationAuthorityRequest,
    ) -> SnapshotValidationAuthorityFacts:
        """Derive the exact protocol before a planning document can declare it."""
        runtime = _runtime(request)
        primary = _primary_binding(request, runtime)
        exact_snapshot = ExactResearchSnapshot(
            request.snapshot_identity.snapshot_id,
            request.snapshot_identity.manifest_hash,
        )
        manifest = VerifiedResearchSnapshotManifest(
            exact_snapshot=exact_snapshot,
            manifest_bytes=self._artifacts.read_frozen_research_input_bytes(
                exact_snapshot.snapshot_id
            ),
        )
        if not set(primary.expected_snapshot_ids).issubset(
            manifest.snapshot_binding.source_snapshot_ids
        ):
            raise _error("snapshot_authority_source_binding_missing")
        inputs = {kind: _select_input(manifest, kind) for kind in _REQUIRED_INPUT_KINDS}
        loader = IndexedResearchArtifactLoader(artifact_service=self._artifacts)
        calendar = loader.load_frame(inputs["calendar"])
        membership = loader.load_frame(inputs["membership"])
        bars = loader.load_frame(inputs["bars"])
        rules = loader.load_instrument_rules(inputs["instrument_rules"])
        source_ids = set(membership.source_snapshot_ids)
        if len(source_ids) != 1 or not source_ids.issubset(
            primary.expected_snapshot_ids
        ):
            raise _error("snapshot_authority_membership_source_mismatch")
        source_id = next(iter(source_ids))

        sessions, months, session_months, closures, authority_as_of = _calendar_facts(
            calendar.frame
        )
        required_start = max(
            cast("date", item.certified_from) for item in request.declared_requirements
        )
        instruments = _instrument_evidence(
            _InstrumentEvidenceContext(
                membership=_membership_by_instrument(membership.frame),
                bar_keys=_bar_keys(bars.frame),
                listing_dates=_listing_dates(rules.frame),
                sessions=sessions,
                months=months,
                session_months=session_months,
                required_start=required_start,
                warmup_sessions=runtime.max_lookback_sessions,
            )
        )
        strategy_eligible_start = min(item.eligible_from for item in instruments)
        last_month = months[-1]
        decision_months = complete_months(
            session_months=dict(session_months),
            strategy_eligible_start=strategy_eligible_start,
            last_complete_month=last_month,
        )
        policy = UniverseCoveragePolicy("a-share-core", 1)
        protocol = ValidationProtocolRequest(
            trading_sessions=sessions,
            strategy_eligible_start=strategy_eligible_start,
            last_complete_month=last_month,
            coverage_policy=policy,
            coverage_decisions=_coverage_decisions(
                months=decision_months,
                instruments=instruments,
                session_months=session_months,
                policy=policy,
            ),
            isolation=IsolationSemantics(
                cast("int", runtime.forward_horizon_sessions),
                cast("int", runtime.holding_period_sessions),
                cast("int", runtime.execution_lag_sessions),
            ),
            trading_calendar=TradingCalendarEvidence.create(
                calendar_id="sse-szse-a-share",
                version=1,
                source=TradingCalendarSourceIdentity(
                    primary.dataset_id,
                    source_id,
                    request.snapshot_identity.manifest_hash,
                    authority_as_of,
                    authority_as_of,
                ),
                month_closures=closures,
            ),
            instrument_eligibility=instruments,
            required_input_start=required_start,
            membership_source=UniverseMembershipSource(
                runtime.universe_id,
                primary.dataset_id,
                source_id,
                request.snapshot_identity.manifest_hash,
            ),
            planning_decision_date=request.planning_decision_date,
        )
        compile_validation_protocol(protocol)
        return SnapshotValidationAuthorityFacts(
            protocol=protocol,
            universe_membership_hash=membership.verified_content_hash,
            dataset_bindings=request.declared_requirements,
        )
