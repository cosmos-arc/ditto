"""Risk models unit tests — RiskMetrics, ExposureData, DrawdownStats."""

from dataclasses import FrozenInstanceError

import pytest
from ditto_risk.models import (
    DrawdownStats,
    ExposureData,
    RiskMetrics,
)


def test_risk_metrics_is_frozen() -> None:
    metrics = RiskMetrics(
        max_drawdown=0.15,
        current_drawdown=0.08,
        sharpe_ratio=1.2,
        volatility=0.18,
    )
    with pytest.raises(FrozenInstanceError):
        metrics.max_drawdown = 0.0


def test_exposure_data_tracks_concentration() -> None:
    data = ExposureData(
        total_exposure=1.0,
        top1_weight=0.35,
        top5_weight=0.72,
        sector_count=8,
    )
    assert data.top1_weight == 0.35


def test_drawdown_stats_tracks_recovery() -> None:
    stats = DrawdownStats(
        max_drawdown=0.22,
        current_drawdown=0.05,
        peak_date="2026-01-15",
        trough_date="2026-03-01",
        recovery_days=45,
    )
    assert stats.recovery_days == 45
