"""Tests for stock_selection_trend strategy template.

Covers StockSelectionTrendConfig, validate_config, get_param_constraints,
MultiFactorSignalStage, build_stock_selection_trend_pipeline, and E2E pipeline.
"""

from __future__ import annotations

import polars as pl
import pytest
from ditto_strategy.alpha.builtins.filtering import (
    RiskLockFilter,
    TrendFilterStage,
)
from ditto_strategy.alpha.builtins.regime import RegimeConfig, TrendIndicator
from ditto_strategy.alpha.builtins.regime_allocation import RegimeAwareAllocationStage
from ditto_strategy.alpha.builtins.regime_scoring import RegimeScoringStep
from ditto_strategy.alpha.builtins.scoring import ScoringStage
from ditto_strategy.alpha.builtins.selection import SelectionStage
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.pipeline import StrategyInputBundle, StrategyPipeline
from ditto_strategy.alpha.specs import ParamConstraint
from ditto_strategy.alpha.templates.stock_selection_trend import (
    MultiFactorSignalStage,
    StockSelectionTrendConfig,
    build_stock_selection_trend_pipeline,
    get_param_constraints,
    validate_config,
)
from ditto_strategy.errors import StrategySpecError

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
        with pytest.raises(StrategySpecError, match="same length"):
            validate_config(config)

    def test_invalid_top_k_raises(self) -> None:
        """top_k < 1 时抛异常。"""
        config = StockSelectionTrendConfig(top_k=0)
        with pytest.raises(StrategySpecError, match="top_k"):
            validate_config(config)

    def test_invalid_max_weight_zero_raises(self) -> None:
        """max_weight <= 0 时抛异常。"""
        config = StockSelectionTrendConfig(max_weight=0.0)
        with pytest.raises(StrategySpecError, match="max_weight"):
            validate_config(config)

    def test_invalid_max_weight_over_one_raises(self) -> None:
        """max_weight > 1 时抛异常。"""
        config = StockSelectionTrendConfig(max_weight=1.5)
        with pytest.raises(StrategySpecError, match="max_weight"):
            validate_config(config)

    def test_invalid_allocation_method_raises(self) -> None:
        """非法 allocation_method 抛异常。"""
        config = StockSelectionTrendConfig(allocation_method="invalid")
        with pytest.raises(StrategySpecError, match="allocation_method"):
            validate_config(config)

    def test_invalid_rebalance_freq_raises(self) -> None:
        """非法 rebalance_freq 抛异常。"""
        config = StockSelectionTrendConfig(rebalance_freq="quarterly")
        with pytest.raises(StrategySpecError, match="rebalance_freq"):
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
    def test_default_config_builds_stages(self) -> None:
        """默认配置构建合法 alpha stages 列表。"""
        config = StockSelectionTrendConfig()
        stages = build_stock_selection_trend_pipeline(config)
        assert isinstance(stages, list)
        # MultiFactor + TrendFilter + Scoring + RiskLock + Select
        assert len(stages) == 5

    def test_pipeline_stage_order(self) -> None:
        """alpha stages 顺序正确。"""
        config = StockSelectionTrendConfig()
        stages = build_stock_selection_trend_pipeline(config)
        assert isinstance(stages[0], MultiFactorSignalStage)
        assert isinstance(stages[1], TrendFilterStage)
        assert isinstance(stages[2], ScoringStage)
        assert isinstance(stages[3], RiskLockFilter)
        assert isinstance(stages[4], SelectionStage)


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
        )
        stages = build_stock_selection_trend_pipeline(config)
        pipeline = StrategyPipeline(stages)
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
        )
        stages = build_stock_selection_trend_pipeline(config)
        pipeline = StrategyPipeline(stages)
        target = pipeline.run(empty_context, bundle)

        # Ranks (descending=False): STK005(-0.10)→0.2, STK004(0.05)→0.4,
        # STK003(0.10)→0.6, STK002(0.15)→0.8, STK001(0.20)→1.0
        # TrendFilter (signal_value >= 0.4): STK001, STK002, STK003, STK004
        assert "STK005" not in target.positions
        assert len(target.positions) == 4

    def test_regime_config_inserts_scoring_step(
        self,
    ) -> None:
        """有 regime_config 时 stages 包含 RegimeScoringStep 和 RegimeAware."""
        regime_config = RegimeConfig(
            indicators=(TrendIndicator(threshold=0.01),),
        )
        config = StockSelectionTrendConfig(regime_config=regime_config)
        stages = build_stock_selection_trend_pipeline(config)

        assert any(isinstance(s, RegimeScoringStep) for s in stages)
        assert any(isinstance(s, RegimeAwareAllocationStage) for s in stages)

        scoring_idx = next(
            i for i, s in enumerate(stages) if isinstance(s, RegimeScoringStep)
        )
        aware_idx = next(
            i for i, s in enumerate(stages) if isinstance(s, RegimeAwareAllocationStage)
        )
        assert scoring_idx < aware_idx
