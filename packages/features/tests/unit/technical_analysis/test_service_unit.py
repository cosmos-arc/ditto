"""Golden, boundary, and PIT-sentinel tests for technical analysis."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from ditto_features.technical_analysis.contracts import (
    TechnicalAnalysisInput,
    TechnicalAnalysisSnapshot,
    TechnicalAnalysisSpec,
    TechnicalBar,
    TechnicalIndicatorReading,
    TechnicalIndicatorStatus,
    TechnicalTimeframe,
)
from ditto_features.technical_analysis.registry import indicator_registry
from ditto_features.technical_analysis.service import TechnicalAnalysisService
from ditto_kernel.identity import InstrumentId


def _at(day: int) -> datetime:
    return datetime(2026, 8, day, 7, tzinfo=UTC)


def _spec(
    *, timeframes: tuple[TechnicalTimeframe, ...] | None = None
) -> TechnicalAnalysisSpec:
    return TechnicalAnalysisSpec(
        spec_id="technical-core",
        spec_version="1",
        algorithm_version="technical-analysis.v1",
        timeframes=timeframes or (TechnicalTimeframe.DAILY,),
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


def _bar(
    day: int,
    close: float,
    *,
    volume: float = 1_000.0,
    adjustment_factor: float = 1.0,
    suspended: bool = False,
    occurred_at: datetime | None = None,
) -> TechnicalBar:
    event_time = occurred_at or _at(day)
    return TechnicalBar(
        occurred_at=event_time,
        knowledge_at=event_time + timedelta(minutes=5),
        publication_at=event_time,
        source_snapshot_id="daily:sha256:a",
        open=close - 1.0,
        high=close + 2.0,
        low=close - 2.0,
        close=close,
        volume=volume,
        turnover=close * volume,
        adjustment_factor=adjustment_factor,
        suspended=suspended,
        benchmark_close=100.0 + day,
        industry_close=99.0 + day,
    )


def _input(
    bars: tuple[TechnicalBar, ...],
    *,
    spec: TechnicalAnalysisSpec | None = None,
) -> TechnicalAnalysisInput:
    return TechnicalAnalysisInput(
        instrument_id=InstrumentId(600519),
        instrument_name="贵州茅台",
        as_of=_at(7),
        knowledge_cutoff=_at(7),
        publication_cutoff=_at(7),
        source_snapshot_ids=("daily:sha256:a",),
        spec=spec or _spec(),
        bars=bars,
        selection_run_id="selection-run:sha256:a",
    )


def _readings(
    snapshot: TechnicalAnalysisSnapshot,
) -> dict[tuple[str, str], TechnicalIndicatorReading]:
    return {(item.timeframe.value, item.name): item for item in snapshot.readings}


def test_registry_is_closed_versioned_and_covers_the_v1_scope() -> None:
    definitions = indicator_registry()

    assert tuple(item.name for item in definitions) == (
        "return",
        "relative_return_benchmark",
        "relative_return_industry",
        "sma",
        "ema",
        "slope",
        "rsi",
        "macd",
        "macd_signal",
        "macd_histogram",
        "atr",
        "historical_volatility",
        "volume",
        "relative_volume",
        "turnover",
        "donchian_high",
        "donchian_low",
        "breakout",
    )
    assert {item.version for item in definitions} == {"1"}


def test_daily_indicator_values_match_independent_small_window_golden() -> None:
    bars = tuple(
        _bar(day, close, volume=volume)
        for day, close, volume in (
            (1, 100.0, 100.0),
            (2, 102.0, 200.0),
            (3, 101.0, 300.0),
            (4, 104.0, 400.0),
            (5, 106.0, 500.0),
            (6, 108.0, 600.0),
        )
    )

    snapshot = TechnicalAnalysisService().analyze(_input(bars))
    readings = _readings(snapshot)

    assert readings[("daily", "return")].value == pytest.approx(108 / 101 - 1)
    assert readings[("daily", "sma")].value == pytest.approx(106.0)
    assert readings[("daily", "ema")].value == pytest.approx(106.125)
    assert readings[("daily", "slope")].value == pytest.approx(2.0)
    assert readings[("daily", "rsi")].value == pytest.approx(100.0)
    assert readings[("daily", "relative_volume")].value == pytest.approx(1.5)
    assert readings[("daily", "donchian_high")].value == pytest.approx(108.0)
    assert readings[("daily", "breakout")].value == pytest.approx(0.0)
    assert snapshot.status == "ready"
    assert snapshot.levels
    assert snapshot.selection_run_id == "selection-run:sha256:a"


@pytest.mark.pit
def test_future_and_decision_row_sentinels_cannot_change_snapshot_values() -> None:
    visible = tuple(_bar(day, 100.0 + day) for day in range(1, 7))
    baseline = TechnicalAnalysisService().analyze(_input(visible))
    at_decision = _bar(7, 1_000_000.0, occurred_at=_at(7))
    future = _bar(8, 2_000_000.0, occurred_at=_at(8))

    with_sentinels = TechnicalAnalysisService().analyze(
        _input((*visible, at_decision, future))
    )

    assert with_sentinels.readings == baseline.readings
    assert with_sentinels.levels == baseline.levels
    assert with_sentinels.last_computed_bar_at == baseline.last_computed_bar_at


def test_warmup_suspension_and_adjustment_are_explicit_not_silent() -> None:
    sparse = TechnicalAnalysisService().analyze(_input((_bar(1, 100.0),)))
    sparse_readings = _readings(sparse)
    assert sparse.status == "blocked"
    assert (
        sparse_readings[("daily", "rsi")].status is TechnicalIndicatorStatus.WARMING_UP
    )
    assert sparse_readings[("daily", "rsi")].reason == "insufficient_history"

    bars = (
        _bar(1, 100.0, adjustment_factor=1.0),
        _bar(2, 50.0, adjustment_factor=2.0),
        _bar(3, 52.0, adjustment_factor=2.0),
        _bar(4, 9_999.0, suspended=True),
        _bar(5, 54.0, adjustment_factor=2.0),
        _bar(6, 55.0, adjustment_factor=2.0),
    )
    snapshot = TechnicalAnalysisService().analyze(_input(bars))

    assert "corporate_action_adjustment_applied" in snapshot.warnings
    assert "suspended_bar_excluded" in snapshot.warnings
    assert snapshot.last_computed_bar_at == _at(6)
    assert _readings(snapshot)[("daily", "return")].value == pytest.approx(
        110 / 100 - 1
    )


def test_daily_weekly_conflict_and_versioned_levels_are_deterministic() -> None:
    start = datetime(2026, 7, 6, 7, tzinfo=UTC)
    closes = (
        120.0,
        118.0,
        116.0,
        114.0,
        112.0,
        110.0,
        108.0,
        106.0,
        104.0,
        102.0,
        101.0,
        103.0,
        105.0,
        107.0,
        109.0,
        111.0,
        113.0,
        115.0,
        117.0,
        119.0,
    )
    bars = tuple(
        replace(
            _bar(1, close),
            occurred_at=start + timedelta(days=index),
            knowledge_at=start + timedelta(days=index, minutes=5),
            publication_at=start + timedelta(days=index),
        )
        for index, close in enumerate(closes)
    )
    request = replace(
        _input(
            bars,
            spec=_spec(
                timeframes=(TechnicalTimeframe.DAILY, TechnicalTimeframe.WEEKLY)
            ),
        ),
        as_of=datetime(2026, 7, 27, 7, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 7, 27, 7, tzinfo=UTC),
        publication_cutoff=datetime(2026, 7, 27, 7, tzinfo=UTC),
    )

    first = TechnicalAnalysisService().analyze(request)
    second = TechnicalAnalysisService().analyze(request)

    assert first == second
    assert {item.timeframe for item in first.timeframe_summaries} == {
        TechnicalTimeframe.DAILY,
        TechnicalTimeframe.WEEKLY,
    }
    assert first.conflicts
    assert all(
        item.algorithm_version == "support-resistance.v1" for item in first.levels
    )
