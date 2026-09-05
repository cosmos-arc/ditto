"""Fail-closed validation edges for technical-analysis replay contracts."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from ditto_features.technical_analysis.contracts import (
    TechnicalAnalysisInput,
    TechnicalAnalysisSpec,
    TechnicalBar,
    TechnicalTimeframe,
)
from ditto_kernel.identity import InstrumentId


def _at(day: int) -> datetime:
    return datetime(2026, 8, day, 7, tzinfo=UTC)


def _spec(**overrides: Any) -> TechnicalAnalysisSpec:
    values: dict[str, object] = {
        "spec_id": "technical-core",
        "spec_version": "1",
        "algorithm_version": "technical-analysis.v1",
        "timeframes": (TechnicalTimeframe.DAILY,),
        "return_window": 3,
        "trend_window": 3,
        "slope_window": 3,
        "rsi_window": 3,
        "macd_fast": 2,
        "macd_slow": 3,
        "macd_signal": 2,
        "atr_window": 3,
        "volatility_window": 3,
        "volume_window": 3,
        "donchian_window": 3,
        "support_resistance_window": 5,
    }
    values.update(overrides)
    return TechnicalAnalysisSpec(**cast(Any, values))


def _bar(day: int, **overrides: Any) -> TechnicalBar:
    occurred_at = _at(day)
    values: dict[str, object] = {
        "occurred_at": occurred_at,
        "knowledge_at": occurred_at + timedelta(minutes=5),
        "publication_at": occurred_at,
        "source_snapshot_id": "daily:sha256:a",
        "open": 100.0,
        "high": 102.0,
        "low": 99.0,
        "close": 101.0,
        "volume": 1_000.0,
        "turnover": 100_000.0,
        "adjustment_factor": 1.0,
        "suspended": False,
        "benchmark_close": 100.0,
        "industry_close": 100.0,
    }
    values.update(overrides)
    return TechnicalBar(**cast(Any, values))


def _input(**overrides: Any) -> TechnicalAnalysisInput:
    values: dict[str, object] = {
        "instrument_id": InstrumentId(600519),
        "instrument_name": "贵州茅台",
        "as_of": _at(7),
        "knowledge_cutoff": _at(7),
        "publication_cutoff": _at(7),
        "source_snapshot_ids": ("daily:sha256:a",),
        "spec": _spec(),
        "bars": (_bar(1),),
    }
    values.update(overrides)
    return TechnicalAnalysisInput(**cast(Any, values))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"spec_id": " technical-core"}, "normalized text"),
        ({"algorithm_version": "technical-analysis.v2"}, "unsupported"),
        ({"timeframes": ()}, "requires supported timeframes"),
        (
            {"timeframes": (TechnicalTimeframe.DAILY, TechnicalTimeframe.DAILY)},
            "timeframes must be unique",
        ),
        ({"return_window": cast(int, True)}, "positive integer"),
        ({"macd_fast": 3, "macd_slow": 3}, "fast window must be smaller"),
        ({"slope_window": 1}, "slope window must be at least two"),
    ],
)
def test_spec_rejects_incomplete_or_ambiguous_algorithm_parameters(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _spec(**overrides)


def test_bar_rejects_naive_source_clock() -> None:
    with pytest.raises(ValueError, match="occurred_at must be timezone-aware"):
        _bar(1, occurred_at=datetime(2026, 8, 1, 7))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"open": cast(float, True)}, "open must be numeric"),
        ({"volume": float("inf")}, "volume is invalid"),
        ({"adjustment_factor": 0.0}, "adjustment_factor must be positive"),
        ({"suspended": cast(bool, 1)}, "suspended must be boolean"),
        ({"benchmark_close": 0.0}, "benchmark_close must be positive"),
    ],
)
def test_bar_rejects_non_replayable_numeric_values(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _bar(1, **overrides)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"publication_cutoff": _at(7) + timedelta(seconds=1)},
            "publication cutoff exceeds knowledge",
        ),
        (
            {"knowledge_cutoff": _at(7) + timedelta(seconds=1)},
            "knowledge cutoff exceeds decision time",
        ),
        ({"source_snapshot_ids": ()}, "unique source snapshot IDs"),
        (
            {"source_snapshot_ids": ("daily:sha256:a", "daily:sha256:a")},
            "unique source snapshot IDs",
        ),
        ({"bars": (_bar(1), replace(_bar(1), close=100.5))}, "unique occurrence"),
    ],
)
def test_input_rejects_ambiguous_temporal_or_lineage_boundaries(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _input(**overrides)
