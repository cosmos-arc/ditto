"""Immutable snapshot-backed production validation authority tests."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date, timedelta
from io import BytesIO
from typing import cast

import orjson
import polars as pl
import pytest
from ditto_application.builders import research_validation_authority_source as source
from ditto_application.builders.research_validation_authority_source import (
    IndexedSnapshotValidationAuthoritySource,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.execution_bundle import (
    ContentAddressedResearchInput,
)
from ditto_application.processes.experiments.research_data_artifacts import (
    research_frame_schema_hash,
)
from ditto_application.research_certification_contracts import (
    ExperimentSnapshotIdentity,
    ResearchDatasetRequirement,
)
from ditto_application.research_validation_contracts import (
    ResearchValidationAuthorityRequest,
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

SOURCE_ID = "tushare:etf_daily:live-snapshot"
SNAPSHOT_ID = "research-etf-live"


class _Artifacts:
    def __init__(self, payloads: dict[str, bytes]) -> None:
        self.payloads = payloads

    def read_frozen_research_input_bytes(self, artifact_id: str) -> bytes:
        return self.payloads[artifact_id]


def _parquet(frame: pl.DataFrame) -> bytes:
    buffer = BytesIO()
    frame.write_parquet(buffer)
    return buffer.getvalue()


def _evidence(
    input_id: str,
    kind: str,
    frame: pl.DataFrame,
) -> tuple[ContentAddressedResearchInput, bytes]:
    payload = _parquet(frame)
    return (
        ContentAddressedResearchInput(
            input_id,
            kind,
            hashlib.sha256(payload).hexdigest(),
            research_frame_schema_hash(frame),
        ),
        payload,
    )


def _rules_evidence(
    sessions: tuple[date, ...],
) -> tuple[ContentAddressedResearchInput, bytes]:
    frame = pl.DataFrame(
        {
            "instrument_code": ["510300.SH"],
            "instrument_id": [2_000_001],
            "asset_class": ["etf"],
            "exchange": ["XSHG"],
            "currency": ["CNY"],
            "tick_size": [0.001],
            "lot_size": [100],
            "multiplier": [1.0],
            "board_segment": ["fund"],
            "lifecycle_state": ["normal"],
            "ipo_date": [sessions[0]],
            "delisting_date": [None],
            "as_of_date": [sessions[-1]],
            "known_at": [sessions[-1]],
            "settlement_cycle": [1],
            "fund_settlement_cycle": [0],
            "price_limit_pct": [0.1],
            "order_types_supported": [["market", "limit"]],
            "call_auction_sessions": [["open", "close"]],
            "commission_rate": [0.0003],
            "min_commission": [5.0],
            "stamp_duty_rate": [0.0],
            "transfer_fee_rate": [0.00001],
            "source_snapshot_id": [SOURCE_ID],
        },
        schema={
            "instrument_code": pl.String,
            "instrument_id": pl.Int64,
            "asset_class": pl.String,
            "exchange": pl.String,
            "currency": pl.String,
            "tick_size": pl.Float64,
            "lot_size": pl.Int64,
            "multiplier": pl.Float64,
            "board_segment": pl.String,
            "lifecycle_state": pl.String,
            "ipo_date": pl.Date,
            "delisting_date": pl.Date,
            "as_of_date": pl.Date,
            "known_at": pl.Date,
            "settlement_cycle": pl.Int64,
            "fund_settlement_cycle": pl.Int64,
            "price_limit_pct": pl.Float64,
            "order_types_supported": pl.List(pl.String),
            "call_auction_sessions": pl.List(pl.String),
            "commission_rate": pl.Float64,
            "min_commission": pl.Float64,
            "stamp_duty_rate": pl.Float64,
            "transfer_fee_rate": pl.Float64,
            "source_snapshot_id": pl.String,
        },
    )
    payload = _parquet(frame)
    fields = tuple((name, str(dtype)) for name, dtype in frame.schema.items())
    return (
        ContentAddressedResearchInput(
            "rules-live",
            "instrument_rules",
            hashlib.sha256(payload).hexdigest(),
            hashlib.sha256(orjson.dumps(fields)).hexdigest(),
        ),
        payload,
    )


def _fixture() -> tuple[_Artifacts, ResearchValidationAuthorityRequest]:
    days = tuple(date(2025, 1, 1) + timedelta(days=index) for index in range(90))
    sessions = tuple(item for item in days if item.weekday() < 5)
    calendar = pl.DataFrame(
        {
            "trade_date": days,
            "is_open": tuple(item.weekday() < 5 for item in days),
            "source_snapshot_id": (SOURCE_ID,) * len(days),
        },
    )
    membership = pl.DataFrame(
        {
            "trade_date": sessions,
            "instrument_id": (2_000_001,) * len(sessions),
            "is_member": (True,) * len(sessions),
            "known_at": sessions,
            "source_snapshot_id": (SOURCE_ID,) * len(sessions),
        },
    )
    bars = pl.DataFrame(
        {
            "trade_date": sessions,
            "instrument_id": (2_000_001,) * len(sessions),
            "open": (1.0,) * len(sessions),
            "high": (1.1,) * len(sessions),
            "low": (0.9,) * len(sessions),
            "close": (1.0,) * len(sessions),
            "prev_close": (1.0,) * len(sessions),
            "volume": (1000.0,) * len(sessions),
            "amount": (1000.0,) * len(sessions),
            "is_suspended": (False,) * len(sessions),
            "limit_up": (False,) * len(sessions),
            "limit_down": (False,) * len(sessions),
            "avg_volume_20d": (1000.0,) * len(sessions),
            "source_snapshot_id": (SOURCE_ID,) * len(sessions),
        },
    )
    calendar_input, calendar_bytes = _evidence("calendar-live", "calendar", calendar)
    membership_input, membership_bytes = _evidence(
        "membership-live", "membership", membership
    )
    bars_input, bars_bytes = _evidence("bars-live", "bars", bars)
    rules_input, rules_bytes = _rules_evidence(sessions)
    inputs = tuple(
        sorted(
            (calendar_input, membership_input, bars_input, rules_input),
            key=lambda item: item.input_id,
        )
    )
    manifest = orjson.dumps(
        {
            "schema_version": 1,
            "snapshot_id": SNAPSHOT_ID,
            "dataset_id": "research-etf-rotation",
            "source_snapshot_ids": [SOURCE_ID],
            "known_at_policy": "sample_time",
            "builder_version": "research-builder-v1",
            "inputs": [dict(item.as_payload()) for item in inputs],
        },
        option=orjson.OPT_SORT_KEYS,
    )
    snapshot = ExperimentSnapshotIdentity(
        SNAPSHOT_ID,
        hashlib.sha256(manifest).hexdigest(),
    )
    placeholder = ValidationProtocolRequest(
        trading_sessions=sessions,
        strategy_eligible_start=sessions[2],
        last_complete_month=CalendarMonth(2025, 3),
        coverage_policy=UniverseCoveragePolicy("a-share-core", 1),
        coverage_decisions=(
            MonthCoverageDecision.create(
                month=CalendarMonth(2025, 2),
                eligibility=CoverageEligibility.ELIGIBLE,
                universe_instrument_ids=("2000001",),
                eligible_instrument_ids=("2000001",),
            ),
            MonthCoverageDecision.create(
                month=CalendarMonth(2025, 3),
                eligibility=CoverageEligibility.ELIGIBLE,
                universe_instrument_ids=("2000001",),
                eligible_instrument_ids=("2000001",),
            ),
        ),
        isolation=IsolationSemantics(2, 5, 1),
        trading_calendar=TradingCalendarEvidence.create(
            calendar_id="placeholder",
            version=1,
            source=TradingCalendarSourceIdentity(
                "etf_daily", SOURCE_ID, snapshot.manifest_hash, days[-1], days[-1]
            ),
            month_closures=tuple(
                TradingCalendarMonthClosure.create(
                    month=month,
                    open_sessions=tuple(
                        item
                        for item in sessions
                        if (item.year, item.month) == (month.year, month.month)
                    ),
                )
                for month in (
                    CalendarMonth(2025, 1),
                    CalendarMonth(2025, 2),
                    CalendarMonth(2025, 3),
                )
            ),
        ),
        instrument_eligibility=(
            InstrumentEligibilityEvidence(
                "2000001",
                sessions[0],
                days[0],
                2,
                sessions[2],
                (
                    PitUniverseMembershipInterval(
                        CalendarMonth(2025, 1), CalendarMonth(2025, 3)
                    ),
                ),
            ),
        ),
        required_input_start=days[0],
        membership_source=UniverseMembershipSource(
            "csi_etf_broad", "etf_daily", SOURCE_ID, snapshot.manifest_hash
        ),
        planning_decision_date=days[-1],
    )
    request = ResearchValidationAuthorityRequest(
        snapshot_identity=snapshot,
        runtime_validation=RuntimeValidationEvidence(
            lane="etf_rotation",
            universe_id="csi_etf_broad",
            required_datasets=("etf_daily",),
            max_lookback_sessions=2,
            requires_pit_universe=True,
            forward_horizon_sessions=2,
            holding_period_sessions=5,
            execution_lag_sessions=1,
        ),
        declared_protocol=placeholder,
        declared_requirements=(
            ResearchDatasetRequirement("etf_daily", (SOURCE_ID,), True, days[0]),
        ),
    )
    return (
        _Artifacts(
            {
                SNAPSHOT_ID: manifest,
                calendar_input.input_id: calendar_bytes,
                membership_input.input_id: membership_bytes,
                bars_input.input_id: bars_bytes,
                rules_input.input_id: rules_bytes,
            }
        ),
        request,
    )


@pytest.mark.unit
def test_source_derives_protocol_and_membership_hash_from_exact_snapshot() -> None:
    artifacts, request = _fixture()
    planning_date = request.declared_protocol.planning_decision_date + timedelta(days=1)
    request = replace(
        request,
        declared_protocol=replace(
            request.declared_protocol,
            planning_decision_date=planning_date,
        ),
    )

    facts = IndexedSnapshotValidationAuthoritySource(artifacts).resolve(request)

    assert (
        facts.universe_membership_hash
        == hashlib.sha256(artifacts.payloads["membership-live"]).hexdigest()
    )
    assert facts.protocol.membership_source.dataset_id == "etf_daily"
    assert facts.protocol.membership_source.snapshot_id == SOURCE_ID
    assert (
        facts.protocol.membership_source.manifest_hash
        == request.snapshot_identity.manifest_hash
    )
    assert facts.protocol.trading_sessions[0] == date(2025, 1, 1)
    assert facts.protocol.last_complete_month == CalendarMonth(2025, 3)
    assert facts.protocol.instrument_eligibility[0].warmup_sessions == 2
    assert facts.protocol.planning_decision_date == planning_date
    assert facts.dataset_bindings == request.declared_requirements


def _reason(error: AppProcessError) -> str:
    return cast("str", error.details["reason"])


def _snapshot_request(
    request: ResearchValidationAuthorityRequest,
    *,
    runtime: RuntimeValidationEvidence | None = None,
    requirements: tuple[ResearchDatasetRequirement, ...] | None = None,
) -> source.SnapshotValidationAuthorityRequest:
    selected_runtime = request.runtime_validation if runtime is None else runtime
    assert type(selected_runtime) is RuntimeValidationEvidence
    return source.SnapshotValidationAuthorityRequest(
        snapshot_identity=request.snapshot_identity,
        runtime_validation=selected_runtime,
        declared_requirements=(
            request.declared_requirements if requirements is None else requirements
        ),
        planning_decision_date=request.declared_protocol.planning_decision_date,
    )


def _runtime_evidence(
    lane: str = "etf_rotation",
    required_datasets: tuple[str, ...] = ("etf_daily",),
    *,
    isolated: bool = True,
) -> RuntimeValidationEvidence:
    return RuntimeValidationEvidence(
        lane,
        "csi_etf_broad",
        required_datasets,
        2,
        True,
        2 if isolated else None,
        5 if isolated else None,
        1 if isolated else None,
    )


def _requirements(
    dataset_id: str = "etf_daily",
    source_id: str = SOURCE_ID,
    *,
    certified: bool = True,
) -> tuple[ResearchDatasetRequirement, ...]:
    return (
        ResearchDatasetRequirement(
            dataset_id,
            (source_id,),
            True,
            date(2025, 1, 1) if certified else None,
        ),
    )


def _install_manifest(
    artifacts: _Artifacts,
    request: ResearchValidationAuthorityRequest,
    manifest: dict[str, object],
) -> ResearchValidationAuthorityRequest:
    payload = orjson.dumps(manifest, option=orjson.OPT_SORT_KEYS)
    artifacts.payloads[SNAPSHOT_ID] = payload
    return replace(
        request,
        snapshot_identity=ExperimentSnapshotIdentity(
            SNAPSHOT_ID,
            hashlib.sha256(payload).hexdigest(),
        ),
    )


def _replace_manifest_frame(
    artifacts: _Artifacts,
    request: ResearchValidationAuthorityRequest,
    *,
    input_id: str,
    frame: pl.DataFrame,
) -> ResearchValidationAuthorityRequest:
    payload = _parquet(frame)
    artifacts.payloads[input_id] = payload
    manifest = cast("dict[str, object]", orjson.loads(artifacts.payloads[SNAPSHOT_ID]))
    inputs = cast("list[dict[str, object]]", manifest["inputs"])
    target = next(item for item in inputs if item["input_id"] == input_id)
    target["content_hash"] = hashlib.sha256(payload).hexdigest()
    target["schema_hash"] = research_frame_schema_hash(frame)
    return _install_manifest(artifacts, request, manifest)


def _instrument_context() -> source._InstrumentEvidenceContext:
    january = CalendarMonth(2025, 1)
    february = CalendarMonth(2025, 2)
    january_sessions = (date(2025, 1, 2), date(2025, 1, 3))
    february_sessions = (date(2025, 2, 3), date(2025, 2, 4))
    sessions = january_sessions + february_sessions
    return source._InstrumentEvidenceContext(
        membership={1: dict.fromkeys(sessions, True)},
        bar_keys={(session, 1) for session in sessions},
        listing_dates={1: january_sessions[0]},
        sessions=sessions,
        months=(january, february),
        session_months={
            january: january_sessions,
            february: february_sessions,
        },
        required_start=january_sessions[0],
        warmup_sessions=0,
    )


@pytest.mark.unit
def test_exact_date_accepts_only_canonical_iso_dates() -> None:
    assert source._exact_date("2025-01-02", field="observed") == date(2025, 1, 2)

    for invalid in ("not-a-date", "20250102", 20250102):
        with pytest.raises(AppProcessError) as exc_info:
            source._exact_date(invalid, field="observed")

        assert _reason(exc_info.value) == "invalid_snapshot_authority_date"
        assert exc_info.value.details["field"] == "observed"


@pytest.mark.unit
def test_month_compression_preserves_empty_and_disjoint_intervals() -> None:
    january = CalendarMonth(2025, 1)
    march = CalendarMonth(2025, 3)

    assert source._compress_months(()) == ()
    assert source._compress_months((january, march)) == (
        PitUniverseMembershipInterval(january, january),
        PitUniverseMembershipInterval(march, march),
    )


@pytest.mark.unit
def test_snapshot_resolution_rejects_runtime_without_registered_isolation() -> None:
    artifacts, request = _fixture()
    runtime = _runtime_evidence(isolated=False)

    with pytest.raises(AppProcessError) as exc_info:
        IndexedSnapshotValidationAuthoritySource(artifacts).resolve_snapshot(
            _snapshot_request(request, runtime=runtime)
        )

    assert _reason(exc_info.value) == "snapshot_authority_runtime_invalid"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("runtime", "requirements", "expected_reason"),
    [
        (
            _runtime_evidence("unsupported_lane"),
            _requirements(),
            "snapshot_authority_lane_unsupported",
        ),
        (
            _runtime_evidence(required_datasets=("etf_daily", "trade_cal")),
            _requirements(),
            "snapshot_authority_dataset_binding_mismatch",
        ),
        (
            _runtime_evidence("stock_selection"),
            _requirements(),
            "snapshot_authority_primary_dataset_missing",
        ),
        (
            _runtime_evidence(),
            _requirements(certified=False),
            "snapshot_authority_primary_dataset_uncertified",
        ),
    ],
)
def test_primary_binding_fails_closed_on_unsupported_or_uncertified_inputs(
    runtime: RuntimeValidationEvidence,
    requirements: tuple[ResearchDatasetRequirement, ...],
    expected_reason: str,
) -> None:
    _, request = _fixture()
    measured = _snapshot_request(
        request,
        runtime=runtime,
        requirements=requirements,
    )

    with pytest.raises(AppProcessError) as exc_info:
        source._primary_binding(measured, runtime)

    assert _reason(exc_info.value) == expected_reason


@pytest.mark.unit
def test_calendar_rejects_non_boolean_status_and_empty_evidence() -> None:
    non_boolean = pl.DataFrame(
        {"trade_date": [date(2025, 1, 1)], "is_open": [1]},
        schema={"trade_date": pl.Date, "is_open": pl.Int64},
    )
    empty = pl.DataFrame(schema={"trade_date": pl.Date, "is_open": pl.Boolean})

    with pytest.raises(AppProcessError) as status_error:
        source._calendar_facts(non_boolean)
    with pytest.raises(AppProcessError) as empty_error:
        source._calendar_facts(empty)

    assert _reason(status_error.value) == "snapshot_authority_calendar_status_invalid"
    assert _reason(empty_error.value) == "snapshot_authority_calendar_invalid"


@pytest.mark.unit
def test_calendar_requires_complete_month_boundaries() -> None:
    days = tuple(date(2025, 1, 2) + timedelta(days=index) for index in range(30))
    frame = pl.DataFrame(
        {"trade_date": days, "is_open": (True,) * len(days)},
        schema={"trade_date": pl.Date, "is_open": pl.Boolean},
    )

    with pytest.raises(AppProcessError) as exc_info:
        source._calendar_facts(frame)

    assert _reason(exc_info.value) == "snapshot_authority_calendar_partial_month"


@pytest.mark.unit
def test_calendar_requires_open_sessions_in_every_observed_month() -> None:
    days = tuple(date(2025, 1, 1) + timedelta(days=index) for index in range(90))
    frame = pl.DataFrame(
        {
            "trade_date": days,
            "is_open": tuple(item.month != 2 for item in days),
        },
        schema={"trade_date": pl.Date, "is_open": pl.Boolean},
    )

    with pytest.raises(AppProcessError) as exc_info:
        source._calendar_facts(frame)

    assert _reason(exc_info.value) == "snapshot_authority_calendar_month_missing"


@pytest.mark.unit
@pytest.mark.pit
def test_membership_rejects_future_known_at_sentinel() -> None:
    frame = pl.DataFrame(
        {
            "trade_date": [date(2025, 1, 2)],
            "instrument_id": [1],
            "is_member": [True],
            "known_at": [date(2025, 1, 3)],
        },
        schema={
            "trade_date": pl.Date,
            "instrument_id": pl.Int64,
            "is_member": pl.Boolean,
            "known_at": pl.Date,
        },
    )

    with pytest.raises(AppProcessError) as exc_info:
        source._membership_by_instrument(frame)

    assert _reason(exc_info.value) == "snapshot_authority_membership_row_invalid"


@pytest.mark.unit
def test_membership_rejects_duplicate_and_empty_evidence() -> None:
    duplicate = pl.DataFrame(
        {
            "trade_date": [date(2025, 1, 2), date(2025, 1, 2)],
            "instrument_id": [1, 1],
            "is_member": [True, False],
            "known_at": [date(2025, 1, 2), date(2025, 1, 2)],
        },
        schema={
            "trade_date": pl.Date,
            "instrument_id": pl.Int64,
            "is_member": pl.Boolean,
            "known_at": pl.Date,
        },
    )
    empty = pl.DataFrame(
        schema={
            "trade_date": pl.Date,
            "instrument_id": pl.Int64,
            "is_member": pl.Boolean,
            "known_at": pl.Date,
        }
    )

    with pytest.raises(AppProcessError) as duplicate_error:
        source._membership_by_instrument(duplicate)
    with pytest.raises(AppProcessError) as empty_error:
        source._membership_by_instrument(empty)

    assert _reason(duplicate_error.value) == "snapshot_authority_membership_duplicate"
    assert _reason(empty_error.value) == "snapshot_authority_membership_empty"


@pytest.mark.unit
def test_bar_keys_reject_invalid_and_duplicate_rows() -> None:
    invalid = pl.DataFrame(
        {"trade_date": [date(2025, 1, 2)], "instrument_id": [0]},
        schema={"trade_date": pl.Date, "instrument_id": pl.Int64},
    )
    duplicate = pl.DataFrame(
        {
            "trade_date": [date(2025, 1, 2), date(2025, 1, 2)],
            "instrument_id": [1, 1],
        },
        schema={"trade_date": pl.Date, "instrument_id": pl.Int64},
    )

    with pytest.raises(AppProcessError) as invalid_error:
        source._bar_keys(invalid)
    with pytest.raises(AppProcessError) as duplicate_error:
        source._bar_keys(duplicate)

    assert _reason(invalid_error.value) == "snapshot_authority_bar_row_invalid"
    assert _reason(duplicate_error.value) == "snapshot_authority_bar_duplicate"


@pytest.mark.unit
def test_listing_dates_reject_invalid_identity_and_conflicting_dates() -> None:
    invalid = pl.DataFrame(
        {"instrument_id": [0], "ipo_date": [date(2025, 1, 2)]},
        schema={"instrument_id": pl.Int64, "ipo_date": pl.Date},
    )
    conflicting = pl.DataFrame(
        {
            "instrument_id": [1, 1],
            "ipo_date": [date(2025, 1, 2), date(2025, 1, 3)],
        },
        schema={"instrument_id": pl.Int64, "ipo_date": pl.Date},
    )

    with pytest.raises(AppProcessError) as invalid_error:
        source._listing_dates(invalid)
    with pytest.raises(AppProcessError) as conflict_error:
        source._listing_dates(conflicting)

    assert _reason(invalid_error.value) == "snapshot_authority_rule_row_invalid"
    assert _reason(conflict_error.value) == "snapshot_authority_listing_date_ambiguous"


@pytest.mark.unit
def test_instrument_evidence_requires_rules_for_every_member() -> None:
    context = replace(_instrument_context(), listing_dates={})

    with pytest.raises(AppProcessError) as exc_info:
        source._instrument_evidence(context)

    assert _reason(exc_info.value) == "snapshot_authority_instrument_rules_missing"


@pytest.mark.unit
def test_instrument_evidence_requires_an_active_month() -> None:
    context = _instrument_context()
    inactive = replace(
        context,
        membership={1: dict.fromkeys(context.sessions, False)},
    )

    with pytest.raises(AppProcessError) as exc_info:
        source._instrument_evidence(inactive)

    assert _reason(exc_info.value) == "snapshot_authority_no_eligible_instruments"


@pytest.mark.unit
def test_instrument_evidence_excludes_partial_listing_month() -> None:
    context = _instrument_context()
    january = context.months[0]
    january_sessions = context.session_months[january]
    partial_listing = replace(
        context,
        sessions=january_sessions,
        months=(january,),
        session_months={january: january_sessions},
        membership={1: dict.fromkeys(january_sessions, True)},
        bar_keys={(session, 1) for session in january_sessions},
        listing_dates={1: january_sessions[1]},
    )

    with pytest.raises(AppProcessError) as exc_info:
        source._instrument_evidence(partial_listing)

    assert _reason(exc_info.value) == "snapshot_authority_no_eligible_instruments"


@pytest.mark.unit
def test_instrument_evidence_requires_bars_for_active_members() -> None:
    context = _instrument_context()
    incomplete_bars = replace(
        context,
        bar_keys=set(context.bar_keys) - {(context.sessions[-1], 1)},
    )

    with pytest.raises(AppProcessError) as exc_info:
        source._instrument_evidence(incomplete_bars)

    assert _reason(exc_info.value) == "snapshot_authority_member_bar_missing"
    assert exc_info.value.details["instrument_id"] == 1


@pytest.mark.unit
def test_instrument_evidence_fails_when_warmup_consumes_every_session() -> None:
    context = _instrument_context()

    with pytest.raises(AppProcessError) as exc_info:
        source._instrument_evidence(
            replace(context, warmup_sessions=len(context.sessions))
        )

    assert _reason(exc_info.value) == "snapshot_authority_no_eligible_instruments"


@pytest.mark.unit
def test_public_resolution_rejects_missing_runtime_evidence() -> None:
    artifacts, request = _fixture()

    with pytest.raises(AppProcessError) as exc_info:
        IndexedSnapshotValidationAuthoritySource(artifacts).resolve(
            replace(request, runtime_validation=None)
        )

    assert _reason(exc_info.value) == "snapshot_authority_runtime_invalid"


@pytest.mark.unit
def test_snapshot_resolution_requires_declared_source_binding() -> None:
    artifacts, request = _fixture()
    requirements = _requirements(source_id="different-source")

    with pytest.raises(AppProcessError) as exc_info:
        IndexedSnapshotValidationAuthoritySource(artifacts).resolve_snapshot(
            _snapshot_request(request, requirements=requirements)
        )

    assert _reason(exc_info.value) == "snapshot_authority_source_binding_missing"


@pytest.mark.unit
@pytest.mark.pit
def test_snapshot_resolution_rejects_membership_source_drift() -> None:
    artifacts, request = _fixture()
    membership = pl.read_parquet(BytesIO(artifacts.payloads["membership-live"]))
    membership = membership.with_columns(
        pl.lit("future-source").alias("source_snapshot_id")
    )
    request = _replace_manifest_frame(
        artifacts,
        request,
        input_id="membership-live",
        frame=membership,
    )

    with pytest.raises(AppProcessError) as exc_info:
        IndexedSnapshotValidationAuthoritySource(artifacts).resolve(request)

    assert _reason(exc_info.value) == "snapshot_authority_membership_source_mismatch"
