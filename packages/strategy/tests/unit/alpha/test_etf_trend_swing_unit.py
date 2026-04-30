"""Tests for etf_trend_swing template: TrailingStopStage, Config, pipeline.

Covers TrailingStopStage, ETFTrendSwingConfig, and
build_etf_trend_swing_pipeline.
"""

from __future__ import annotations

import polars as pl
import pytest
from ditto_portfolio.rebalancing.allocation import (
    AllocationStage,
    InverseVolAllocator,
)
from ditto_strategy.alpha.builtins.filtering import (
    RiskLockFilter,
    TrendFilterStage,
)
from ditto_strategy.alpha.builtins.regime import RegimeConfig, TrendIndicator
from ditto_strategy.alpha.builtins.regime_allocation import RegimeAwareAllocationStage
from ditto_strategy.alpha.builtins.regime_scoring import RegimeScoringStep
from ditto_strategy.alpha.builtins.scoring import ScoringStage
from ditto_strategy.alpha.builtins.selection import SelectionStage
from ditto_strategy.alpha.builtins.signal import SignalStage
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.pipeline import StrategyInputBundle
from ditto_strategy.alpha.templates.etf_trend_swing import (
    ETFTrendSwingConfig,
    TrailingStopStage,
    build_etf_trend_swing_pipeline,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_context() -> StrategyContext:
    return StrategyContext()


@pytest.fixture
def context_with_positions() -> StrategyContext:
    """带持仓成本的上下文。"""
    return StrategyContext(
        positions={1: 0.80, 2: 4.10},
    )


@pytest.fixture
def allocated_frame() -> pl.DataFrame:
    """已分配权重的 DecisionFrame（TrailingStop 输入）。"""
    return pl.DataFrame(
        {
            "instrument_id": [1, 2, 3],
            "close": [0.76, 4.25, 1.50],
            "weight": [0.333, 0.333, 0.333],
        }
    )


# ---------------------------------------------------------------------------
# ETFTrendSwingConfig
# ---------------------------------------------------------------------------


class TestETFTrendSwingConfig:
    def test_default_values(self) -> None:
        """默认配置值正确。"""
        config = ETFTrendSwingConfig()
        assert config.lookback_window == 20
        assert config.trend_threshold == 0.0
        assert config.trailing_stop_pct == 0.08
        assert config.max_positions == 10
        assert config.scoring_method == "rank"
        assert config.scoring_ascending is True
        assert config.allocation_method == "equal_weight"
        assert config.cash_target == 0.0
        assert config.signal_column == "signal_value"

    def test_frozen(self) -> None:
        """Config 是 frozen dataclass，不可变。"""
        config = ETFTrendSwingConfig()
        with pytest.raises(AttributeError):
            config.trailing_stop_pct = 0.20  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TrailingStopStage
# ---------------------------------------------------------------------------


class TestTrailingStopStage:
    def test_no_positions_returns_as_is(
        self,
        empty_context: StrategyContext,
        allocated_frame: pl.DataFrame,
    ) -> None:
        """无持仓时原样返回。"""
        stage = TrailingStopStage(trailing_stop_pct=0.10)
        result = stage.process(allocated_frame, empty_context)
        assert result.equals(allocated_frame)

    def test_no_stop_triggered(
        self,
        context_with_positions: StrategyContext,
    ) -> None:
        """价格在止损线上方，不触发止损。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "close": [0.79, 4.00],
                "weight": [0.5, 0.5],
            }
        )
        # stop for 159915.SZ: 0.80 * (1 - 0.10) = 0.72; current 0.79 > 0.72 -> ok
        # stop for 510300.SH: 4.10 * (1 - 0.10) = 3.69; current 4.00 > 3.69 -> ok
        stage = TrailingStopStage(trailing_stop_pct=0.10)
        result = stage.process(frame, context_with_positions)
        assert result["weight"].to_list() == [0.5, 0.5]

    def test_stop_triggered_zeros_weight(
        self,
        context_with_positions: StrategyContext,
    ) -> None:
        """价格跌破止损线时权重归零。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "close": [0.70, 4.25],
                "weight": [0.5, 0.5],
            }
        )
        # stop for 159915.SZ: 0.80 * (1 - 0.10) = 0.72; current 0.70 < 0.72 -> triggered
        stage = TrailingStopStage(trailing_stop_pct=0.10)
        result = stage.process(frame, context_with_positions)
        weights = dict(
            zip(
                result["instrument_id"].to_list(),
                result["weight"].to_list(),
                strict=True,
            ),
        )
        assert weights[1] == 0.0
        assert weights[2] == 0.5

    def test_stop_triggered_adds_reason_codes(
        self,
        context_with_positions: StrategyContext,
    ) -> None:
        """止损触发时添加 trailing_stop reason_codes。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "close": [0.70, 4.25],
                "weight": [0.5, 0.5],
            }
        )
        stage = TrailingStopStage(trailing_stop_pct=0.10)
        result = stage.process(frame, context_with_positions)
        assert "reason_codes" in result.columns

        codes_map = dict(
            zip(
                result["instrument_id"].to_list(),
                result["reason_codes"].to_list(),
                strict=True,
            ),
        )
        assert "trailing_stop" in codes_map[1]
        # 2 not triggered, should have null reason_codes
        assert codes_map[2] is None

    def test_position_not_in_frame_ignored(
        self,
        context_with_positions: StrategyContext,
    ) -> None:
        """持仓标的不在 frame 中时被忽略。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [3],
                "close": [1.50],
                "weight": [1.0],
            }
        )
        stage = TrailingStopStage(trailing_stop_pct=0.10)
        result = stage.process(frame, context_with_positions)
        assert result["weight"][0] == 1.0

    def test_no_price_column_returns_as_is(
        self,
        context_with_positions: StrategyContext,
    ) -> None:
        """frame 中无价格列时原样返回。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "weight": [0.5, 0.5],
            }
        )
        stage = TrailingStopStage(trailing_stop_pct=0.10)
        result = stage.process(frame, context_with_positions)
        assert result["weight"].to_list() == [0.5, 0.5]

    def test_empty_frame_no_error(
        self,
        context_with_positions: StrategyContext,
    ) -> None:
        """空 frame 不报错。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [],
                "close": [],
                "weight": [],
            },
            schema={
                "instrument_id": pl.Int64,
                "close": pl.Float64,
                "weight": pl.Float64,
            },
        )
        stage = TrailingStopStage(trailing_stop_pct=0.10)
        result = stage.process(frame, context_with_positions)
        assert result.is_empty()

    def test_multiple_triggered(
        self,
        context_with_positions: StrategyContext,
    ) -> None:
        """多个持仓同时触发止损。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "close": [0.70, 3.50],
                "weight": [0.5, 0.5],
            }
        )
        # 159915.SZ: 0.80 * 0.90 = 0.72; current 0.70 < 0.72 -> triggered
        # 510300.SH: 4.10 * 0.90 = 3.69; current 3.50 < 3.69 -> triggered
        stage = TrailingStopStage(trailing_stop_pct=0.10)
        result = stage.process(frame, context_with_positions)
        assert result["weight"].to_list() == [0.0, 0.0]

    def test_frozen(self) -> None:
        """TrailingStopStage 是 frozen dataclass。"""
        stage = TrailingStopStage(trailing_stop_pct=0.10)
        with pytest.raises(AttributeError):
            stage.trailing_stop_pct = 0.20  # type: ignore[misc]


# ---------------------------------------------------------------------------
# build_etf_trend_swing_pipeline
# ---------------------------------------------------------------------------


class TestBuildETFTrendSwingPipeline:
    def test_default_config_builds_pipeline(self) -> None:
        """默认配置构建合法 Pipeline。"""
        config = ETFTrendSwingConfig()
        pipeline = build_etf_trend_swing_pipeline(config)
        assert pipeline is not None
        # Signal + TrendFilter + Score + RiskLock + Select + Allocate + TrailingStop
        assert len(pipeline._stages) == 7

    def test_pipeline_stage_order(self) -> None:
        """Pipeline 阶段顺序正确。"""
        config = ETFTrendSwingConfig()
        pipeline = build_etf_trend_swing_pipeline(config)
        stages = pipeline._stages
        assert isinstance(stages[0], SignalStage)
        assert isinstance(stages[1], TrendFilterStage)
        assert isinstance(stages[2], ScoringStage)
        assert isinstance(stages[3], RiskLockFilter)
        assert isinstance(stages[4], SelectionStage)
        assert isinstance(stages[5], AllocationStage)
        assert isinstance(stages[6], TrailingStopStage)

    def test_inverse_vol_allocation(self) -> None:
        """inverse_vol 分配方式正确使用 InverseVolAllocator。"""
        config = ETFTrendSwingConfig(
            allocation_method="inverse_vol",
            cash_target=0.1,
        )
        pipeline = build_etf_trend_swing_pipeline(config)
        allocation = pipeline._stages[5]
        assert isinstance(allocation, AllocationStage)
        assert isinstance(allocation.allocator, InverseVolAllocator)
        assert allocation.allocator.cash_target == 0.1

    def test_trailing_stop_stage_present(self) -> None:
        """默认配置包含 TrailingStopStage。"""
        config = ETFTrendSwingConfig()
        pipeline = build_etf_trend_swing_pipeline(config)
        assert any(isinstance(s, TrailingStopStage) for s in pipeline._stages)

    def test_trailing_stop_disabled_when_zero(self) -> None:
        """trailing_stop_pct=0 时不添加 TrailingStopStage。"""
        config = ETFTrendSwingConfig(trailing_stop_pct=0.0)
        pipeline = build_etf_trend_swing_pipeline(config)
        assert not any(isinstance(s, TrailingStopStage) for s in pipeline._stages)
        # Should be 6 stages instead of 7
        assert len(pipeline._stages) == 6

    def test_pipeline_run_e2e(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """端到端运行 Pipeline 并验证 TargetPortfolio。"""
        ids = [20, 21, 22]
        instruments = pl.DataFrame({"instrument_id": ids})
        market_data = pl.DataFrame(
            {
                "instrument_id": ids,
                "close": [1.0, 2.0, 3.0],
                "open": [1.0, 2.0, 3.0],
                "high": [1.1, 2.1, 3.1],
                "low": [0.9, 1.9, 2.9],
                "volume": [1000000.0, 1000000.0, 1000000.0],
            }
        )
        signal_values = pl.DataFrame(
            {
                "instrument_id": ids,
                "signal_value": [0.15, 0.10, -0.05],
            }
        )

        bundle = StrategyInputBundle(
            trade_date="2026-03-22",
            strategy_id="test_trend_swing",
            run_id="run_001",
            instruments=instruments,
            market_data=market_data,
            signal_values=signal_values,
        )

        config = ETFTrendSwingConfig(
            max_positions=2,
            trend_threshold=0.0,
            trailing_stop_pct=0.0,  # disable trailing stop for e2e
        )
        pipeline = build_etf_trend_swing_pipeline(config)
        target = pipeline.run(empty_context, bundle)

        # ETF003 has negative signal, filtered by TrendFilter (long, threshold=0)
        assert len(target.positions) == 2
        assert 20 in target.positions
        assert 21 in target.positions
        # Equal weight: 1.0 / 2 = 0.5
        assert target.positions[20] == pytest.approx(0.5)
        assert target.positions[21] == pytest.approx(0.5)

    def test_regime_config_inserts_scoring_step(
        self,
    ) -> None:
        """有 regime_config 时 Pipeline 包含 RegimeScoringStep 和 RegimeAware."""
        regime_config = RegimeConfig(
            indicators=(TrendIndicator(threshold=0.01),),
        )
        config = ETFTrendSwingConfig(
            max_positions=2,
            trailing_stop_pct=0.0,
            regime_config=regime_config,
        )
        pipeline = build_etf_trend_swing_pipeline(config)

        assert any(isinstance(s, RegimeScoringStep) for s in pipeline._stages)
        assert any(isinstance(s, RegimeAwareAllocationStage) for s in pipeline._stages)

        # RegimeScoringStep 应在 RegimeAwareAllocationStage 之前
        scoring_idx = next(
            i
            for i, s in enumerate(pipeline._stages)
            if isinstance(s, RegimeScoringStep)
        )
        aware_idx = next(
            i
            for i, s in enumerate(pipeline._stages)
            if isinstance(s, RegimeAwareAllocationStage)
        )
        assert scoring_idx < aware_idx
