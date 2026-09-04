"""Contracts for deterministic, content-addressed technical analysis."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from ditto_features.technical_analysis.contracts import (
    TechnicalAnalysisInput,
    TechnicalAnalysisSpec,
    TechnicalBar,
    TechnicalTimeframe,
    canonical_spec_hash,
)
from ditto_kernel.identity import InstrumentId


def _at(day: int) -> datetime:
    return datetime(2026, 8, day, 7, tzinfo=UTC)


def _spec() -> TechnicalAnalysisSpec:
    return TechnicalAnalysisSpec(
        spec_id="technical-core",
        spec_version="1",
        algorithm_version="technical-analysis.v1",
        timeframes=(TechnicalTimeframe.WEEKLY, TechnicalTimeframe.DAILY),
        return_window=3,
        trend_window=3,
        slope_window=3,
        rsi_window=3,
        macd_fast=2,
        macd_slow=3,
        macd_signal=2,
        atr_window=3,
        volatility_window=3,
        volume_window=3,
        donchian_window=3,
        support_resistance_window=5,
    )


def _bar(day: int, *, snapshot_id: str = "daily:sha256:a") -> TechnicalBar:
    occurred_at = _at(day)
    return TechnicalBar(
        occurred_at=occurred_at,
        knowledge_at=occurred_at + timedelta(minutes=5),
        publication_at=occurred_at,
        source_snapshot_id=snapshot_id,
        open=100.0,
        high=102.0,
        low=99.0,
        close=101.0,
        volume=1_000.0,
        turnover=100_000.0,
        adjustment_factor=1.0,
        suspended=False,
        benchmark_close=100.0,
        industry_close=100.0,
    )


def test_spec_identity_normalizes_timeframe_order_and_covers_parameters() -> None:
    spec = _spec()
    reordered = TechnicalAnalysisSpec(
        **{
            **spec.identity_payload(),
            "timeframes": (TechnicalTimeframe.DAILY, TechnicalTimeframe.WEEKLY),
        }
    )

    assert spec.timeframes == (
        TechnicalTimeframe.DAILY,
        TechnicalTimeframe.WEEKLY,
    )
    assert canonical_spec_hash(spec) == canonical_spec_hash(reordered)
    assert canonical_spec_hash(spec) != canonical_spec_hash(
        TechnicalAnalysisSpec(
            **{**spec.identity_payload(), "rsi_window": spec.rsi_window + 1}
        )
    )


def test_input_rejects_ambiguous_lineage_and_invalid_bar_values() -> None:
    with pytest.raises(ValueError, match="source snapshot"):
        TechnicalAnalysisInput(
            instrument_id=InstrumentId(600519),
            instrument_name="贵州茅台",
            as_of=_at(7),
            knowledge_cutoff=_at(7),
            publication_cutoff=_at(7),
            source_snapshot_ids=("daily:sha256:a",),
            spec=_spec(),
            bars=(_bar(1, snapshot_id="daily:sha256:undeclared"),),
        )

    with pytest.raises(ValueError, match="OHLC"):
        replace(_bar(1), high=98.0)


def test_input_is_immutable_and_requires_explicit_replay_boundaries() -> None:
    value = TechnicalAnalysisInput(
        instrument_id=InstrumentId(600519),
        instrument_name="贵州茅台",
        as_of=_at(7),
        knowledge_cutoff=_at(7),
        publication_cutoff=_at(7),
        source_snapshot_ids=("daily:sha256:a",),
        spec=_spec(),
        bars=(_bar(2), _bar(1)),
        selection_run_id="selection-run:sha256:a",
        research_case_id="research-case:sha256:b",
        portfolio_snapshot_id="portfolio:sha256:c",
    )

    assert tuple(bar.occurred_at for bar in value.bars) == (_at(1), _at(2))
    assert value.instrument_id == InstrumentId(600519)
