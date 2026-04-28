"""Tests for Regime Score Engine -- types, indicators, engine, and allocation.

覆盖:
- RegimeIndicator Protocol 合规性
- RegimeConfig / RegimeResult 类型定义
- TrendIndicator / VolatilityIndicator (Task 2)
- BreadthIndicator / MomentumIndicator (Task 3)
- RegimeScoreEngine (Task 4)
"""

from __future__ import annotations

import polars as pl
import pytest
from ditto_engine.alpha.builtins.regime import (
    BreadthIndicator,
    MomentumIndicator,
    RegimeConfig,
    RegimeIndicator,
    RegimeLabel,
    RegimeMethod,
    RegimeResult,
    RegimeScoreEngine,
    RegimeStage,
    TrendIndicator,
    VolatilityIndicator,
)
from ditto_engine.alpha.context import StrategyContext

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_context() -> StrategyContext:
    return StrategyContext()


# ---------------------------------------------------------------------------
# Task 1: 核心类型定义
# ---------------------------------------------------------------------------


class TestRegimeIndicatorProtocol:
    """RegimeIndicator Protocol 合规性测试."""

    def test_protocol_compliance(self) -> None:
        """自定义 indicator 满足 RegimeIndicator Protocol."""

        class DummyIndicator:
            name: str = "dummy"
            weight: float = 1.0

            def compute(self, frame: pl.DataFrame) -> float:
                return 0.5

        indicator: RegimeIndicator = DummyIndicator()
        assert indicator.name == "dummy"
        assert indicator.weight == 1.0
        assert indicator.compute(pl.DataFrame()) == 0.5


class TestRegimeConfig:
    """RegimeConfig 配置测试."""

    def test_default_values(self) -> None:
        """默认配置值."""
        config = RegimeConfig(indicators=())
        assert config.bull_threshold == 0.65
        assert config.bear_threshold == 0.35
        assert config.position_mapping == "stepped"
        assert config.bull_position == 1.0
        assert config.neutral_position == 0.7
        assert config.bear_position == 0.3
        assert config.default_regime == RegimeLabel.NEUTRAL

    def test_custom_values(self) -> None:
        """自定义配置值."""

        class DummyIndicator:
            name: str = "test"
            weight: float = 0.5

            def compute(self, frame: pl.DataFrame) -> float:
                return 0.8

        config = RegimeConfig(
            indicators=(DummyIndicator(),),
            bull_threshold=0.70,
            bear_threshold=0.30,
            position_mapping="linear",
            bull_position=0.9,
            neutral_position=0.5,
            bear_position=0.1,
            default_regime=RegimeLabel.BULL,
        )
        assert len(config.indicators) == 1
        assert config.bull_threshold == 0.70
        assert config.position_mapping == "linear"
        assert config.default_regime == RegimeLabel.BULL

    def test_frozen(self) -> None:
        """RegimeConfig 是 frozen dataclass."""
        config = RegimeConfig(indicators=())
        with pytest.raises(AttributeError):
            config.bull_threshold = 0.5  # type: ignore[misc]

    def test_indicators_tuple(self) -> None:
        """indicators 是 tuple，不可变."""

        class DummyIndicator:
            name: str = "d"
            weight: float = 1.0

            def compute(self, frame: pl.DataFrame) -> float:
                return 0.5

        config = RegimeConfig(
            indicators=(DummyIndicator(), DummyIndicator()),
        )
        assert len(config.indicators) == 2


class TestRegimeResult:
    """RegimeResult 结果数据类测试."""

    def test_creation(self) -> None:
        """正常创建 RegimeResult."""
        result = RegimeResult(
            score=75.0,
            label=RegimeLabel.BULL,
            position_ratio=1.0,
            indicator_values={"trend": 0.8, "volatility": 0.7},
        )
        assert result.score == 75.0
        assert result.label == RegimeLabel.BULL
        assert result.position_ratio == 1.0
        assert result.indicator_values["trend"] == 0.8

    def test_frozen(self) -> None:
        """RegimeResult 是 frozen dataclass."""
        result = RegimeResult(
            score=50.0,
            label=RegimeLabel.NEUTRAL,
            position_ratio=0.7,
            indicator_values={},
        )
        with pytest.raises(AttributeError):
            result.score = 60.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Task 2: TrendIndicator
# ---------------------------------------------------------------------------


class TestTrendIndicator:
    """TrendIndicator 趋势指标测试."""

    def test_bull_trend(self) -> None:
        """short_ma > long_ma * (1+threshold) → score = 1.0."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "ma_short": [1.12],
                "ma_long": [1.00],
            },
        )
        indicator = TrendIndicator(threshold=0.01)
        assert indicator.compute(frame) == 1.0

    def test_bear_trend(self) -> None:
        """short_ma < long_ma * (1-threshold) → score = 0.0."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "ma_short": [0.88],
                "ma_long": [1.00],
            },
        )
        indicator = TrendIndicator(threshold=0.01)
        assert indicator.compute(frame) == 0.0

    def test_neutral_trend(self) -> None:
        """ratio 在阈值范围内 → 线性插值 → 约 0.5."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "ma_short": [1.00],
                "ma_long": [1.00],
            },
        )
        indicator = TrendIndicator(threshold=0.01)
        # ratio = 1.0, lower=0.99, upper=1.01
        # (1.0 - 0.99) / (1.01 - 0.99) = 0.5
        assert indicator.compute(frame) == pytest.approx(0.5)

    def test_missing_columns(self) -> None:
        """缺失 MA 列 → 0.5."""
        frame = pl.DataFrame({"instrument_id": [10]})
        indicator = TrendIndicator()
        assert indicator.compute(frame) == 0.5

    def test_empty_frame(self) -> None:
        """空 frame → 0.5."""
        frame = pl.DataFrame(
            {
                "instrument_id": [],
                "ma_short": [],
                "ma_long": [],
            },
            schema={
                "instrument_id": pl.Int64,
                "ma_short": pl.Float64,
                "ma_long": pl.Float64,
            },
        )
        indicator = TrendIndicator()
        assert indicator.compute(frame) == 0.5

    def test_null_values(self) -> None:
        """MA 列含 null → 0.5."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "ma_short": [None],
                "ma_long": [1.00],
            },
            schema={
                "instrument_id": pl.Int64,
                "ma_short": pl.Float64,
                "ma_long": pl.Float64,
            },
        )
        indicator = TrendIndicator()
        assert indicator.compute(frame) == 0.5

    def test_custom_columns(self) -> None:
        """自定义列名."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "sma_5": [1.10],
                "sma_20": [1.00],
            },
        )
        indicator = TrendIndicator(
            short_ma_column="sma_5",
            long_ma_column="sma_20",
            threshold=0.01,
        )
        assert indicator.compute(frame) == 1.0

    def test_custom_threshold(self) -> None:
        """自定义阈值."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "ma_short": [1.05],
                "ma_long": [1.00],
            },
        )
        # threshold=0.10: upper=1.10, lower=0.90
        # ratio=1.05 → (1.05 - 0.90) / (1.10 - 0.90) = 0.75
        indicator = TrendIndicator(threshold=0.10)
        assert indicator.compute(frame) == pytest.approx(0.75)

    def test_default_attributes(self) -> None:
        """默认属性值."""
        indicator = TrendIndicator()
        assert indicator.name == "trend"
        assert indicator.weight == 1.0
        assert indicator.short_ma_column == "ma_short"
        assert indicator.long_ma_column == "ma_long"
        assert indicator.threshold == 0.01

    def test_frozen(self) -> None:
        """frozen dataclass."""
        indicator = TrendIndicator()
        with pytest.raises(AttributeError):
            indicator.name = "x"  # type: ignore[misc]

    def test_zero_long_ma(self) -> None:
        """long_ma = 0 → 0.5 (安全处理)."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "ma_short": [1.00],
                "ma_long": [0.00],
            },
        )
        indicator = TrendIndicator()
        assert indicator.compute(frame) == 0.5


# ---------------------------------------------------------------------------
# Task 2: VolatilityIndicator
# ---------------------------------------------------------------------------


class TestVolatilityIndicator:
    """VolatilityIndicator 波动率指标测试."""

    def test_low_volatility_bull(self) -> None:
        """vol < low_threshold → 1.0."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "volatility": [0.10],
            },
        )
        indicator = VolatilityIndicator()
        assert indicator.compute(frame) == 1.0

    def test_high_volatility_bear(self) -> None:
        """vol > high_threshold → 0.0."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "volatility": [0.40],
            },
        )
        indicator = VolatilityIndicator()
        assert indicator.compute(frame) == 0.0

    def test_mid_volatility(self) -> None:
        """vol 在阈值之间 → 线性插值."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "volatility": [0.225],
            },
        )
        indicator = VolatilityIndicator(
            low_vol_threshold=0.15,
            high_vol_threshold=0.30,
        )
        # (0.225 - 0.15) / (0.30 - 0.15) = 0.5 → 1.0 - 0.5 = 0.5
        assert indicator.compute(frame) == pytest.approx(0.5)

    def test_missing_column(self) -> None:
        """缺失波动率列 → 0.5."""
        frame = pl.DataFrame({"instrument_id": [10]})
        indicator = VolatilityIndicator()
        assert indicator.compute(frame) == 0.5

    def test_empty_frame(self) -> None:
        """空 frame → 0.5."""
        frame = pl.DataFrame(
            {"instrument_id": [], "volatility": []},
            schema={"instrument_id": pl.Int64, "volatility": pl.Float64},
        )
        indicator = VolatilityIndicator()
        assert indicator.compute(frame) == 0.5

    def test_null_values(self) -> None:
        """vol 列含 null → 0.5."""
        frame = pl.DataFrame(
            {"instrument_id": [10], "volatility": [None]},
            schema={"instrument_id": pl.Int64, "volatility": pl.Float64},
        )
        indicator = VolatilityIndicator()
        assert indicator.compute(frame) == 0.5

    def test_custom_column(self) -> None:
        """自定义波动率列名."""
        frame = pl.DataFrame(
            {"instrument_id": [10], "realized_vol": [0.10]},
        )
        indicator = VolatilityIndicator(volatility_column="realized_vol")
        assert indicator.compute(frame) == 1.0

    def test_default_attributes(self) -> None:
        """默认属性值."""
        indicator = VolatilityIndicator()
        assert indicator.name == "volatility"
        assert indicator.weight == 1.0
        assert indicator.low_vol_threshold == 0.15
        assert indicator.high_vol_threshold == 0.30

    def test_frozen(self) -> None:
        """frozen dataclass."""
        indicator = VolatilityIndicator()
        with pytest.raises(AttributeError):
            indicator.name = "x"  # type: ignore[misc]

    def test_exact_low_boundary(self) -> None:
        """vol 恰好等于 low_threshold → 1.0."""
        frame = pl.DataFrame(
            {"instrument_id": [10], "volatility": [0.15]},
        )
        indicator = VolatilityIndicator()
        assert indicator.compute(frame) == 1.0

    def test_exact_high_boundary(self) -> None:
        """vol 恰好等于 high_threshold → 0.0."""
        frame = pl.DataFrame(
            {"instrument_id": [10], "volatility": [0.30]},
        )
        indicator = VolatilityIndicator()
        assert indicator.compute(frame) == 0.0


# ---------------------------------------------------------------------------
# Task 2: RegimeStage 向后兼容验证
# ---------------------------------------------------------------------------


class TestRegimeStageBackwardCompat:
    """验证 RegimeStage 行为与原有测试完全一致."""

    def test_ma_cross_bull_via_stage(self, empty_context: StrategyContext) -> None:
        """RegimeStage MA_CROSS 行为不变."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "ma_short": [1.12],
                "ma_long": [1.00],
            },
        )
        stage = RegimeStage(method=RegimeMethod.MA_CROSS, threshold=0.01)
        result = stage.process(frame, empty_context)
        assert result["regime"][0] == RegimeLabel.BULL

    def test_volatility_bull_via_stage(self, empty_context: StrategyContext) -> None:
        """RegimeStage VOLATILITY_THRESHOLD 行为不变."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "volatility": [0.10],
            },
        )
        stage = RegimeStage(method=RegimeMethod.VOLATILITY_THRESHOLD)
        result = stage.process(frame, empty_context)
        assert result["regime"][0] == RegimeLabel.BULL

    def test_indicator_matches_stage_ma_cross(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """TrendIndicator 与 RegimeStage MA_CROSS 行为一致."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "ma_short": [1.12],
                "ma_long": [1.00],
            },
        )
        threshold = 0.01
        stage = RegimeStage(method=RegimeMethod.MA_CROSS, threshold=threshold)
        indicator = TrendIndicator(threshold=threshold)

        stage_result = stage.process(frame, empty_context)
        indicator_result = indicator.compute(frame)

        # Stage 给出 BULL → indicator 给出 1.0
        assert stage_result["regime"][0] == RegimeLabel.BULL
        assert indicator_result == 1.0

    def test_indicator_matches_stage_volatility(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """VolatilityIndicator 与 RegimeStage VOLATILITY_THRESHOLD 行为一致."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "volatility": [0.10],
            },
        )
        stage = RegimeStage(method=RegimeMethod.VOLATILITY_THRESHOLD)
        indicator = VolatilityIndicator()

        stage_result = stage.process(frame, empty_context)
        indicator_result = indicator.compute(frame)

        # Stage 给出 BULL → indicator 给出 1.0
        assert stage_result["regime"][0] == RegimeLabel.BULL
        assert indicator_result == 1.0


# ---------------------------------------------------------------------------
# Task 3: BreadthIndicator
# ---------------------------------------------------------------------------


class TestBreadthIndicator:
    """BreadthIndicator 市场广度指标测试."""

    def test_all_up(self) -> None:
        """全部上涨 → 1.0."""
        frame = pl.DataFrame(
            {"instrument_id": [10], "up_count": [100], "down_count": [0]},
        )
        indicator = BreadthIndicator()
        assert indicator.compute(frame) == 1.0

    def test_all_down(self) -> None:
        """全部下跌 → 0.0."""
        frame = pl.DataFrame(
            {"instrument_id": [10], "up_count": [0], "down_count": [100]},
        )
        indicator = BreadthIndicator()
        assert indicator.compute(frame) == 0.0

    def test_balanced(self) -> None:
        """涨跌各半 → 0.5."""
        frame = pl.DataFrame(
            {"instrument_id": [10], "up_count": [50], "down_count": [50]},
        )
        indicator = BreadthIndicator()
        assert indicator.compute(frame) == pytest.approx(0.5)

    def test_missing_columns(self) -> None:
        """缺失列 → 0.5."""
        frame = pl.DataFrame({"instrument_id": [10]})
        indicator = BreadthIndicator()
        assert indicator.compute(frame) == 0.5

    def test_empty_frame(self) -> None:
        """空 frame → 0.5."""
        frame = pl.DataFrame(
            {"instrument_id": [], "up_count": [], "down_count": []},
            schema={
                "instrument_id": pl.Int64,
                "up_count": pl.Float64,
                "down_count": pl.Float64,
            },
        )
        indicator = BreadthIndicator()
        assert indicator.compute(frame) == 0.5

    def test_null_values(self) -> None:
        """含 null → 0.5."""
        frame = pl.DataFrame(
            {"instrument_id": [10], "up_count": [None], "down_count": [50]},
            schema={
                "instrument_id": pl.Int64,
                "up_count": pl.Float64,
                "down_count": pl.Float64,
            },
        )
        indicator = BreadthIndicator()
        assert indicator.compute(frame) == 0.5

    def test_zero_total(self) -> None:
        """up + down = 0 → 0.5."""
        frame = pl.DataFrame(
            {"instrument_id": [10], "up_count": [0], "down_count": [0]},
        )
        indicator = BreadthIndicator()
        assert indicator.compute(frame) == 0.5

    def test_default_attributes(self) -> None:
        """默认属性值."""
        indicator = BreadthIndicator()
        assert indicator.name == "breadth"
        assert indicator.weight == 1.0
        assert indicator.up_count_column == "up_count"
        assert indicator.down_count_column == "down_count"

    def test_frozen(self) -> None:
        """frozen dataclass."""
        indicator = BreadthIndicator()
        with pytest.raises(AttributeError):
            indicator.name = "x"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Task 3: MomentumIndicator
# ---------------------------------------------------------------------------


class TestMomentumIndicator:
    """MomentumIndicator 动量指标测试."""

    def test_strong_upward(self) -> None:
        """大幅上涨 → 接近 1.0."""
        frame = pl.DataFrame(
            {"instrument_id": [10, 10], "close": [100.0, 115.0]},
        )
        indicator = MomentumIndicator(lookback=1)
        # change = (115-100)/100 = 0.15
        # mapped: (0.15+0.10)/0.20 = 1.25 → clamped to 1.0
        assert indicator.compute(frame) == 1.0

    def test_strong_downward(self) -> None:
        """大幅下跌 → 接近 0.0."""
        frame = pl.DataFrame(
            {"instrument_id": [10, 10], "close": [100.0, 85.0]},
        )
        indicator = MomentumIndicator(lookback=1)
        # change = (85-100)/100 = -0.15
        # mapped: (-0.15+0.10)/0.20 = -0.25 → clamped to 0.0
        assert indicator.compute(frame) == 0.0

    def test_flat(self) -> None:
        """价格不变 → 0.5."""
        frame = pl.DataFrame(
            {"instrument_id": [10, 10], "close": [100.0, 100.0]},
        )
        indicator = MomentumIndicator(lookback=1)
        # change = 0.0, mapped: (0.0+0.10)/0.20 = 0.5
        assert indicator.compute(frame) == pytest.approx(0.5)

    def test_missing_close_column(self) -> None:
        """缺失 close 列 → 0.5."""
        frame = pl.DataFrame({"instrument_id": [10]})
        indicator = MomentumIndicator()
        assert indicator.compute(frame) == 0.5

    def test_empty_frame(self) -> None:
        """空 frame → 0.5."""
        frame = pl.DataFrame(
            {"instrument_id": [], "close": []},
            schema={"instrument_id": pl.Int64, "close": pl.Float64},
        )
        indicator = MomentumIndicator()
        assert indicator.compute(frame) == 0.5

    def test_single_row(self) -> None:
        """单行 frame → 0.5 (至少需要 2 个值)."""
        frame = pl.DataFrame(
            {"instrument_id": [10], "close": [100.0]},
        )
        indicator = MomentumIndicator()
        assert indicator.compute(frame) == 0.5

    def test_default_attributes(self) -> None:
        """默认属性值."""
        indicator = MomentumIndicator()
        assert indicator.name == "momentum"
        assert indicator.weight == 1.0
        assert indicator.lookback == 20
        assert indicator.close_column == "close"

    def test_frozen(self) -> None:
        """frozen dataclass."""
        indicator = MomentumIndicator()
        with pytest.raises(AttributeError):
            indicator.name = "x"  # type: ignore[misc]

    def test_zero_past_price(self) -> None:
        """过去价格为 0 → 0.5 (安全处理)."""
        frame = pl.DataFrame(
            {"instrument_id": [10, 10], "close": [0.0, 100.0]},
        )
        indicator = MomentumIndicator(lookback=1)
        assert indicator.compute(frame) == 0.5


# ---------------------------------------------------------------------------
# Task 4: RegimeScoreEngine
# ---------------------------------------------------------------------------


class TestRegimeScoreEngine:
    """RegimeScoreEngine 评分引擎测试."""

    def test_bull_score(self) -> None:
        """多指标综合评分 → BULL."""
        config = RegimeConfig(
            indicators=(
                TrendIndicator(threshold=0.01),
                VolatilityIndicator(),
            ),
        )
        engine = RegimeScoreEngine(config=config)

        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "ma_short": [1.12],
                "ma_long": [1.00],
                "volatility": [0.10],
            },
        )
        result = engine.score(frame)
        # trend=1.0, volatility=1.0 → avg=1.0 → score=100
        assert result.score == 100.0
        assert result.label == RegimeLabel.BULL
        assert result.position_ratio == 1.0  # stepped BULL

    def test_bear_score(self) -> None:
        """多指标综合评分 → BEAR."""
        config = RegimeConfig(
            indicators=(
                TrendIndicator(threshold=0.01),
                VolatilityIndicator(),
            ),
        )
        engine = RegimeScoreEngine(config=config)

        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "ma_short": [0.88],
                "ma_long": [1.00],
                "volatility": [0.40],
            },
        )
        result = engine.score(frame)
        # trend=0.0, volatility=0.0 → avg=0.0 → score=0
        assert result.score == 0.0
        assert result.label == RegimeLabel.BEAR
        assert result.position_ratio == 0.3  # stepped BEAR

    def test_neutral_score(self) -> None:
        """混合指标 → NEUTRAL."""
        config = RegimeConfig(
            indicators=(
                TrendIndicator(threshold=0.01),
                VolatilityIndicator(),
            ),
        )
        engine = RegimeScoreEngine(config=config)

        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "ma_short": [1.00],
                "ma_long": [1.00],
                "volatility": [0.225],
            },
        )
        result = engine.score(frame)
        # trend≈0.5, volatility≈0.5 → avg≈0.5 → score≈50
        assert 40 < result.score < 60
        assert result.label == RegimeLabel.NEUTRAL
        assert result.position_ratio == 0.7  # stepped NEUTRAL

    def test_linear_position_mapping(self) -> None:
        """linear 映射: position_ratio = score / 100."""
        config = RegimeConfig(
            indicators=(TrendIndicator(threshold=0.01),),
            position_mapping="linear",
        )
        engine = RegimeScoreEngine(config=config)

        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "ma_short": [1.00],
                "ma_long": [1.00],
            },
        )
        result = engine.score(frame)
        # trend=0.5 → score=50 → linear: 50/100 = 0.5
        assert result.position_ratio == pytest.approx(0.5)

    def test_weighted_indicators(self) -> None:
        """不同权重的指标."""

        class FixedIndicator:
            def __init__(self, name: str, value: float, weight: float) -> None:
                self._name = name
                self._value = value
                self.weight = weight

            @property
            def name(self) -> str:
                return self._name

            def compute(self, frame: pl.DataFrame) -> float:
                return self._value

        config = RegimeConfig(
            indicators=(
                FixedIndicator("a", 1.0, 3.0),
                FixedIndicator("b", 0.0, 1.0),
            ),
        )
        engine = RegimeScoreEngine(config=config)
        result = engine.score(pl.DataFrame({"instrument_id": [10]}))

        # weighted: (3.0*1.0 + 1.0*0.0) / (3.0 + 1.0) = 0.75 → score=75
        assert result.score == 75.0
        assert result.indicator_values["a"] == 1.0
        assert result.indicator_values["b"] == 0.0

    def test_empty_indicators(self) -> None:
        """无指标 → score=50, NEUTRAL."""

        class FixedIndicator:
            name: str = "fixed"
            weight: float = 1.0

            def compute(self, frame: pl.DataFrame) -> float:
                return 0.5

        config = RegimeConfig(indicators=())
        engine = RegimeScoreEngine(config=config)
        result = engine.score(pl.DataFrame({"instrument_id": [10]}))
        assert result.score == 50.0
        assert result.label == RegimeLabel.NEUTRAL

    def test_indicator_values_populated(self) -> None:
        """indicator_values 包含各指标原始值."""
        config = RegimeConfig(
            indicators=(
                TrendIndicator(threshold=0.01),
                VolatilityIndicator(),
            ),
        )
        engine = RegimeScoreEngine(config=config)

        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "ma_short": [1.12],
                "ma_long": [1.00],
                "volatility": [0.10],
            },
        )
        result = engine.score(frame)
        assert "trend" in result.indicator_values
        assert "volatility" in result.indicator_values
        assert result.indicator_values["trend"] == 1.0
        assert result.indicator_values["volatility"] == 1.0

    def test_frozen(self) -> None:
        """frozen dataclass."""
        engine = RegimeScoreEngine(config=RegimeConfig(indicators=()))
        with pytest.raises(AttributeError):
            engine.config = RegimeConfig(indicators=())  # type: ignore[misc]

    def test_custom_thresholds(self) -> None:
        """自定义阈值."""
        config = RegimeConfig(
            indicators=(TrendIndicator(threshold=0.01),),
            bull_threshold=0.80,
            bear_threshold=0.20,
        )
        engine = RegimeScoreEngine(config=config)

        # trend=0.5 → score=50, 50/100=0.5, 0.5 < 0.80 → not BULL
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "ma_short": [1.00],
                "ma_long": [1.00],
            },
        )
        result = engine.score(frame)
        assert result.label == RegimeLabel.NEUTRAL
