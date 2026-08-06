"""Tests for stock_selection_trend strategy template.

Covers StockSelectionTrendConfig, validate_config, get_param_constraints,
MultiFactorSignalStage, build_stock_selection_trend_pipeline, and E2E pipeline.
"""

from __future__ import annotations

from dataclasses import replace

import polars as pl
import pytest
from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.builtins.composite import CompositeDecisionStage
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
from ditto_strategy.alpha.selection_evidence import SelectionEvidenceCollector
from ditto_strategy.alpha.specs import ParamConstraint
from ditto_strategy.alpha.templates.stock_selection_trend import (
    MultiFactorSignalStage,
    StockSelectionTrendConfig,
    build_stock_selection_trend_pipeline,
    get_param_constraints,
    preprocess_factor_column,
    validate_config,
)
from ditto_strategy.errors import StrategySpecError
from polars.testing import assert_frame_equal

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_context() -> StrategyContext:
    return StrategyContext()


def _build_stock_id_map(ids: list[str]) -> dict[str, InstrumentId]:
    return {ticker: InstrumentId(index) for index, ticker in enumerate(ids, start=1)}


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
        instrument_id_map=_build_stock_id_map(ids),
        require_canonical_target_ids=True,
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
        Scoring(ascending=False) 保持 larger-is-better，
        所以 STK001(rank 1.0)→score 1.0 是最高的。
        SelectionStage 取 score 最高的 2 个: STK001 和 STK002。
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
        assert InstrumentId(1) in target.positions
        assert InstrumentId(2) in target.positions
        assert "STK001" not in target.positions
        assert "STK002" not in target.positions

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
            instrument_id_map=_build_stock_id_map(ids),
            require_canonical_target_ids=True,
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
        assert InstrumentId(5) not in target.positions
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


# ---------------------------------------------------------------------------
# F1-#1 因子预处理增强
# ---------------------------------------------------------------------------


class TestPreprocessFactorColumn:
    """preprocess_factor_column 纯函数 — winsorize/zscore/neutralize 数学性质.

    语义对齐 ditto_features.expression.codegen._cs_operators(横截面算子),
    但无 .over(time_keys):stage frame 是单日横截面,全 frame 即一个截面。
    """

    def test_no_preprocess_is_identity(self) -> None:
        """全开关关闭时,预处理是恒等变换(值不变)."""
        df = pl.DataFrame({"factor": [1.0, 2.0, 3.0, 4.0, 5.0]})
        result = df.with_columns(
            preprocess_factor_column(
                pl.col("factor"),
                winsorize_sigma=None,
                zscore=False,
                neutralize_by=None,
            ).alias("prepped"),
        )
        assert result["prepped"].to_list() == [1.0, 2.0, 3.0, 4.0, 5.0]

    def test_winsorize_clips_outlier_to_sigma_bounds(self) -> None:
        """winsorize(sigma) 将超出 mean±sigma·std 的极值截断到边界.

        factor=[1,2,3,4,100], mean=22, std(ddof=1)=sqrt(1902.5)≈43.6174,
        sigma=1 → bounds=[-21.6174, 65.6174]; 100 clipped to 65.6174。
        """
        df = pl.DataFrame({"factor": [1.0, 2.0, 3.0, 4.0, 100.0]})
        result = df.with_columns(
            preprocess_factor_column(
                pl.col("factor"),
                winsorize_sigma=1.0,
                zscore=False,
                neutralize_by=None,
            ).alias("prepped"),
        )
        values = result["prepped"].to_list()
        assert values[:4] == [1.0, 2.0, 3.0, 4.0]
        assert values[4] == pytest.approx(65.6174, rel=1e-3)

    def test_zscore_standardizes_mean_zero_std_one(self) -> None:
        """zscore 后 mean≈0, std≈1; 中间值标准化为 0."""
        df = pl.DataFrame({"factor": [1.0, 2.0, 3.0, 4.0, 5.0]})
        result = df.with_columns(
            preprocess_factor_column(
                pl.col("factor"),
                winsorize_sigma=None,
                zscore=True,
                neutralize_by=None,
            ).alias("prepped"),
        )
        prepped = result["prepped"]
        assert prepped.mean() == pytest.approx(0.0, abs=1e-9)
        assert prepped.std() == pytest.approx(1.0, abs=1e-9)
        assert prepped.to_list()[2] == pytest.approx(0.0, abs=1e-9)

    def test_zscore_zero_std_returns_zero(self) -> None:
        """常数列 std=0 → zscore 返回 0.0(对齐 cs_zscore 语义)."""
        df = pl.DataFrame({"factor": [5.0, 5.0, 5.0]})
        result = df.with_columns(
            preprocess_factor_column(
                pl.col("factor"),
                winsorize_sigma=None,
                zscore=True,
                neutralize_by=None,
            ).alias("prepped"),
        )
        assert result["prepped"].to_list() == [0.0, 0.0, 0.0]

    def test_neutralize_centers_each_group_to_zero_mean(self) -> None:
        """按组中性化: 每组 demean 后组内均值=0.

        factor=[1,3,10,20], group=["A","A","B","B"]
        A mean=2 → [-1, 1]; B mean=15 → [-5, 5]。
        """
        df = pl.DataFrame(
            {
                "factor": [1.0, 3.0, 10.0, 20.0],
                "industry": ["A", "A", "B", "B"],
            },
        )
        result = df.with_columns(
            preprocess_factor_column(
                pl.col("factor"),
                winsorize_sigma=None,
                zscore=False,
                neutralize_by="industry",
            ).alias("prepped"),
        )
        assert result["prepped"].to_list() == [-1.0, 1.0, -5.0, 5.0]

    def test_chain_winsorize_then_zscore(self) -> None:
        """组合 winsorize+zscore: 极值先截断再标准化, std≈1."""
        df = pl.DataFrame({"factor": [1.0, 2.0, 3.0, 4.0, 100.0]})
        result = df.with_columns(
            preprocess_factor_column(
                pl.col("factor"),
                winsorize_sigma=1.0,
                zscore=True,
                neutralize_by=None,
            ).alias("prepped"),
        )
        prepped = result["prepped"]
        assert prepped.std() == pytest.approx(1.0, abs=1e-9)
        assert prepped.mean() == pytest.approx(0.0, abs=1e-9)


class TestMultiFactorSignalStagePreprocess:
    """MultiFactorSignalStage 预处理端到端行为."""

    def test_neutralize_changes_rank_order(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """按组中性化改变横截面 rank 排序(只有非单调变换影响 rank).

        factor=[10,20,1,2], group=["A","A","B","B"]
        无中性化: rank(asc)=[3,4,1,2] → pct=[0.75,1.0,0.25,0.5]
        中性化后: demean=[-5,5,-0.5,0.5] → rank(asc)=[1,4,2,3] → pct=[0.25,1.0,0.5,0.75]
        """
        frame = pl.DataFrame(
            {
                "instrument_id": ["A1", "A2", "B1", "B2"],
                "factor": [10.0, 20.0, 1.0, 2.0],
                "industry": ["A", "A", "B", "B"],
            },
        )
        stage_plain = MultiFactorSignalStage(
            signal_factors=("factor",),
            signal_weights=(1.0,),
            output_column="signal_value",
        )
        plain = stage_plain.process(frame, empty_context)["signal_value"].to_list()
        assert plain == pytest.approx([0.75, 1.0, 0.25, 0.5])

        stage_neutral = MultiFactorSignalStage(
            signal_factors=("factor",),
            signal_weights=(1.0,),
            output_column="signal_value",
            neutralize_by="industry",
        )
        neutral = stage_neutral.process(frame, empty_context)["signal_value"].to_list()
        assert neutral == pytest.approx([0.25, 1.0, 0.5, 0.75])

    def test_neutralize_missing_column_raises_strategy_spec_error(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """neutralize_by 列缺失 → StrategySpecError(fail-closed)."""
        frame = pl.DataFrame(
            {
                "instrument_id": ["A", "B", "C"],
                "factor": [10.0, 20.0, 30.0],
            },
        )
        stage = MultiFactorSignalStage(
            signal_factors=("factor",),
            signal_weights=(1.0,),
            output_column="signal_value",
            neutralize_by="industry",
        )
        with pytest.raises(StrategySpecError, match="industry"):
            stage.process(frame, empty_context)

    def test_preprocess_off_by_default_preserves_behavior(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """默认配置(无预处理)与现有 rank+加权行为一致(向后兼容)."""
        frame = pl.DataFrame(
            {
                "instrument_id": ["A", "B", "C"],
                "factor": [10.0, 20.0, 30.0],
            },
        )
        stage = MultiFactorSignalStage(
            signal_factors=("factor",),
            signal_weights=(1.0,),
            output_column="signal_value",
        )
        result = stage.process(frame, empty_context)["signal_value"].to_list()
        assert result == pytest.approx([1.0 / 3, 2.0 / 3, 3.0 / 3])

    def test_full_preprocess_chain_runs_without_leaking_temp_columns(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """winsorize+zscore+neutralize 全链不报错; 临时预处理列不污染输出."""
        frame = pl.DataFrame(
            {
                "instrument_id": ["A1", "A2", "B1", "B2", "B3"],
                "factor": [1.0, 2.0, 3.0, 4.0, 100.0],
                "industry": ["A", "A", "B", "B", "B"],
            },
        )
        stage = MultiFactorSignalStage(
            signal_factors=("factor",),
            signal_weights=(1.0,),
            output_column="signal_value",
            winsorize_sigma=2.0,
            zscore=True,
            neutralize_by="industry",
        )
        result = stage.process(frame, empty_context)
        assert "signal_value" in result.columns
        assert result["signal_value"].dtype == pl.Float64
        assert all(not name.startswith("_prepped_") for name in result.columns)


class TestMultiFactorContributionEvidence:
    """Contribution evidence comes from the actual preprocess/rank path."""

    def test_duplicate_factor_occurrences_are_aggregated_in_first_seen_order(
        self,
        empty_context: StrategyContext,
    ) -> None:
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "factor": [1.0, 2.0, 3.0],
                "other": [3.0, 1.0, 2.0],
            },
        )
        factors = ("factor", "other", "factor")
        weights = (0.25, 0.25, 0.5)
        expected = MultiFactorSignalStage(
            signal_factors=factors,
            signal_weights=weights,
        ).process(frame, empty_context)
        collector = SelectionEvidenceCollector()
        collector.begin_rebalance("2026-03-22")

        actual = MultiFactorSignalStage(
            signal_factors=factors,
            signal_weights=weights,
            evidence_sink=collector,
        ).process(frame, empty_context)
        collector.commit_rebalance()

        assert_frame_equal(actual, expected)
        first_instrument = [
            event
            for event in collector.snapshot().factor_contributions
            if event.instrument_id == 1
        ]
        assert [event.factor_name for event in first_instrument] == ["factor", "other"]
        assert [event.weight for event in first_instrument] == pytest.approx(
            [0.75, 0.25],
        )
        assert sum(event.contribution or 0.0 for event in first_instrument) == (
            pytest.approx(actual["signal_value"][0])
        )

    def test_duplicate_factor_negative_occurrence_aggregates_effective_weight(
        self,
        empty_context: StrategyContext,
    ) -> None:
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "factor": [1.0, 2.0, 3.0],
                "other": [3.0, 1.0, 2.0],
            },
        )
        factors = ("factor", "other", "factor")
        weights = (1.0, 1.0, -1.0)
        expected = MultiFactorSignalStage(
            signal_factors=factors,
            signal_weights=weights,
        ).process(frame, empty_context)
        collector = SelectionEvidenceCollector()
        collector.begin_rebalance("2026-03-22")

        actual = MultiFactorSignalStage(
            signal_factors=factors,
            signal_weights=weights,
            evidence_sink=collector,
        ).process(frame, empty_context)
        collector.commit_rebalance()

        assert_frame_equal(actual, expected)
        first_instrument = [
            event
            for event in collector.snapshot().factor_contributions
            if event.instrument_id == 1
        ]
        assert [event.weight for event in first_instrument] == pytest.approx([0.0, 1.0])
        assert first_instrument[0].contribution == pytest.approx(0.0)
        assert sum(event.contribution or 0.0 for event in first_instrument) == (
            pytest.approx(actual["signal_value"][0])
        )

    def test_duplicate_missing_factor_emits_one_zero_contribution_per_instrument(
        self,
        empty_context: StrategyContext,
    ) -> None:
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "present": [1.0, 2.0, 3.0],
            },
        )
        factors = ("missing", "present", "missing")
        weights = (0.2, 0.3, 0.5)
        expected = MultiFactorSignalStage(
            signal_factors=factors,
            signal_weights=weights,
        ).process(frame, empty_context)
        collector = SelectionEvidenceCollector()
        collector.begin_rebalance("2026-03-22")

        actual = MultiFactorSignalStage(
            signal_factors=factors,
            signal_weights=weights,
            evidence_sink=collector,
        ).process(frame, empty_context)
        collector.commit_rebalance()

        assert_frame_equal(actual, expected)
        missing = [
            event
            for event in collector.snapshot().factor_contributions
            if event.factor_name == "missing"
        ]
        assert len(missing) == frame.height
        assert {event.weight for event in missing} == {0.7}
        assert all(event.raw_value is None for event in missing)
        assert all(event.contribution == 0.0 for event in missing)

    def test_pipeline_emits_raw_processed_contribution_and_final_selection(
        self,
        empty_context: StrategyContext,
    ) -> None:
        ids = ["A", "B", "C"]
        bundle = StrategyInputBundle(
            trade_date="2026-03-22",
            strategy_id="contribution-proof",
            run_id="run-contribution",
            instruments=pl.DataFrame({"instrument_id": ids}),
            market_data=pl.DataFrame({"instrument_id": ids}),
            signal_values=pl.DataFrame(
                {"instrument_id": ids, "momentum": [1.0, 2.0, 3.0]},
            ),
        )
        config = StockSelectionTrendConfig(
            signal_factors=("momentum",),
            signal_weights=(1.0,),
            top_k=2,
            zscore=True,
        )
        collector = SelectionEvidenceCollector()
        stages = build_stock_selection_trend_pipeline(
            config,
            evidence_sink=collector,
        )

        target = StrategyPipeline(stages, evidence_sink=collector).run(
            empty_context,
            bundle,
        )
        snapshot = collector.snapshot()

        assert target.positions == {"B": 0.5, "C": 0.5}
        contributions = snapshot.factor_contributions
        assert [item.instrument_id for item in contributions] == ["A", "B", "C"]
        assert [
            (
                item.raw_value,
                item.processed_value,
                item.normalized_value,
                item.weight,
                item.contribution,
                item.factor_signal_score,
            )
            for item in contributions
        ] == pytest.approx(
            [
                (1.0, -1.0, 1 / 3, 1.0, 1 / 3, 1 / 3),
                (2.0, 0.0, 2 / 3, 1.0, 2 / 3, 2 / 3),
                (3.0, 1.0, 1.0, 1.0, 1.0, 1.0),
            ],
        )
        assert [(item.rank, item.selected) for item in contributions] == [
            (3, False),
            (2, True),
            (1, True),
        ]

    def test_sink_path_preserves_exact_factor_output_and_drops_temp_columns(
        self,
        empty_context: StrategyContext,
    ) -> None:
        frame = pl.DataFrame(
            {"instrument_id": [1, 2, 3], "factor": [10.0, 20.0, 30.0]},
        )
        plain_stage = MultiFactorSignalStage(
            signal_factors=("factor",),
            signal_weights=(1.0,),
            output_column="signal_value",
            zscore=True,
        )
        collector = SelectionEvidenceCollector()
        collector.begin_rebalance("2026-03-22")
        evidence_stage = MultiFactorSignalStage(
            signal_factors=("factor",),
            signal_weights=(1.0,),
            output_column="signal_value",
            zscore=True,
            evidence_sink=collector,
        )

        expected = plain_stage.process(frame, empty_context)
        actual = evidence_stage.process(frame, empty_context)
        collector.commit_rebalance()

        assert_frame_equal(actual, expected)
        assert all(not name.startswith("_prepped_") for name in actual.columns)
        assert len(collector.snapshot().factor_contributions) == 3

    def test_missing_factor_value_is_explicit_none_in_evidence(
        self,
        empty_context: StrategyContext,
    ) -> None:
        frame = pl.DataFrame(
            {"instrument_id": [1, 2, 3], "factor": [10.0, None, 30.0]},
        )
        collector = SelectionEvidenceCollector()
        collector.begin_rebalance("2026-03-22")

        MultiFactorSignalStage(
            signal_factors=("factor",),
            signal_weights=(1.0,),
            evidence_sink=collector,
        ).process(frame, empty_context)
        collector.commit_rebalance()

        missing = collector.snapshot().factor_contributions[1]
        assert missing.raw_value is None
        assert missing.processed_value is None
        assert missing.normalized_value is None
        assert missing.contribution is None
        assert missing.factor_signal_score is None

    def test_one_collector_records_complete_simple_pipeline_evidence_across_dates(
        self,
        empty_context: StrategyContext,
        multi_factor_bundle: StrategyInputBundle,
    ) -> None:
        collector = SelectionEvidenceCollector()
        stages = build_stock_selection_trend_pipeline(
            StockSelectionTrendConfig(
                signal_factors=("momentum", "volatility"),
                signal_weights=(0.8, 0.2),
                top_k=2,
                trend_threshold=0.0,
            ),
            evidence_sink=collector,
        )
        pipeline = StrategyPipeline(stages, evidence_sink=collector)

        for trade_date in ("2026-03-22", "2026-03-23"):
            pipeline.run(
                empty_context,
                replace(multi_factor_bundle, trade_date=trade_date),
            )

        snapshot = collector.snapshot()
        assert {event.trade_date for event in snapshot.initial_universe} == {
            "2026-03-22",
            "2026-03-23",
        }
        assert {event.trade_date for event in snapshot.factor_contributions} == {
            "2026-03-22",
            "2026-03-23",
        }
        assert {event.trade_date for event in snapshot.selections} == {
            "2026-03-22",
            "2026-03-23",
        }
        assert {event.trade_date for event in snapshot.exclusions} == {
            "2026-03-22",
            "2026-03-23",
        }


class TestStockSelectionTrendConfigPreprocess:
    """StockSelectionTrendConfig 预处理字段默认值."""

    def test_default_preprocess_off(self) -> None:
        config = StockSelectionTrendConfig()
        assert config.winsorize_sigma is None
        assert config.zscore is False
        assert config.neutralize_by is None

    def test_preprocess_fields_settable(self) -> None:
        config = StockSelectionTrendConfig(
            winsorize_sigma=3.0,
            zscore=True,
            neutralize_by="industry",
        )
        assert config.winsorize_sigma == 3.0
        assert config.zscore is True
        assert config.neutralize_by == "industry"


class TestValidateConfigPreprocess:
    """validate_config 预处理字段校验."""

    def test_valid_winsorize_sigma_passes(self) -> None:
        validate_config(StockSelectionTrendConfig(winsorize_sigma=3.0))  # no raise

    def test_zero_winsorize_sigma_raises(self) -> None:
        with pytest.raises(StrategySpecError, match="winsorize_sigma"):
            validate_config(StockSelectionTrendConfig(winsorize_sigma=0.0))

    def test_negative_winsorize_sigma_raises(self) -> None:
        with pytest.raises(StrategySpecError, match="winsorize_sigma"):
            validate_config(StockSelectionTrendConfig(winsorize_sigma=-1.0))

    def test_empty_neutralize_by_raises(self) -> None:
        with pytest.raises(StrategySpecError, match="neutralize_by"):
            validate_config(StockSelectionTrendConfig(neutralize_by=""))

    def test_valid_neutralize_by_passes(self) -> None:
        validate_config(StockSelectionTrendConfig(neutralize_by="industry"))  # no raise


class TestBuildStockSelectionTrendPipelinePreprocess:
    """build_stock_selection_trend_pipeline 透传预处理参数到首 stage."""

    def test_pipeline_passes_preprocess_to_first_stage(self) -> None:
        config = StockSelectionTrendConfig(
            winsorize_sigma=3.0,
            zscore=True,
            neutralize_by="industry",
        )
        stages = build_stock_selection_trend_pipeline(config)
        assert isinstance(stages[0], MultiFactorSignalStage)
        assert stages[0].winsorize_sigma == 3.0
        assert stages[0].zscore is True
        assert stages[0].neutralize_by == "industry"

    def test_default_pipeline_stage_has_no_preprocess(self) -> None:
        config = StockSelectionTrendConfig()
        stages = build_stock_selection_trend_pipeline(config)
        assert isinstance(stages[0], MultiFactorSignalStage)
        assert stages[0].winsorize_sigma is None
        assert stages[0].zscore is False
        assert stages[0].neutralize_by is None


# ---------------------------------------------------------------------------
# F1-#3 多因子融合增强(simple / composite)
# ---------------------------------------------------------------------------


class TestStockSelectionTrendConfigFusion:
    """StockSelectionTrendConfig fusion 字段."""

    def test_default_fusion_is_simple(self) -> None:
        assert StockSelectionTrendConfig().fusion == "simple"

    def test_fusion_settable_composite(self) -> None:
        config = StockSelectionTrendConfig(fusion="composite")
        assert config.fusion == "composite"


class TestValidateConfigFusion:
    """validate_config fusion 枚举校验."""

    def test_invalid_fusion_raises(self) -> None:
        with pytest.raises(StrategySpecError, match="fusion"):
            validate_config(StockSelectionTrendConfig(fusion="invalid"))

    def test_valid_simple_passes(self) -> None:
        validate_config(StockSelectionTrendConfig(fusion="simple"))  # no raise

    def test_valid_composite_passes(self) -> None:
        validate_config(StockSelectionTrendConfig(fusion="composite"))  # no raise


class TestBuildStockSelectionTrendPipelineFusion:
    """build_stock_selection_trend_pipeline fusion 分支与列命名桥接."""

    def test_simple_uses_multi_factor_stage(self) -> None:
        config = StockSelectionTrendConfig(fusion="simple")
        stages = build_stock_selection_trend_pipeline(config)
        assert isinstance(stages[0], MultiFactorSignalStage)

    def test_composite_uses_composite_decision_stage(self) -> None:
        config = StockSelectionTrendConfig(
            signal_factors=("momentum", "volatility"),
            signal_weights=(0.6, 0.4),
            fusion="composite",
        )
        stages = build_stock_selection_trend_pipeline(config)
        assert isinstance(stages[0], CompositeDecisionStage)

    def test_composite_skips_scoring_stage(self) -> None:
        """composite 已产 score,跳过 ScoringStage(列命名桥接)."""
        config = StockSelectionTrendConfig(fusion="composite")
        stages = build_stock_selection_trend_pipeline(config)
        # Composite + TrendFilter + RiskLock + Select = 4(simple 是 5,多一个 Scoring)
        assert len(stages) == 4
        assert not any(isinstance(s, ScoringStage) for s in stages)

    def test_composite_trend_filter_reads_score_column(self) -> None:
        """composite 模式 TrendFilter 读 score(非 signal_value,桥接列命名)."""
        config = StockSelectionTrendConfig(fusion="composite")
        stages = build_stock_selection_trend_pipeline(config)
        trend = next(s for s in stages if isinstance(s, TrendFilterStage))
        assert trend.signal_column == "score"

    def test_composite_sub_stages_one_per_factor_with_weights(self) -> None:
        config = StockSelectionTrendConfig(
            signal_factors=("momentum", "volatility", "quality"),
            signal_weights=(0.4, 0.3, 0.3),
            fusion="composite",
        )
        stages = build_stock_selection_trend_pipeline(config)
        composite = stages[0]
        assert isinstance(composite, CompositeDecisionStage)
        assert len(composite.stages) == 3
        assert composite.weights == (0.4, 0.3, 0.3)
        for sub in composite.stages:
            assert isinstance(sub, MultiFactorSignalStage)

    def test_composite_pipeline_e2e_selects_top_k(
        self,
        empty_context: StrategyContext,
        multi_factor_bundle: StrategyInputBundle,
    ) -> None:
        """composite 模式端到端: 融合后选 top_k,产出合法 positions."""
        config = StockSelectionTrendConfig(
            signal_factors=("momentum", "volatility"),
            signal_weights=(0.6, 0.4),
            top_k=2,
            trend_threshold=0.0,
            fusion="composite",
        )
        stages = build_stock_selection_trend_pipeline(config)
        pipeline = StrategyPipeline(stages)
        target = pipeline.run(empty_context, multi_factor_bundle)
        assert len(target.positions) <= 2

    def test_composite_evidence_does_not_report_local_substage_contributions(
        self,
        empty_context: StrategyContext,
        multi_factor_bundle: StrategyInputBundle,
    ) -> None:
        """Child-local rank scores are not additive to the composite final score."""
        collector = SelectionEvidenceCollector()
        config = StockSelectionTrendConfig(
            signal_factors=("momentum", "volatility"),
            signal_weights=(0.8, 0.2),
            top_k=2,
            trend_threshold=0.0,
            fusion="composite",
        )
        stages = build_stock_selection_trend_pipeline(
            config,
            evidence_sink=collector,
        )

        StrategyPipeline(stages, evidence_sink=collector).run(
            empty_context,
            multi_factor_bundle,
        )

        assert collector.snapshot().factor_contributions == ()
        composite = stages[0]
        assert isinstance(composite, CompositeDecisionStage)
        assert all(
            isinstance(stage, MultiFactorSignalStage) and stage.evidence_sink is None
            for stage in composite.stages
        )
