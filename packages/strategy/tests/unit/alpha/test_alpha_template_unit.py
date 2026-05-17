"""Tests for etf_rotation strategy template and RiskLockFilter."""

from __future__ import annotations

import polars as pl
import pytest
from ditto_strategy.alpha.builtins.filtering import RiskLockFilter
from ditto_strategy.alpha.builtins.regime import RegimeConfig, TrendIndicator
from ditto_strategy.alpha.builtins.regime_allocation import RegimeAwareAllocationStage
from ditto_strategy.alpha.builtins.regime_scoring import RegimeScoringStep
from ditto_strategy.alpha.builtins.scoring import ScoringStage
from ditto_strategy.alpha.builtins.selection import SelectionStage
from ditto_strategy.alpha.builtins.signal import SignalStage
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.pipeline import StrategyInputBundle, StrategyPipeline
from ditto_strategy.alpha.specs import ParamConstraint
from ditto_strategy.alpha.templates.etf_rotation import (
    ETFRotationConfig,
    build_etf_rotation_pipeline,
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
        assert config.scoring_method.value == "rank"
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
    def test_default_config_builds_stages(self) -> None:
        """默认配置构建合法 alpha stages 列表。"""
        config = ETFRotationConfig(top_k=5)
        stages = build_etf_rotation_pipeline(config)
        assert isinstance(stages, list)
        assert len(stages) == 4

    def test_custom_top_k(self) -> None:
        """自定义 top_k 正确传递到 SelectionStage。"""
        config = ETFRotationConfig(top_k=3)
        stages = build_etf_rotation_pipeline(config)
        selection = stages[3]
        assert isinstance(selection, SelectionStage)
        assert selection.top_k == 3

    def test_stages_contain_risklock_filter(self) -> None:
        """alpha stages 包含 RiskLockFilter。"""
        config = ETFRotationConfig()
        stages = build_etf_rotation_pipeline(config)
        assert any(isinstance(s, RiskLockFilter) for s in stages)

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
        stages = build_etf_rotation_pipeline(config)
        pipeline = StrategyPipeline(stages)
        target = pipeline.run(empty_context, sample_bundle)

        assert len(target.positions) == 0

    def test_custom_signal_column(self, sample_bundle: StrategyInputBundle) -> None:
        """自定义 signal_column 正确传递到 SignalStage。"""
        config = ETFRotationConfig(
            top_k=3,
            signal_column="momentum_20d",
        )
        stages = build_etf_rotation_pipeline(config)
        signal_stage = stages[0]
        assert isinstance(signal_stage, SignalStage)
        assert signal_stage.source_column == "momentum_20d"

    def test_regime_config_inserts_scoring_step(
        self,
        sample_bundle: StrategyInputBundle,
        empty_context: StrategyContext,
    ) -> None:
        """regime_config 时 stages 包含 RegimeScoringStep 且 frame 含三列."""
        regime_config = RegimeConfig(
            indicators=(TrendIndicator(threshold=0.01),),
        )
        config = ETFRotationConfig(
            top_k=3,
            signal_column="momentum_20d",
            regime_config=regime_config,
        )
        stages = build_etf_rotation_pipeline(config)

        # stages 应包含 RegimeScoringStep 和 RegimeAwareAllocationStage
        assert any(isinstance(s, RegimeScoringStep) for s in stages)
        assert any(isinstance(s, RegimeAwareAllocationStage) for s in stages)

        # RegimeScoringStep 应在 RegimeAwareAllocationStage 之前
        scoring_idx = next(
            i for i, s in enumerate(stages) if isinstance(s, RegimeScoringStep)
        )
        aware_idx = next(
            i for i, s in enumerate(stages) if isinstance(s, RegimeAwareAllocationStage)
        )
        assert scoring_idx < aware_idx

        # 运行 pipeline 验证 frame 包含 regime 三列
        pipeline = StrategyPipeline(stages)
        target = pipeline.run(empty_context, sample_bundle)
        assert len(target.positions) > 0

    def test_pipeline_stage_order(self) -> None:
        """Pipeline 阶段顺序正确。"""
        config = ETFRotationConfig()
        stages = build_etf_rotation_pipeline(config)
        assert isinstance(stages[0], SignalStage)
        assert isinstance(stages[1], ScoringStage)
        assert isinstance(stages[2], RiskLockFilter)
        assert isinstance(stages[3], SelectionStage)


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


# ---------------------------------------------------------------------------
# ETFRotation validate_config
# ---------------------------------------------------------------------------


class TestETFRotationValidateConfig:
    def test_valid_config_passes(self) -> None:
        """合法配置不抛异常。"""
        config = ETFRotationConfig()
        validate_config(config)  # Should not raise

    def test_invalid_top_k_raises(self) -> None:
        """top_k < 1 时抛异常。"""
        config = ETFRotationConfig(top_k=0)
        with pytest.raises(StrategySpecError, match="top_k"):
            validate_config(config)

    def test_invalid_max_weight_zero_raises(self) -> None:
        """max_weight <= 0 时抛异常。"""
        config = ETFRotationConfig(max_weight=0.0)
        with pytest.raises(StrategySpecError, match="max_weight"):
            validate_config(config)

    def test_invalid_max_weight_over_one_raises(self) -> None:
        """max_weight > 1 时抛异常。"""
        config = ETFRotationConfig(max_weight=1.5)
        with pytest.raises(StrategySpecError, match="max_weight"):
            validate_config(config)

    def test_max_weight_none_ok(self) -> None:
        """max_weight=None 不报错。"""
        config = ETFRotationConfig(max_weight=None)
        validate_config(config)  # Should not raise

    def test_invalid_allocation_method_raises(self) -> None:
        """非法 allocation_method 抛异常。"""
        config = ETFRotationConfig(allocation_method="invalid")
        with pytest.raises(StrategySpecError, match="allocation_method"):
            validate_config(config)

    def test_invalid_cash_target_raises(self) -> None:
        """cash_target < 0 或 >= 1 时抛异常。"""
        config = ETFRotationConfig(cash_target=-0.1)
        with pytest.raises(StrategySpecError, match="cash_target"):
            validate_config(config)

        config2 = ETFRotationConfig(cash_target=1.0)
        with pytest.raises(StrategySpecError, match="cash_target"):
            validate_config(config2)


# ---------------------------------------------------------------------------
# ETFRotation get_param_constraints
# ---------------------------------------------------------------------------


class TestETFRotationGetParamConstraints:
    def test_returns_constraints(self) -> None:
        """返回非空的 ParamConstraint 元组。"""
        constraints = get_param_constraints()
        assert isinstance(constraints, tuple)
        assert len(constraints) > 0
        for c in constraints:
            assert isinstance(c, ParamConstraint)

    def test_contains_top_k(self) -> None:
        """包含 top_k 约束。"""
        constraints = get_param_constraints()
        names = [c.name for c in constraints]
        assert "top_k" in names
