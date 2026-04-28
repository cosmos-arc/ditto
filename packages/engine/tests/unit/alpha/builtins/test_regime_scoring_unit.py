"""Tests for RegimeScoringStep -- DecisionStage that delegates to RegimeScoreEngine.

覆盖:
- 正常评分: frame 包含 signal 列，调用后新增 regime_score/regime_label/position_ratio
- 空 frame: 原样返回（不调用 engine）
- 缺列 fallback: frame 无 indicator 所需列，engine 内部 fallback 返回 0.5
- scalar 列验证: 所有行的 regime_score/label/position_ratio 相同
- linear 映射: position_mapping="linear" 时 position_ratio 为线性映射
- frozen dataclass: 确认 frozen=True
"""

from __future__ import annotations

import polars as pl
import pytest
from ditto_engine.alpha.builtins.regime import (
    RegimeConfig,
    TrendIndicator,
)
from ditto_engine.alpha.builtins.regime_scoring import RegimeScoringStep
from ditto_engine.alpha.context import StrategyContext

# Note: TrendIndicator satisfies RegimeIndicator Protocol (structural subtyping)
# pyright reports false positive for frozen dataclass vs Protocol writable attributes

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_context() -> StrategyContext:
    return StrategyContext()


@pytest.fixture
def bull_config() -> RegimeConfig:
    """TrendIndicator 在 bull 条件下的配置."""
    return RegimeConfig(
        indicators=(TrendIndicator(threshold=0.01),),
    )


# ---------------------------------------------------------------------------
# Test 1: 正常评分
# ---------------------------------------------------------------------------


class TestRegimeScoringStepNormal:
    """正常评分 — frame 包含 indicator 所需列."""

    def test_adds_three_columns(
        self,
        empty_context: StrategyContext,
        bull_config: RegimeConfig,
    ) -> None:
        """调用后新增 regime_score / regime_label / position_ratio 三列."""
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "ma_short": [1.12, 1.12],
                "ma_long": [1.00, 1.00],
            },
        )
        step = RegimeScoringStep(config=bull_config)
        result = step.process(frame, empty_context)

        assert "regime_score" in result.columns
        assert "regime_label" in result.columns
        assert "position_ratio" in result.columns

    def test_score_is_float_0_to_100(
        self,
        empty_context: StrategyContext,
        bull_config: RegimeConfig,
    ) -> None:
        """regime_score 为 0-100 之间的 float."""
        frame = pl.DataFrame(
            {
                "instrument_id": [1],
                "ma_short": [1.12],
                "ma_long": [1.00],
            },
        )
        step = RegimeScoringStep(config=bull_config)
        result = step.process(frame, empty_context)

        score = result["regime_score"][0]
        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_label_is_regime_label_string(
        self,
        empty_context: StrategyContext,
        bull_config: RegimeConfig,
    ) -> None:
        """regime_label 为有效的 RegimeLabel 字符串值."""
        frame = pl.DataFrame(
            {
                "instrument_id": [1],
                "ma_short": [1.12],
                "ma_long": [1.00],
            },
        )
        step = RegimeScoringStep(config=bull_config)
        result = step.process(frame, empty_context)

        label = result["regime_label"][0]
        assert label in ("bull", "bear", "neutral")

    def test_position_ratio_0_to_1(
        self,
        empty_context: StrategyContext,
        bull_config: RegimeConfig,
    ) -> None:
        """position_ratio 为 0-1 之间的 float."""
        frame = pl.DataFrame(
            {
                "instrument_id": [1],
                "ma_short": [1.12],
                "ma_long": [1.00],
            },
        )
        step = RegimeScoringStep(config=bull_config)
        result = step.process(frame, empty_context)

        ratio = result["position_ratio"][0]
        assert isinstance(ratio, float)
        assert 0.0 <= ratio <= 1.0

    def test_bull_conditions(
        self,
        empty_context: StrategyContext,
        bull_config: RegimeConfig,
    ) -> None:
        """bull 条件下 score=100, label=bull, position_ratio=1.0."""
        frame = pl.DataFrame(
            {
                "instrument_id": [1],
                "ma_short": [1.12],
                "ma_long": [1.00],
            },
        )
        step = RegimeScoringStep(config=bull_config)
        result = step.process(frame, empty_context)

        assert result["regime_score"][0] == 100.0
        assert result["regime_label"][0] == "bull"
        assert result["position_ratio"][0] == 1.0

    def test_preserves_original_columns(
        self,
        empty_context: StrategyContext,
        bull_config: RegimeConfig,
    ) -> None:
        """原始列保持不变."""
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "weight": [0.5, 0.5],
                "ma_short": [1.12, 1.12],
                "ma_long": [1.00, 1.00],
            },
        )
        step = RegimeScoringStep(config=bull_config)
        result = step.process(frame, empty_context)

        assert result["instrument_id"].to_list() == [1, 2]
        assert result["weight"].to_list() == [0.5, 0.5]


# ---------------------------------------------------------------------------
# Test 2: 空 frame
# ---------------------------------------------------------------------------


class TestRegimeScoringStepEmptyFrame:
    """空 frame 原样返回."""

    def test_empty_frame_returns_as_is(
        self,
        empty_context: StrategyContext,
        bull_config: RegimeConfig,
    ) -> None:
        """空 frame 原样返回，不添加列."""
        frame = pl.DataFrame(
            {"instrument_id": [], "ma_short": [], "ma_long": []},
            schema={
                "instrument_id": pl.Int64,
                "ma_short": pl.Float64,
                "ma_long": pl.Float64,
            },
        )
        step = RegimeScoringStep(config=bull_config)
        result = step.process(frame, empty_context)

        assert result.is_empty()
        # 不添加 regime 列
        assert "regime_score" not in result.columns


# ---------------------------------------------------------------------------
# Test 3: 缺列 fallback
# ---------------------------------------------------------------------------


class TestRegimeScoringStepMissingColumns:
    """frame 无 indicator 所需列时 engine fallback 返回 0.5."""

    def test_missing_indicator_columns_fallback(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """frame 无 ma_short/ma_long → TrendIndicator fallback 0.5 → score=50."""
        config = RegimeConfig(
            indicators=(TrendIndicator(threshold=0.01),),
        )
        frame = pl.DataFrame(
            {"instrument_id": [1], "signal_value": [0.5]},
        )
        step = RegimeScoringStep(config=config)
        result = step.process(frame, empty_context)

        # TrendIndicator 缺列返回 0.5 → score=50.0, label=neutral
        assert result["regime_score"][0] == 50.0
        assert result["regime_label"][0] == "neutral"


# ---------------------------------------------------------------------------
# Test 4: scalar 列验证
# ---------------------------------------------------------------------------


class TestRegimeScoringStepScalarColumns:
    """所有行的 regime_score / regime_label / position_ratio 相同."""

    def test_all_rows_same_score(
        self,
        empty_context: StrategyContext,
        bull_config: RegimeConfig,
    ) -> None:
        """多行 frame 的 regime_score 完全一致."""
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "ma_short": [1.12, 1.05, 0.95],
                "ma_long": [1.00, 1.00, 1.00],
            },
        )
        step = RegimeScoringStep(config=bull_config)
        result = step.process(frame, empty_context)

        scores = result["regime_score"].to_list()
        assert len(set(scores)) == 1

    def test_all_rows_same_label(
        self,
        empty_context: StrategyContext,
        bull_config: RegimeConfig,
    ) -> None:
        """多行 frame 的 regime_label 完全一致."""
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "ma_short": [1.12, 1.05, 0.95],
                "ma_long": [1.00, 1.00, 1.00],
            },
        )
        step = RegimeScoringStep(config=bull_config)
        result = step.process(frame, empty_context)

        labels = result["regime_label"].to_list()
        assert len(set(labels)) == 1

    def test_all_rows_same_position_ratio(
        self,
        empty_context: StrategyContext,
        bull_config: RegimeConfig,
    ) -> None:
        """多行 frame 的 position_ratio 完全一致."""
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "ma_short": [1.12, 1.05, 0.95],
                "ma_long": [1.00, 1.00, 1.00],
            },
        )
        step = RegimeScoringStep(config=bull_config)
        result = step.process(frame, empty_context)

        ratios = result["position_ratio"].to_list()
        assert len(set(ratios)) == 1


# ---------------------------------------------------------------------------
# Test 5: linear 映射
# ---------------------------------------------------------------------------


class TestRegimeScoringStepLinearMapping:
    """RegimeConfig(position_mapping="linear") 时 position_ratio 为线性映射."""

    def test_linear_position_ratio(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """linear 映射: position_ratio = score / 100."""
        config = RegimeConfig(
            indicators=(TrendIndicator(threshold=0.01),),
            position_mapping="linear",
        )
        # ratio=1.0 → trend=0.5 → score=50 → position_ratio=0.5
        frame = pl.DataFrame(
            {
                "instrument_id": [1],
                "ma_short": [1.00],
                "ma_long": [1.00],
            },
        )
        step = RegimeScoringStep(config=config)
        result = step.process(frame, empty_context)

        assert result["regime_score"][0] == pytest.approx(50.0)
        assert result["position_ratio"][0] == pytest.approx(0.5)

    def test_linear_bull_mapping(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """linear 映射下 bull score=100 → position_ratio=1.0."""
        config = RegimeConfig(
            indicators=(TrendIndicator(threshold=0.01),),
            position_mapping="linear",
        )
        frame = pl.DataFrame(
            {
                "instrument_id": [1],
                "ma_short": [1.12],
                "ma_long": [1.00],
            },
        )
        step = RegimeScoringStep(config=config)
        result = step.process(frame, empty_context)

        assert result["regime_score"][0] == 100.0
        assert result["position_ratio"][0] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Test 6: frozen dataclass
# ---------------------------------------------------------------------------


class TestRegimeScoringStepFrozen:
    """确认 RegimeScoringStep 是 frozen dataclass."""

    def test_frozen(self, bull_config: RegimeConfig) -> None:
        """frozen dataclass 不可修改属性."""
        step = RegimeScoringStep(config=bull_config)
        with pytest.raises(AttributeError):
            step.config = RegimeConfig(indicators=())  # type: ignore[misc]
