"""Selection evidence contracts and stage emission tests."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import FrozenInstanceError, fields
from importlib.util import find_spec
from math import inf, nan

import ditto_strategy.alpha.selection_evidence as evidence
import polars as pl
import pytest
from ditto_strategy.alpha.builtins.filtering import (
    FilterCondition,
    FilteringStage,
    RiskLockFilter,
    TrendFilterStage,
)
from ditto_strategy.alpha.builtins.selection import SelectionStage
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.selection_evidence import (
    ExclusionEvidence,
    ExclusionReason,
    FactorContributionEvidence,
    InitialUniverseEvidence,
    SelectionEvidence,
    SelectionEvidenceCollector,
    SelectionEvidenceLog,
    SelectionExposureApplicability,
    SelectionExposureDeclaration,
    SelectionExposureEvidence,
    SelectionExposureLane,
    SelectionExposurePolicy,
    SelectionExposureSizeBucket,
)
from ditto_strategy.errors import StrategySpecError
from polars.testing import assert_frame_equal

_TRADE_DATE = "2026-03-22"


def test_selection_evidence_module_exists() -> None:
    """R3 selection evidence must have a strategy-owned contract module."""
    assert find_spec("ditto_strategy.alpha.selection_evidence") is not None


def test_selection_evidence_contract_surface_is_explicit() -> None:
    """The module owns typed events, a narrow sink, and an immutable snapshot."""
    expected_names = {
        "ExclusionReason",
        "ExclusionEvidence",
        "FactorContributionEvidence",
        "InitialUniverseEvidence",
        "SelectionEvidence",
        "SelectionEvidenceCollector",
        "SelectionEvidenceLog",
        "SelectionEvidenceSink",
        "SelectionExposureApplicability",
        "SelectionExposureDeclaration",
        "SelectionExposureEvidence",
        "SelectionExposureLane",
        "SelectionExposurePolicy",
        "SelectionExposureSizeBucket",
    }

    assert expected_names <= set(evidence.__dict__)


def test_every_evidence_record_has_an_explicit_trade_date() -> None:
    """A reusable run collector must never infer rebalance dates later."""
    event_types = (
        InitialUniverseEvidence,
        ExclusionEvidence,
        FactorContributionEvidence,
        SelectionEvidence,
        SelectionExposureDeclaration,
        SelectionExposureEvidence,
    )

    for event_type in event_types:
        assert "trade_date" in {field.name for field in fields(event_type)}


def test_stock_exposure_policy_freezes_source_columns_and_bucket_semantics() -> None:
    policy = SelectionExposurePolicy.stock()

    assert policy.applicability is SelectionExposureApplicability.APPLICABLE
    assert policy.lane is SelectionExposureLane.STOCK_LANE
    assert policy.industry_column == "sector_id"
    assert policy.size_column == "market_cap"
    assert policy.size_bucket_method == "selected_market_cap_tertiles_v1"


def test_etf_exposure_policy_is_explicitly_not_applicable() -> None:
    policy = SelectionExposurePolicy.etf()

    assert policy.applicability is SelectionExposureApplicability.NOT_APPLICABLE
    assert policy.lane is SelectionExposureLane.ETF_LANE
    assert policy.industry_column is None
    assert policy.size_column is None
    assert policy.size_bucket_method is None


def test_log_rejects_exposure_without_same_date_applicable_declaration() -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        SelectionEvidenceLog(
            exposures=(
                SelectionExposureEvidence(
                    trade_date=_TRADE_DATE,
                    instrument_id=1,
                    selected_weight=1.0,
                    industry_id="bank",
                    size_value=50_000_000_000.0,
                    size_bucket=SelectionExposureSizeBucket.LARGE,
                ),
            ),
        )

    assert exc_info.value.details["reason"] == "exposure_declaration_missing"


def test_log_rejects_rows_for_not_applicable_etf_declaration() -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        SelectionEvidenceLog(
            exposure_declarations=(
                SelectionExposureDeclaration.from_policy(
                    _TRADE_DATE,
                    SelectionExposurePolicy.etf(),
                ),
            ),
            exposures=(
                SelectionExposureEvidence(
                    trade_date=_TRADE_DATE,
                    instrument_id="510300.SH",
                    selected_weight=1.0,
                    industry_id="ETF",
                    size_value=1.0,
                    size_bucket=SelectionExposureSizeBucket.LARGE,
                ),
            ),
        )

    assert exc_info.value.details["reason"] == "not_applicable_exposure_has_rows"


def test_factor_contribution_names_its_additive_score_scope() -> None:
    """Factor totals are not the later selector score produced by ScoringStage."""
    field_names = {field.name for field in fields(FactorContributionEvidence)}

    assert "factor_signal_score" in field_names
    assert "score" not in field_names


def test_exclusion_reason_values_are_stable_and_specific() -> None:
    assert {reason.value for reason in ExclusionReason} == {
        "missing_data",
        "insufficient_liquidity",
        "st_status",
        "suspended",
        "risk_locked",
        "trend_threshold",
        "condition_not_met",
        "below_top_k",
    }


def test_evidence_records_are_frozen() -> None:
    event = SelectionEvidence(
        trade_date=_TRADE_DATE,
        instrument_id=1,
        score=0.9,
        rank=1,
        selected=True,
    )

    with pytest.raises(FrozenInstanceError):
        event.rank = 2  # type: ignore[misc]


def test_log_defensively_copies_ordered_sequences() -> None:
    events = [
        InitialUniverseEvidence(
            trade_date=_TRADE_DATE,
            instrument_id=1,
            ordinal=1,
        ),
    ]
    log = SelectionEvidenceLog(initial_universe=events)  # type: ignore[arg-type]

    events.append(
        InitialUniverseEvidence(
            trade_date=_TRADE_DATE,
            instrument_id=2,
            ordinal=2,
        ),
    )

    assert log.initial_universe == (
        InitialUniverseEvidence(
            trade_date=_TRADE_DATE,
            instrument_id=1,
            ordinal=1,
        ),
    )


@pytest.mark.parametrize(
    "invalid_events",
    [
        "not-events",
        {
            InitialUniverseEvidence(
                trade_date=_TRADE_DATE,
                instrument_id=1,
                ordinal=1,
            ),
        },
        (
            event
            for event in (
                InitialUniverseEvidence(
                    trade_date=_TRADE_DATE,
                    instrument_id=1,
                    ordinal=1,
                ),
            )
        ),
    ],
    ids=("text", "unordered-set", "generator"),
)
def test_log_rejects_text_unordered_and_one_shot_iterables(
    invalid_events: object,
) -> None:
    with pytest.raises(TypeError, match="ordered sequence"):
        SelectionEvidenceLog(initial_universe=invalid_events)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_number", [True, nan, inf, -inf])
def test_factor_contribution_rejects_bool_and_non_finite_numbers(
    invalid_number: object,
) -> None:
    with pytest.raises((TypeError, ValueError), match="finite number"):
        FactorContributionEvidence(
            trade_date=_TRADE_DATE,
            instrument_id=1,
            factor_name="momentum",
            raw_value=invalid_number,  # type: ignore[arg-type]
            processed_value=0.5,
            normalized_value=0.75,
            weight=1.0,
            contribution=0.75,
            factor_signal_score=0.75,
        )


def test_collector_snapshot_enriches_factor_rows_with_selection_state() -> None:
    collector = SelectionEvidenceCollector()
    collector.begin_rebalance(_TRADE_DATE)
    collector.emit(
        InitialUniverseEvidence(
            trade_date=_TRADE_DATE,
            instrument_id="000001.SZ",
            ordinal=1,
        ),
    )
    collector.emit(
        FactorContributionEvidence(
            trade_date=_TRADE_DATE,
            instrument_id="000001.SZ",
            factor_name="momentum",
            raw_value=0.12,
            processed_value=1.25,
            normalized_value=1.0,
            weight=0.6,
            contribution=0.6,
            factor_signal_score=0.8,
        ),
    )
    collector.emit(
        SelectionEvidence(
            trade_date=_TRADE_DATE,
            instrument_id="000001.SZ",
            score=0.95,
            rank=1,
            selected=True,
        ),
    )
    collector.commit_rebalance()

    snapshot = collector.snapshot()

    assert snapshot.factor_contributions[0].rank == 1
    assert snapshot.factor_contributions[0].selected is True
    assert snapshot.factor_contributions[0].factor_signal_score == pytest.approx(0.8)


def test_collector_rejects_duplicate_selection_for_one_instrument_and_date() -> None:
    """Last-write-wins enrichment would silently corrupt duplicate rows."""
    collector = SelectionEvidenceCollector()
    collector.begin_rebalance(_TRADE_DATE)
    duplicate = SelectionEvidence(
        trade_date=_TRADE_DATE,
        instrument_id="000001.SZ",
        score=0.9,
        rank=1,
        selected=True,
    )
    collector.emit(duplicate)

    with pytest.raises(StrategySpecError, match="duplicate selection evidence"):
        collector.emit(duplicate)


def test_collector_emit_uses_constant_invariant_scan_count_at_scale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-event validation must not rescan the full committed event history."""
    scan_sizes: list[int] = []
    original_validator = evidence._validate_event_invariants

    def record_scan(events: Sequence[evidence.SelectionEvidenceEvent]) -> None:
        scan_sizes.append(len(events))
        original_validator(events)

    monkeypatch.setattr(evidence, "_validate_event_invariants", record_scan)
    collector = SelectionEvidenceCollector()
    collector.begin_rebalance(_TRADE_DATE)

    for instrument_id in range(2_000):
        collector.emit(
            InitialUniverseEvidence(
                trade_date=_TRADE_DATE,
                instrument_id=instrument_id,
                ordinal=instrument_id + 1,
            ),
        )

    assert scan_sizes == []
    collector.commit_rebalance()
    assert len(collector.snapshot().initial_universe) == 2_000
    assert scan_sizes == [2_000]


@pytest.mark.parametrize(
    "invalid_trade_date",
    ["", "20260322", "2026-3-22", "2026-02-30"],
)
def test_trade_date_must_be_a_strict_iso_calendar_date(
    invalid_trade_date: str,
) -> None:
    with pytest.raises(StrategySpecError, match="trade_date"):
        InitialUniverseEvidence(
            trade_date=invalid_trade_date,
            instrument_id=1,
            ordinal=1,
        )


def test_collector_rejects_unbound_and_mismatched_event_dates() -> None:
    event = InitialUniverseEvidence(
        trade_date=_TRADE_DATE,
        instrument_id=1,
        ordinal=1,
    )
    collector = SelectionEvidenceCollector()

    with pytest.raises(StrategySpecError, match="not bound"):
        collector.emit(event)

    collector.begin_rebalance("2026-03-23")
    with pytest.raises(StrategySpecError, match="does not match"):
        collector.emit(event)


def test_same_instrument_is_valid_across_dates_and_enriched_per_date() -> None:
    collector = SelectionEvidenceCollector()
    for trade_date, selected in (
        ("2026-03-22", True),
        ("2026-03-23", False),
    ):
        collector.begin_rebalance(trade_date)
        collector.emit(
            InitialUniverseEvidence(
                trade_date=trade_date,
                instrument_id=1,
                ordinal=1,
            ),
        )
        collector.emit(
            FactorContributionEvidence(
                trade_date=trade_date,
                instrument_id=1,
                factor_name="momentum",
                raw_value=1.0,
                processed_value=1.0,
                normalized_value=1.0,
                weight=1.0,
                contribution=1.0,
                factor_signal_score=1.0,
            ),
        )
        collector.emit(
            SelectionEvidence(
                trade_date=trade_date,
                instrument_id=1,
                score=1.0,
                rank=1,
                selected=selected,
            ),
        )
        collector.commit_rebalance()

    snapshot = collector.snapshot()

    assert [event.trade_date for event in snapshot.initial_universe] == [
        "2026-03-22",
        "2026-03-23",
    ]
    assert [event.selected for event in snapshot.factor_contributions] == [
        True,
        False,
    ]


def test_collector_rejects_duplicate_initial_universe_for_one_date() -> None:
    collector = SelectionEvidenceCollector()
    collector.begin_rebalance(_TRADE_DATE)
    initial = InitialUniverseEvidence(
        trade_date=_TRADE_DATE,
        instrument_id=1,
        ordinal=1,
    )
    collector.emit(initial)

    with pytest.raises(StrategySpecError, match="duplicate initial universe"):
        collector.emit(initial)


def test_pending_and_aborted_rebalance_is_never_published() -> None:
    collector = SelectionEvidenceCollector()
    collector.begin_rebalance(_TRADE_DATE)
    collector.emit(
        InitialUniverseEvidence(
            trade_date=_TRADE_DATE,
            instrument_id=1,
            ordinal=1,
        ),
    )

    assert collector.snapshot().initial_universe == ()

    collector.abort_rebalance()

    assert collector.snapshot().initial_universe == ()
    with pytest.raises(StrategySpecError) as exc_info:
        _ = collector.current_trade_date
    assert exc_info.value.details["reason"] == "evidence_rebalance_unbound"


def test_collector_lifecycle_misuse_fails_closed_with_typed_reasons() -> None:
    collector = SelectionEvidenceCollector()

    with pytest.raises(StrategySpecError) as commit_error:
        collector.commit_rebalance()
    assert commit_error.value.details["reason"] == "evidence_rebalance_unbound"

    collector.begin_rebalance(_TRADE_DATE)
    with pytest.raises(StrategySpecError) as begin_error:
        collector.begin_rebalance("2026-03-23")
    assert begin_error.value.details["reason"] == "evidence_rebalance_already_active"

    collector.abort_rebalance()
    with pytest.raises(StrategySpecError) as abort_error:
        collector.abort_rebalance()
    assert abort_error.value.details["reason"] == "evidence_rebalance_unbound"


def test_collector_pristine_state_covers_active_pending_and_committed_events() -> None:
    collector = SelectionEvidenceCollector()

    assert collector.is_pristine

    collector.begin_rebalance(_TRADE_DATE)
    assert not collector.is_pristine

    collector.emit(
        InitialUniverseEvidence(
            trade_date=_TRADE_DATE,
            instrument_id=1,
            ordinal=1,
        )
    )
    assert not collector.is_pristine

    collector.abort_rebalance()
    assert collector.is_pristine

    collector.begin_rebalance(_TRADE_DATE)
    collector.emit(
        InitialUniverseEvidence(
            trade_date=_TRADE_DATE,
            instrument_id=1,
            ordinal=1,
        )
    )
    collector.commit_rebalance()
    assert not collector.is_pristine


def test_collector_rejects_duplicate_exclusion_and_selected_contradiction() -> None:
    collector = SelectionEvidenceCollector()
    collector.begin_rebalance(_TRADE_DATE)
    exclusion = ExclusionEvidence(
        trade_date=_TRADE_DATE,
        instrument_id=1,
        stage="trend_filter",
        reason_code=ExclusionReason.TREND_THRESHOLD,
    )
    collector.emit(exclusion)

    with pytest.raises(StrategySpecError, match="duplicate exclusion evidence"):
        collector.emit(exclusion)

    selected_collector = SelectionEvidenceCollector()
    selected_collector.begin_rebalance(_TRADE_DATE)
    selected_collector.emit(
        SelectionEvidence(
            trade_date=_TRADE_DATE,
            instrument_id=1,
            score=1.0,
            rank=1,
            selected=True,
        ),
    )
    with pytest.raises(StrategySpecError, match="contradictory exclusion"):
        selected_collector.emit(exclusion)


def test_exclusion_message_is_display_only_and_reason_is_typed() -> None:
    event = ExclusionEvidence(
        trade_date=_TRADE_DATE,
        instrument_id=1,
        stage="liquidity",
        reason_code=ExclusionReason.INSUFFICIENT_LIQUIDITY,
        message="成交额低于策略阈值",
    )

    assert event.reason_code is ExclusionReason.INSUFFICIENT_LIQUIDITY
    assert event.message == "成交额低于策略阈值"


def test_filtering_records_each_instruments_first_specific_exclusion() -> None:
    collector = SelectionEvidenceCollector()
    collector.begin_rebalance(_TRADE_DATE)
    stage = FilteringStage(
        conditions=(
            FilterCondition(
                name="liquidity",
                column="amount",
                min_value=1_000_000.0,
                reason_code=ExclusionReason.INSUFFICIENT_LIQUIDITY,
            ),
            FilterCondition(
                name="st_status",
                column="is_st",
                max_value=0.0,
                reason_code=ExclusionReason.ST_STATUS,
            ),
            FilterCondition(
                name="suspension",
                column="is_suspended",
                max_value=0.0,
                reason_code=ExclusionReason.SUSPENDED,
            ),
        ),
        evidence_sink=collector,
    )
    frame = pl.DataFrame(
        {
            "instrument_id": ["PASS", "MISSING", "ILLIQUID", "ST", "SUSPENDED"],
            "amount": [2_000_000.0, None, 10_000.0, 2_000_000.0, 2_000_000.0],
            "is_st": [0, 0, 1, 1, 0],
            "is_suspended": [0, 0, 1, 1, 1],
        },
    )

    result = stage.process(frame, StrategyContext())
    collector.commit_rebalance()
    exclusions = collector.snapshot().exclusions

    assert result["instrument_id"].to_list() == ["PASS"]
    actual_exclusions = [
        (item.instrument_id, item.stage, item.reason_code) for item in exclusions
    ]
    assert actual_exclusions == [
        ("MISSING", "liquidity", ExclusionReason.MISSING_DATA),
        ("ILLIQUID", "liquidity", ExclusionReason.INSUFFICIENT_LIQUIDITY),
        ("ST", "st_status", ExclusionReason.ST_STATUS),
        ("SUSPENDED", "suspension", ExclusionReason.SUSPENDED),
    ]


def test_selection_emits_top_k_state_without_changing_tie_order() -> None:
    frame = pl.DataFrame(
        {
            "instrument_id": ["FIRST_TIE", "SECOND_TIE", "LOW"],
            "score": [0.9, 0.9, 0.7],
        },
    )
    expected = SelectionStage(top_k=2).process(frame, StrategyContext())
    collector = SelectionEvidenceCollector()
    collector.begin_rebalance(_TRADE_DATE)

    actual = SelectionStage(top_k=2, evidence_sink=collector).process(
        frame,
        StrategyContext(),
    )
    collector.commit_rebalance()

    assert_frame_equal(actual, expected)
    assert actual["instrument_id"].to_list() == ["FIRST_TIE", "SECOND_TIE"]
    assert [
        (item.instrument_id, item.score, item.rank, item.selected)
        for item in collector.snapshot().selections
    ] == [
        ("FIRST_TIE", 0.9, 1, True),
        ("SECOND_TIE", 0.9, 2, True),
        ("LOW", 0.7, 3, False),
    ]
    assert [item.instrument_id for item in collector.snapshot().exclusions] == ["LOW"]
    assert collector.snapshot().exclusions[0].reason_code is ExclusionReason.BELOW_TOP_K


def test_trend_and_risk_filters_emit_missing_threshold_and_lock_reasons() -> None:
    collector = SelectionEvidenceCollector()
    collector.begin_rebalance(_TRADE_DATE)
    context = StrategyContext()
    context.lock_instrument("LOCKED", "operator_lock")
    frame = pl.DataFrame(
        {
            "instrument_id": ["PASS", "MISSING", "LOW", "LOCKED"],
            "signal_value": [0.8, None, 0.1, 0.9],
        },
    )

    after_trend = TrendFilterStage(
        threshold=0.5,
        evidence_sink=collector,
    ).process(frame, context)
    result = RiskLockFilter(evidence_sink=collector).process(after_trend, context)
    collector.commit_rebalance()

    assert result["instrument_id"].to_list() == ["PASS"]
    assert [item.reason_code for item in collector.snapshot().exclusions] == [
        ExclusionReason.MISSING_DATA,
        ExclusionReason.TREND_THRESHOLD,
        ExclusionReason.RISK_LOCKED,
    ]


class _FailingSink:
    def begin_rebalance(self, trade_date: str) -> None:
        pass

    def commit_rebalance(self) -> None:
        pass

    def abort_rebalance(self) -> None:
        pass

    @property
    def current_trade_date(self) -> str:
        return _TRADE_DATE

    def emit(self, event: object) -> None:
        raise RuntimeError("evidence sink unavailable")


def test_stage_does_not_swallow_evidence_sink_failures() -> None:
    frame = pl.DataFrame({"instrument_id": [1], "score": [0.5]})

    with pytest.raises(RuntimeError, match="evidence sink unavailable"):
        SelectionStage(top_k=1, evidence_sink=_FailingSink()).process(
            frame,
            StrategyContext(),
        )
