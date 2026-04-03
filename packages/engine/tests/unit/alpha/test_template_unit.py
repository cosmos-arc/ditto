"""Tests for etf_rotation strategy template and RiskLockFilter."""

from __future__ import annotations

import polars as pl
import pytest
from ditto_engine.alpha.builtins.filtering import RiskLockFilter
from ditto_engine.alpha.builtins.selection import SelectionStage
from ditto_engine.alpha.builtins.signal import SignalStage
from ditto_engine.alpha.context import StrategyContext
from ditto_engine.alpha.pipeline import StrategyInputBundle
from ditto_engine.alpha.templates.etf_rotation import (
    ETFRotationConfig,
    build_etf_rotation_pipeline,
)
from ditto_engine.portfolio.allocation import AllocationStage, ScoreWeightAllocator
from ditto_engine.portfolio.constraints import ConstraintStage

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_context() -> StrategyContext:
    return StrategyContext()


@pytest.fixture
def sample_bundle() -> StrategyInputBundle:
    """构造 6 个标的的测试用 StrategyInputBundle。"""
    ids = [f"ETF{i:03d}" for i in range(1, 7)]
    instruments = pl.DataFrame({"instrument_id": ids})

    market_data = pl.DataFrame(
        {
            "instrument_id": ids,
            "close": [float(i + 1) for i in range(6)],
            "open": [float(i + 1) for i in range(6)],
            "high": [float(i + 2) for i in range(6)],
            "low": [float(i) for i in range(6)],
            "volume": [1000000.0] * 6,
        },
    )

    signal_values = pl.DataFrame(
        {
            "instrument_id": ids,
            "momentum_20d": [0.15, 0.12, 0.09, 0.06, 0.03, -0.01],
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
# ETFRotationConfig
# ---------------------------------------------------------------------------


class TestETFRotationConfig:
    def test_default_values(self) -> None:
        """默认配置值正确。"""
        config = ETFRotationConfig()
        assert config.top_k == 10
        assert config.scoring_method == "rank"
        assert config.allocation_method == "equal_weight"
        assert config.cash_target == 0.0
        assert config.signal_column == "signal_value"
        assert config.max_weight is None
        assert config.max_positions is None

    def test_frozen(self) -> None:
        """Config 是 frozen dataclass，不可变。"""
        config = ETFRotationConfig()
        with pytest.raises(AttributeError):
            config.top_k = 20  # type: ignore[misc]


# ---------------------------------------------------------------------------
# build_etf_rotation_pipeline
# ---------------------------------------------------------------------------


class TestBuildETFRotationPipeline:
    def test_default_config_builds_pipeline(self) -> None:
        """默认配置构建合法 Pipeline。"""
        config = ETFRotationConfig(top_k=5)
        pipeline = build_etf_rotation_pipeline(config)
        assert pipeline is not None
        # Signal + Score + RiskLock + Select + Allocate
        assert len(pipeline._stages) == 5

    def test_custom_top_k(self) -> None:
        """自定义 top_k 正确传递到 SelectionStage。"""
        config = ETFRotationConfig(top_k=3)
        pipeline = build_etf_rotation_pipeline(config)
        # 4th stage is SelectionStage
        selection = pipeline._stages[3]
        assert isinstance(selection, SelectionStage)
        assert selection.top_k == 3

    def test_score_weight_allocation(self) -> None:
        """score_weight 分配方式正确使用 ScoreWeightAllocator。"""
        config = ETFRotationConfig(
            allocation_method="score_weight",
            cash_target=0.1,
        )
        pipeline = build_etf_rotation_pipeline(config)
        allocation = pipeline._stages[4]
        assert isinstance(allocation, AllocationStage)
        assert isinstance(allocation.allocator, ScoreWeightAllocator)
        assert allocation.allocator.cash_target == 0.1

    def test_pipeline_contains_risklock_filter(self) -> None:
        """Pipeline 包含 RiskLockFilter。"""
        config = ETFRotationConfig()
        pipeline = build_etf_rotation_pipeline(config)
        assert any(isinstance(s, RiskLockFilter) for s in pipeline._stages)

    def test_with_max_weight_constraint(self) -> None:
        """带 max_weight 约束时 Pipeline 包含 ConstraintStage。"""
        config = ETFRotationConfig(max_weight=0.25)
        pipeline = build_etf_rotation_pipeline(config)
        assert any(isinstance(s, ConstraintStage) for s in pipeline._stages)

    def test_with_max_positions_constraint(self) -> None:
        """带 max_positions 约束时 Pipeline 包含 ConstraintStage。"""
        config = ETFRotationConfig(max_positions=5)
        pipeline = build_etf_rotation_pipeline(config)
        assert any(isinstance(s, ConstraintStage) for s in pipeline._stages)

    def test_empty_constraints_no_constraint_stage(self) -> None:
        """无约束时 Pipeline 不包含 ConstraintStage。"""
        config = ETFRotationConfig()
        pipeline = build_etf_rotation_pipeline(config)
        assert not any(isinstance(s, ConstraintStage) for s in pipeline._stages)

    def test_empty_selection_returns_empty_portfolio(
        self,
        sample_bundle: StrategyInputBundle,
        empty_context: StrategyContext,
    ) -> None:
        """top_k=0 选不出任何标的，返回空持仓。"""
        config = ETFRotationConfig(
            top_k=0,
            signal_column="momentum_20d",
        )
        pipeline = build_etf_rotation_pipeline(config)
        target = pipeline.run(empty_context, sample_bundle)

        assert len(target.positions) == 0

    def test_custom_signal_column(self, sample_bundle: StrategyInputBundle) -> None:
        """自定义 signal_column 正确传递到 SignalStage。"""
        config = ETFRotationConfig(
            top_k=3,
            signal_column="momentum_20d",
        )
        pipeline = build_etf_rotation_pipeline(config)
        signal_stage = pipeline._stages[0]
        assert isinstance(signal_stage, SignalStage)
        assert signal_stage.source_column == "momentum_20d"


# ---------------------------------------------------------------------------
# RiskLockFilter
# ---------------------------------------------------------------------------


class TestRiskLockFilter:
    def test_no_locked_returns_as_is(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """无锁定标的时原样返回。"""
        frame = pl.DataFrame(
            {"instrument_id": ["A", "B", "C"], "value": [1.0, 2.0, 3.0]},
        )
        filt = RiskLockFilter()
        result = filt.process(frame, empty_context)
        assert result.shape == frame.shape

    def test_partial_lock_filters_locked(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """部分锁定时过滤锁定标的。"""
        frame = pl.DataFrame(
            {"instrument_id": ["A", "B", "C"], "value": [1.0, 2.0, 3.0]},
        )
        empty_context.lock_instrument("B", "hit stop-loss")
        filt = RiskLockFilter()
        result = filt.process(frame, empty_context)
        assert result.shape == (2, 2)
        assert set(result["instrument_id"].to_list()) == {"A", "C"}

    def test_all_locked_returns_empty(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """全部锁定时返回空 frame。"""
        frame = pl.DataFrame(
            {"instrument_id": ["A", "B"], "value": [1.0, 2.0]},
        )
        empty_context.lock_instrument("A", "halt")
        empty_context.lock_instrument("B", "halt")
        filt = RiskLockFilter()
        result = filt.process(frame, empty_context)
        assert result.is_empty()

    def test_locked_not_in_frame_no_error(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """锁定标的不在 frame 中时不出错。"""
        frame = pl.DataFrame(
            {"instrument_id": ["A", "B"], "value": [1.0, 2.0]},
        )
        empty_context.lock_instrument("X", "some reason")
        filt = RiskLockFilter()
        result = filt.process(frame, empty_context)
        assert result.shape == (2, 2)

    def test_empty_frame_no_error(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """空 frame 不报错。"""
        frame = pl.DataFrame(
            {"instrument_id": []},
            schema={"instrument_id": pl.Utf8},
        )
        empty_context.lock_instrument("A", "halt")
        filt = RiskLockFilter()
        result = filt.process(frame, empty_context)
        assert result.is_empty()

    def test_frozen(self) -> None:
        """RiskLockFilter 是 frozen dataclass。"""
        filt = RiskLockFilter()
        with pytest.raises(AttributeError):
            filt.some_attr = 1  # type: ignore[attr-defined]
