"""Tests for stock_selection_trend strategy template.

Covers StockSelectionTrendConfig, validate_config, get_param_constraints,
MultiFactorSignalStage, build_stock_selection_trend_pipeline, E2E pipeline,
and EngineConfig rebalance_freq.
"""

from __future__ import annotations

import polars as pl
import pytest
from ditto_engine.alpha.builtins.filtering import (
    RiskLockFilter,
    TrendFilterStage,
)
from ditto_engine.alpha.builtins.regime import RegimeConfig, TrendIndicator
from ditto_engine.alpha.builtins.regime_allocation import RegimeAwareAllocationStage
from ditto_engine.alpha.builtins.regime_scoring import RegimeScoringStep
from ditto_engine.alpha.builtins.scoring import ScoringStage
from ditto_engine.alpha.builtins.selection import SelectionStage
from ditto_engine.alpha.context import StrategyContext
from ditto_engine.alpha.pipeline import StrategyInputBundle
from ditto_engine.alpha.specs import ParamConstraint
from ditto_engine.alpha.templates.stock_selection_trend import (
    MultiFactorSignalStage,
    StockSelectionTrendConfig,
    build_stock_selection_trend_pipeline,
    get_param_constraints,
    validate_config,
)
from ditto_engine.backtest.engine import EngineConfig, EngineLoop, EngineOptions
from ditto_engine.portfolio.allocation import (
    AllocationStage,
    EqualWeightAllocator,
    InverseVolAllocator,
)
from ditto_engine.portfolio.constraints import (
    ConstraintChecker,
    ConstraintStage,
    MaxWeightConstraint,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_context() -> StrategyContext:
    return StrategyContext()


@pytest.fixture
def multi_factor_bundle() -> StrategyInputBundle:
    """5 instruments with two factor columns."""
    ids = [f"STK{i:03d}" for i in range(1, 6)]
    instruments = pl.DataFrame({"instrument_id": ids})
    market_data = pl.DataFrame(
        {
            "instrument_id": ids,
            "close": [10.0, 20.0, 30.0, 40.0, 50.0],
            "open": [10.0, 20.0, 30.0, 40.0, 50.0],
            "high": [10.5, 20.5, 30.5, 40.5, 50.5],
            "low": [9.5, 19.5, 29.5, 39.5, 49.5],
            "volume": [1_000_000.0] * 5,
        },
    )
    signal_values = pl.DataFrame(
        {
            "instrument_id": ids,
            "momentum": [0.15, 0.12, 0.08, 0.05, -0.02],
            "volatility": [0.10, 0.20, 0.30, 0.40, 0.50],
        },
    )
    return StrategyInputBundle(
        trade_date="2026-03-22",
        strategy_id="test_stock_selection_trend",
        run_id="run_001",
        instruments=instruments,
        market_data=market_data,
        signal_values=signal_values,
    )


# ---------------------------------------------------------------------------
# StockSelectionTrendConfig
# ---------------------------------------------------------------------------


class TestStockSelectionTrendConfig:
    def test_default_values(self) -> None:
        """默认配置值正确。"""
        config = StockSelectionTrendConfig()
        assert config.universe_filter == ""
        assert config.signal_factors == ("signal_value",)
        assert config.signal_weights == (1.0,)
        assert config.top_k == 10
        assert config.max_weight == 0.15
        assert config.allocation_method == "equal_weight"
        assert config.cash_target == 0.0
        assert config.trend_threshold == 0.0
        assert config.rebalance_freq == "daily"

    def test_frozen(self) -> None:
        """Config 是 frozen dataclass，不可变。"""
        config = StockSelectionTrendConfig()
        with pytest.raises(AttributeError):
            config.top_k = 20  # type: ignore[misc]


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


class TestValidateConfig:
    def test_valid_config_passes(self) -> None:
        """合法配置不抛异常。"""
        config = StockSelectionTrendConfig()
        validate_config(config)  # Should not raise

    def test_mismatched_factors_and_weights_raises(self) -> None:
        """signal_factors 与 signal_weights 长度不一致时抛异常。"""
        config = StockSelectionTrendConfig(
            signal_factors=("momentum", "volatility"),
            signal_weights=(1.0,),
        )
        with pytest.raises(ValueError, match="same length"):
            validate_config(config)

    def test_invalid_top_k_raises(self) -> None:
        """top_k < 1 时抛异常。"""
        config = StockSelectionTrendConfig(top_k=0)
        with pytest.raises(ValueError, match="top_k"):
            validate_config(config)

    def test_invalid_max_weight_zero_raises(self) -> None:
        """max_weight <= 0 时抛异常。"""
        config = StockSelectionTrendConfig(max_weight=0.0)
        with pytest.raises(ValueError, match="max_weight"):
            validate_config(config)

    def test_invalid_max_weight_over_one_raises(self) -> None:
        """max_weight > 1 时抛异常。"""
        config = StockSelectionTrendConfig(max_weight=1.5)
        with pytest.raises(ValueError, match="max_weight"):
            validate_config(config)

    def test_invalid_allocation_method_raises(self) -> None:
        """非法 allocation_method 抛异常。"""
        config = StockSelectionTrendConfig(allocation_method="invalid")
        with pytest.raises(ValueError, match="allocation_method"):
            validate_config(config)

    def test_invalid_rebalance_freq_raises(self) -> None:
        """非法 rebalance_freq 抛异常。"""
        config = StockSelectionTrendConfig(rebalance_freq="quarterly")
        with pytest.raises(ValueError, match="rebalance_freq"):
            validate_config(config)


# ---------------------------------------------------------------------------
# get_param_constraints
# ---------------------------------------------------------------------------


class TestGetParamConstraints:
    def test_returns_constraints(self) -> None:
        """返回非空的 ParamConstraint 元组。"""
        constraints = get_param_constraints()
        assert isinstance(constraints, tuple)
        assert len(constraints) > 0
        for c in constraints:
            assert isinstance(c, ParamConstraint)


# ---------------------------------------------------------------------------
# MultiFactorSignalStage
# ---------------------------------------------------------------------------


class TestMultiFactorSignalStage:
    def test_single_factor(self, empty_context: StrategyContext) -> None:
        """单因子、单权重 — output_column 的值等于该因子的 rank 百分位。"""
        frame = pl.DataFrame(
            {
                "instrument_id": ["A", "B", "C"],
                "signal_value": [10.0, 20.0, 30.0],
            },
        )
        stage = MultiFactorSignalStage(
            signal_factors=("signal_value",),
            signal_weights=(1.0,),
            output_column="signal_value",
        )
        result = stage.process(frame, empty_context)
        values = result["signal_value"].to_list()
        # rank: 10→1, 20→2, 30→3 → percentiles: 1/3, 2/3, 3/3
        assert values == pytest.approx([1.0 / 3.0, 2.0 / 3.0, 3.0 / 3.0])

    def test_two_factors_weighted(self, empty_context: StrategyContext) -> None:
        """双因子加权 — 验证加权求和并归一化。"""
        frame = pl.DataFrame(
            {
                "instrument_id": ["A", "B", "C"],
                "momentum": [10.0, 20.0, 30.0],
                "volatility": [30.0, 20.0, 10.0],
            },
        )
        stage = MultiFactorSignalStage(
            signal_factors=("momentum", "volatility"),
            signal_weights=(0.6, 0.4),
            output_column="signal_value",
        )
        result = stage.process(frame, empty_context)
        values = result["signal_value"].to_list()

        # momentum ranks (descending=False): 10→1, 20→2, 30→3 → pcts: 1/3, 2/3, 3/3
        # volatility ranks (descending=False): 30→3, 20→2, 10→1 → pcts: 3/3, 2/3, 1/3
        # A: 0.6*(1/3) + 0.4*(3/3) = 0.2 + 0.4 = 0.6
        # B: 0.6*(2/3) + 0.4*(2/3) = 0.4 + 0.2667 = 0.6667
        # C: 0.6*(3/3) + 0.4*(1/3) = 0.6 + 0.1333 = 0.7333
        # weight_sum = 0.6 + 0.4 = 1.0, so no normalization needed
        assert values[0] == pytest.approx(0.6)
        assert values[1] == pytest.approx(2.0 / 3.0)
        assert values[2] == pytest.approx(0.7333, rel=1e-3)

    def test_empty_frame_returns_zero(self, empty_context: StrategyContext) -> None:
        """空 frame 返回空 frame + signal_value 列。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [],
                "momentum": [],
            },
            schema={"instrument_id": pl.Utf8, "momentum": pl.Float64},
        )
        stage = MultiFactorSignalStage(
            signal_factors=("momentum",),
            signal_weights=(1.0,),
            output_column="signal_value",
        )
        result = stage.process(frame, empty_context)
        assert result.is_empty()
        assert "signal_value" in result.columns

    def test_missing_factor_column_treated_as_zero(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """缺失因子列按 rank=0 处理。"""
        frame = pl.DataFrame(
            {
                "instrument_id": ["A", "B", "C"],
                "momentum": [10.0, 20.0, 30.0],
            },
        )
        # "volatility" is missing from frame
        stage = MultiFactorSignalStage(
            signal_factors=("momentum", "volatility"),
            signal_weights=(0.6, 0.4),
            output_column="signal_value",
        )
        result = stage.process(frame, empty_context)
        values = result["signal_value"].to_list()

        # momentum ranks: 1/3, 2/3, 3/3
        # volatility: all missing → rank=0 for each
        # A: (0.6*(1/3) + 0.4*0) / 1.0 = 0.2
        # B: (0.6*(2/3) + 0.4*0) / 1.0 = 0.4
        # C: (0.6*(3/3) + 0.4*0) / 1.0 = 0.6
        assert values[0] == pytest.approx(0.2)
        assert values[1] == pytest.approx(0.4)
        assert values[2] == pytest.approx(0.6)

    def test_frozen(self) -> None:
        """MultiFactorSignalStage 是 frozen dataclass。"""
        stage = MultiFactorSignalStage()
        with pytest.raises(AttributeError):
            stage.signal_factors = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# build_stock_selection_trend_pipeline
# ---------------------------------------------------------------------------


class TestBuildStockSelectionTrendPipeline:
    def test_default_config_builds_pipeline(self) -> None:
        """默认配置构建合法 Pipeline。"""
        config = StockSelectionTrendConfig()
        pipeline = build_stock_selection_trend_pipeline(config)
        assert pipeline is not None
        # MultiFactor + TrendFilter + Scoring + RiskLock +
        # Select + Allocate + Constraint
        assert len(pipeline._stages) == 7

    def test_pipeline_stage_order(self) -> None:
        """Pipeline 阶段顺序正确。"""
        config = StockSelectionTrendConfig()
        pipeline = build_stock_selection_trend_pipeline(config)
        stages = pipeline._stages
        assert isinstance(stages[0], MultiFactorSignalStage)
        assert isinstance(stages[1], TrendFilterStage)
        assert isinstance(stages[2], ScoringStage)
        assert isinstance(stages[3], RiskLockFilter)
        assert isinstance(stages[4], SelectionStage)
        assert isinstance(stages[5], AllocationStage)
        assert isinstance(stages[6], ConstraintStage)

    def test_max_weight_constraint_present(self) -> None:
        """ConstraintStage 中包含 MaxWeightConstraint。"""
        config = StockSelectionTrendConfig(max_weight=0.20)
        pipeline = build_stock_selection_trend_pipeline(config)
        constraint_stage = pipeline._stages[6]
        assert isinstance(constraint_stage, ConstraintStage)
        assert isinstance(constraint_stage.checker, ConstraintChecker)
        # The checker should contain a MaxWeightConstraint
        has_max_weight = any(
            isinstance(c, MaxWeightConstraint)
            for c in constraint_stage.checker._constraints
        )
        assert has_max_weight

    def test_inverse_vol_allocation(self) -> None:
        """inverse_vol 分配方式正确使用 InverseVolAllocator。"""
        config = StockSelectionTrendConfig(
            allocation_method="inverse_vol",
            cash_target=0.1,
        )
        pipeline = build_stock_selection_trend_pipeline(config)
        allocation_stage = pipeline._stages[5]
        assert isinstance(allocation_stage, AllocationStage)
        assert isinstance(allocation_stage.allocator, InverseVolAllocator)
        assert allocation_stage.allocator.cash_target == 0.1

    def test_equal_weight_allocation(self) -> None:
        """equal_weight 分配方式正确使用 EqualWeightAllocator。"""
        config = StockSelectionTrendConfig(
            allocation_method="equal_weight",
            cash_target=0.05,
        )
        pipeline = build_stock_selection_trend_pipeline(config)
        allocation_stage = pipeline._stages[5]
        assert isinstance(allocation_stage, AllocationStage)
        assert isinstance(allocation_stage.allocator, EqualWeightAllocator)
        assert allocation_stage.allocator.cash_target == 0.05


# ---------------------------------------------------------------------------
# E2E Pipeline
# ---------------------------------------------------------------------------


class TestPipelineE2E:
    def test_e2e_selects_top_k(
        self,
        empty_context: StrategyContext,
        multi_factor_bundle: StrategyInputBundle,
    ) -> None:
        """5 个标的、top_k=2 → 最终 2 个持仓。

        MultiFactorSignal 对 momentum 排名 (descending=False):
        STK001(0.15)→rank 1.0, STK005(-0.02)→rank 0.2.
        Scoring(ascending=False) 再排名 (descending=True),
        所以 STK005(rank 0.2)→score 1.0 是最高的。
        SelectionStage 取 score 最高的 2 个: STK005 和 STK004。
        """
        config = StockSelectionTrendConfig(
            signal_factors=("momentum",),
            signal_weights=(1.0,),
            top_k=2,
            trend_threshold=0.0,
            allocation_method="equal_weight",
        )
        pipeline = build_stock_selection_trend_pipeline(config)
        target = pipeline.run(empty_context, multi_factor_bundle)
        assert len(target.positions) == 2
        # ascending=False inverts: STK005 (rank 0.2→score 1.0)
        # and STK004 (rank 0.4→score 0.8)
        assert "STK004" in target.positions
        assert "STK005" in target.positions

    def test_e2e_trend_filter_excludes_low_rank(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """趋势过滤排除低 signal_value (rank percentile) 的标的。

        使用高 threshold 过滤掉 rank 较低的标的。
        """
        ids = [f"STK{i:03d}" for i in range(1, 6)]
        instruments = pl.DataFrame({"instrument_id": ids})
        market_data = pl.DataFrame(
            {
                "instrument_id": ids,
                "close": [10.0] * 5,
                "open": [10.0] * 5,
                "high": [10.5] * 5,
                "low": [9.5] * 5,
                "volume": [1_000_000.0] * 5,
            },
        )
        signal_values = pl.DataFrame(
            {
                "instrument_id": ids,
                "momentum": [0.20, 0.15, 0.10, 0.05, -0.10],
            },
        )
        bundle = StrategyInputBundle(
            trade_date="2026-03-22",
            strategy_id="test",
            run_id="run_001",
            instruments=instruments,
            market_data=market_data,
            signal_values=signal_values,
        )

        config = StockSelectionTrendConfig(
            signal_factors=("momentum",),
            signal_weights=(1.0,),
            top_k=10,
            trend_threshold=0.4,
            allocation_method="equal_weight",
        )
        pipeline = build_stock_selection_trend_pipeline(config)
        target = pipeline.run(empty_context, bundle)

        # Ranks (descending=False): STK005(-0.10)→0.2, STK004(0.05)→0.4,
        # STK003(0.10)→0.6, STK002(0.15)→0.8, STK001(0.20)→1.0
        # TrendFilter (signal_value >= 0.4): STK001, STK002, STK003, STK004
        assert "STK005" not in target.positions
        assert len(target.positions) == 4

    def test_e2e_max_weight_constraint_applied(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """max_weight 约束生效，无权重超过上限。"""
        ids = [f"STK{i:03d}" for i in range(1, 6)]
        instruments = pl.DataFrame({"instrument_id": ids})
        market_data = pl.DataFrame(
            {
                "instrument_id": ids,
                "close": [10.0] * 5,
                "open": [10.0] * 5,
                "high": [10.5] * 5,
                "low": [9.5] * 5,
                "volume": [1_000_000.0] * 5,
            },
        )
        signal_values = pl.DataFrame(
            {
                "instrument_id": ids,
                "signal_value": [0.20, 0.18, 0.15, 0.10, 0.05],
            },
        )
        bundle = StrategyInputBundle(
            trade_date="2026-03-22",
            strategy_id="test",
            run_id="run_001",
            instruments=instruments,
            market_data=market_data,
            signal_values=signal_values,
        )

        config = StockSelectionTrendConfig(
            signal_factors=("signal_value",),
            signal_weights=(1.0,),
            top_k=5,
            max_weight=0.15,
            trend_threshold=0.0,
            allocation_method="equal_weight",
        )
        pipeline = build_stock_selection_trend_pipeline(config)
        target = pipeline.run(empty_context, bundle)

        # All weights should be <= 0.15
        for weight in target.positions.values():
            assert weight <= 0.15

    def test_regime_config_inserts_scoring_step(
        self,
    ) -> None:
        """有 regime_config 时 Pipeline 包含 RegimeScoringStep 和 RegimeAware."""
        regime_config = RegimeConfig(
            indicators=(TrendIndicator(threshold=0.01),),
        )
        config = StockSelectionTrendConfig(regime_config=regime_config)
        pipeline = build_stock_selection_trend_pipeline(config)

        assert any(isinstance(s, RegimeScoringStep) for s in pipeline._stages)
        assert any(isinstance(s, RegimeAwareAllocationStage) for s in pipeline._stages)

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


# ---------------------------------------------------------------------------
# EngineConfig rebalance_freq
# ---------------------------------------------------------------------------


class TestRebalanceFreq:
    def _make_engine_loop(
        self,
        rebalance_freq: str,
        trading_days: list[str],
    ) -> EngineLoop:
        """构建带 rebalance_freq 配置的 EngineLoop。"""
        from unittest.mock import Mock

        config = EngineConfig(
            start_date=trading_days[0],
            end_date=trading_days[-1],
            initial_cash=1_000_000.0,
            rebalance_freq=rebalance_freq,
        )
        loop = EngineLoop(
            config=config,
            pipeline=Mock(),
            planner=Mock(),
            brokerage=Mock(),
            pre_trade_check=Mock(),
            data_feed=Mock(),
            options=EngineOptions(clock=Mock(), fee_model=Mock()),
        )
        loop._trading_days = tuple(trading_days)
        return loop

    def test_daily_always_true(self) -> None:
        """daily 模式下每天都返回 True。"""
        days = ["2026-03-01", "2026-03-02", "2026-03-03"]
        loop = self._make_engine_loop("daily", days)
        for d in days:
            assert loop._is_rebalance_day(d) is True

    def test_weekly_monday_true(self) -> None:
        """weekly 模式下周一返回 True。"""
        # 2026-03-02 is a Monday
        days = ["2026-03-02"]
        loop = self._make_engine_loop("weekly", days)
        assert loop._is_rebalance_day("2026-03-02") is True

    def test_weekly_tuesday_false(self) -> None:
        """weekly 模式下周二返回 False。"""
        days = ["2026-03-02", "2026-03-03"]  # Mon, Tue
        loop = self._make_engine_loop("weekly", days)
        assert loop._is_rebalance_day("2026-03-03") is False

    def test_monthly_first_day_true(self) -> None:
        """monthly 模式下当月第一个交易日返回 True。"""
        days = ["2026-03-02", "2026-03-09", "2026-03-16"]
        loop = self._make_engine_loop("monthly", days)
        assert loop._is_rebalance_day("2026-03-02") is True

    def test_monthly_second_day_false(self) -> None:
        """monthly 模式下当月非首个交易日返回 False。"""
        days = ["2026-03-02", "2026-03-09", "2026-03-16"]
        loop = self._make_engine_loop("monthly", days)
        assert loop._is_rebalance_day("2026-03-09") is False

    def test_monthly_cross_month_true(self) -> None:
        """monthly 模式下跨月首个交易日返回 True。"""
        days = ["2026-03-02", "2026-03-30", "2026-04-01"]
        loop = self._make_engine_loop("monthly", days)
        assert loop._is_rebalance_day("2026-04-01") is True
