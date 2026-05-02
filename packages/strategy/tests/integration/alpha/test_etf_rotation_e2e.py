"""E2E integration tests for etf_rotation strategy template.

测试完整 Pipeline:
  输入 -> Signal -> Score -> RiskLock -> Select -> TargetPortfolio
"""

from __future__ import annotations

import polars as pl
import pytest
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.pipeline import StrategyInputBundle, StrategyPipeline
from ditto_strategy.alpha.templates.etf_rotation import (
    ETFRotationConfig,
    build_etf_rotation_pipeline,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_bundle() -> StrategyInputBundle:
    """构造 12 个标的的测试用 StrategyInputBundle。"""
    ids = [f"ETF{i:03d}" for i in range(1, 13)]
    instruments = pl.DataFrame({"instrument_id": ids})

    market_data = pl.DataFrame(
        {
            "instrument_id": ids,
            "close": [float(i + 1) for i in range(12)],
            "open": [float(i + 1) for i in range(12)],
            "high": [float(i + 2) for i in range(12)],
            "low": [float(i) for i in range(12)],
            "volume": [1000000.0] * 12,
        },
    )

    # Signal values: ETF001=0.15, ETF002=0.12, ..., ETF012=-0.10 (decreasing)
    signal_values = pl.DataFrame(
        {
            "instrument_id": ids,
            "signal_value": [
                0.15,
                0.12,
                0.09,
                0.06,
                0.03,
                0.01,
                -0.01,
                -0.03,
                -0.04,
                -0.05,
                -0.07,
                -0.10,
            ],
        },
    )

    return StrategyInputBundle(
        trade_date="2026-01-15",
        strategy_id="test_etf_rotation",
        run_id="run_001",
        instruments=instruments,
        market_data=market_data,
        signal_values=signal_values,
    )


# ---------------------------------------------------------------------------
# E2E Tests
# ---------------------------------------------------------------------------


class TestETFRotationE2E:
    """端到端测试: 输入 -> Pipeline -> TargetPortfolio。"""

    def test_etf_rotation_recommendation(
        self,
        sample_bundle: StrategyInputBundle,
    ) -> None:
        """完整 E2E: 输入 -> Pipeline -> TargetPortfolio。"""
        config = ETFRotationConfig(top_k=5)
        stages = build_etf_rotation_pipeline(config)
        pipeline = StrategyPipeline(stages)
        context = StrategyContext()
        target = pipeline.run(context, sample_bundle)

        assert len(target.positions) == 5
        # Equal weight fallback (no AllocationStage): 1.0 / 5 = 0.2
        assert abs(sum(target.positions.values()) - 1.0) < 1e-9
        # ETF001-ETF005 should be selected (highest momentum)
        assert "ETF001" in target.positions
        assert "ETF005" in target.positions
        assert "ETF006" not in target.positions

    def test_risklock_filtering_in_pipeline(
        self,
        sample_bundle: StrategyInputBundle,
    ) -> None:
        """部分标的被 RiskLock 过滤。"""
        context = StrategyContext()
        context.lock_instrument("ETF001", "hit stop-loss")
        context.lock_instrument("ETF002", "hit stop-loss")

        config = ETFRotationConfig(top_k=5)
        stages = build_etf_rotation_pipeline(config)
        pipeline = StrategyPipeline(stages)
        target = pipeline.run(context, sample_bundle)

        assert "ETF001" not in target.positions
        assert "ETF002" not in target.positions
        assert len(target.positions) == 5
        assert "ETF003" in target.positions

    def test_all_locked_returns_empty(
        self,
        sample_bundle: StrategyInputBundle,
    ) -> None:
        """全部被 RiskLock 锁定。"""
        context = StrategyContext()
        for i in range(1, 13):
            context.lock_instrument(f"ETF{i:03d}", "market halt")

        config = ETFRotationConfig(top_k=5)
        stages = build_etf_rotation_pipeline(config)
        pipeline = StrategyPipeline(stages)
        target = pipeline.run(context, sample_bundle)

        assert len(target.positions) == 0

    def test_fewer_instruments_than_top_k(self) -> None:
        """标的数 < top_k。"""
        ids = ["ETF001", "ETF002", "ETF003"]
        instruments = pl.DataFrame({"instrument_id": ids})
        market_data = pl.DataFrame(
            {
                "instrument_id": ids,
                "close": [1.0, 2.0, 3.0],
                "open": [1.0, 2.0, 3.0],
                "high": [1.0, 2.0, 3.0],
                "low": [1.0, 2.0, 3.0],
                "volume": [1000.0, 1000.0, 1000.0],
            },
        )
        signal_values = pl.DataFrame(
            {
                "instrument_id": ids,
                "signal_value": [0.1, 0.2, 0.3],
            },
        )
        bundle = StrategyInputBundle(
            trade_date="2026-01-15",
            strategy_id="test",
            run_id="run_001",
            instruments=instruments,
            market_data=market_data,
            signal_values=signal_values,
        )

        config = ETFRotationConfig(top_k=10)
        stages = build_etf_rotation_pipeline(config)
        pipeline = StrategyPipeline(stages)
        context = StrategyContext()
        target = pipeline.run(context, bundle)

        assert len(target.positions) == 3
        assert abs(sum(target.positions.values()) - 1.0) < 1e-9

    def test_target_portfolio_metadata(
        self,
        sample_bundle: StrategyInputBundle,
    ) -> None:
        """TargetPortfolio 保留元数据。"""
        config = ETFRotationConfig(top_k=5)
        stages = build_etf_rotation_pipeline(config)
        pipeline = StrategyPipeline(stages)
        context = StrategyContext()
        target = pipeline.run(context, sample_bundle)

        assert target.trade_date == "2026-01-15"
        assert target.strategy_id == "test_etf_rotation"
        assert target.run_id == "run_001"
