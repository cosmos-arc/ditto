"""Immutable snapshot-backed production validation authority tests."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date, timedelta
from io import BytesIO

import orjson
import polars as pl
import pytest
from ditto_application.builders.research_validation_authority_source import (
    IndexedSnapshotValidationAuthoritySource,
)
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
