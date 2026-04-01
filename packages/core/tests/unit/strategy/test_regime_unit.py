"""Tests for RegimeStage -- 市场状态检测 DecisionStage.

Covers MA_CROSS 和 VOLATILITY_THRESHOLD 两种方法的正常运行、
自定义参数、frozen dataclass 约束以及边界条件。
"""

from __future__ import annotations

import polars as pl
import pytest
from ditto_engine.strategy.builtins.regime import (
    RegimeLabel,
    RegimeMethod,
    RegimeStage,
)
from ditto_engine.strategy.context import StrategyContext

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_context() -> StrategyContext:
    return StrategyContext()


# ---------------------------------------------------------------------------
# RegimeStage -- MA_CROSS
# ---------------------------------------------------------------------------


class TestRegimeStage:
    """RegimeStage 正常运行测试。"""

    def test_ma_cross_bull(self, empty_context: StrategyContext) -> None:
        """MA_CROSS 方法：short_ma > long_ma * (1+threshold) 时标记为 bull。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12],
                "ma_short": [1.12, 1.05, 1.20],
                "ma_long": [1.00, 1.00, 1.00],
            }
        )
        stage = RegimeStage(method=RegimeMethod.MA_CROSS, threshold=0.01)
        result = stage.process(frame, empty_context)
        regimes = result["regime"].to_list()
        # ratio = 1.12/1.00=1.12 > 1.01 -> bull
        assert regimes[0] == RegimeLabel.BULL
        # ratio = 1.05/1.00=1.05 > 1.01 -> bull
        assert regimes[1] == RegimeLabel.BULL
        # ratio = 1.20/1.00=1.20 > 1.01 -> bull
        assert regimes[2] == RegimeLabel.BULL

    def test_ma_cross_bear(self, empty_context: StrategyContext) -> None:
        """MA_CROSS 方法：short_ma < long_ma * (1-threshold) 时标记为 bear。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11],
                "ma_short": [0.88, 0.95],
                "ma_long": [1.00, 1.00],
            }
        )
        stage = RegimeStage(method=RegimeMethod.MA_CROSS, threshold=0.01)
        result = stage.process(frame, empty_context)
        regimes = result["regime"].to_list()
        # ratio = 0.88/1.00=0.88 < 0.99 -> bear
        assert regimes[0] == RegimeLabel.BEAR
        # ratio = 0.95/1.00=0.95 < 0.99 -> bear
        assert regimes[1] == RegimeLabel.BEAR

    def test_ma_cross_neutral(self, empty_context: StrategyContext) -> None:
        """MA_CROSS 方法：ratio 在阈值范围内时标记为 neutral。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12],
                "ma_short": [1.005, 1.00, 0.995],
                "ma_long": [1.00, 1.00, 1.00],
            }
        )
        stage = RegimeStage(method=RegimeMethod.MA_CROSS, threshold=0.01)
        result = stage.process(frame, empty_context)
        regimes = result["regime"].to_list()
        # ratio = 1.005, within [0.99, 1.01] -> neutral
        assert regimes[0] == RegimeLabel.NEUTRAL
        # ratio = 1.00, within [0.99, 1.01] -> neutral
        assert regimes[1] == RegimeLabel.NEUTRAL
        # ratio = 0.995, within [0.99, 1.01] -> neutral
        assert regimes[2] == RegimeLabel.NEUTRAL

    def test_ma_cross_custom_columns(self, empty_context: StrategyContext) -> None:
        """MA_CROSS 方法：使用自定义列名。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "sma_5": [1.10],
                "sma_20": [1.00],
            }
        )
        stage = RegimeStage(
            method=RegimeMethod.MA_CROSS,
            short_ma_column="sma_5",
            long_ma_column="sma_20",
        )
        result = stage.process(frame, empty_context)
        assert result["regime"][0] == RegimeLabel.BULL

    def test_ma_cross_custom_threshold(self, empty_context: StrategyContext) -> None:
        """MA_CROSS 方法：使用自定义阈值。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11],
                "ma_short": [1.05, 0.95],
                "ma_long": [1.00, 1.00],
            }
        )
        # threshold=0.10: bull if ratio > 1.10, bear if ratio < 0.90
        stage = RegimeStage(method=RegimeMethod.MA_CROSS, threshold=0.10)
        result = stage.process(frame, empty_context)
        regimes = result["regime"].to_list()
        # ratio = 1.05, within [0.90, 1.10] -> neutral
        assert regimes[0] == RegimeLabel.NEUTRAL
        # ratio = 0.95, within [0.90, 1.10] -> neutral
        assert regimes[1] == RegimeLabel.NEUTRAL

    def test_volatility_bull(self, empty_context: StrategyContext) -> None:
        """VOLATILITY_THRESHOLD 方法：vol < low_threshold 时标记为 bull。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11],
                "volatility": [0.10, 0.14],
            }
        )
        stage = RegimeStage(method=RegimeMethod.VOLATILITY_THRESHOLD)
        result = stage.process(frame, empty_context)
        regimes = result["regime"].to_list()
        assert regimes[0] == RegimeLabel.BULL
        assert regimes[1] == RegimeLabel.BULL

    def test_volatility_bear(self, empty_context: StrategyContext) -> None:
        """VOLATILITY_THRESHOLD 方法：vol > high_threshold 时标记为 bear。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11],
                "volatility": [0.31, 0.50],
            }
        )
        stage = RegimeStage(method=RegimeMethod.VOLATILITY_THRESHOLD)
        result = stage.process(frame, empty_context)
        regimes = result["regime"].to_list()
        assert regimes[0] == RegimeLabel.BEAR
        assert regimes[1] == RegimeLabel.BEAR

    def test_volatility_neutral(self, empty_context: StrategyContext) -> None:
        """VOLATILITY_THRESHOLD 方法：vol 在阈值之间时标记为 neutral。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11],
                "volatility": [0.15, 0.30],
            }
        )
        stage = RegimeStage(method=RegimeMethod.VOLATILITY_THRESHOLD)
        result = stage.process(frame, empty_context)
        regimes = result["regime"].to_list()
        # vol=0.15 >= low_vol_threshold=0.15 -> neutral (not < low)
        assert regimes[0] == RegimeLabel.NEUTRAL
        # vol=0.30 <= high_vol_threshold=0.30 -> neutral (not > high)
        assert regimes[1] == RegimeLabel.NEUTRAL

    def test_volatility_custom_columns(self, empty_context: StrategyContext) -> None:
        """VOLATILITY_THRESHOLD 方法：使用自定义列名。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "realized_vol": [0.10],
            }
        )
        stage = RegimeStage(
            method=RegimeMethod.VOLATILITY_THRESHOLD,
            volatility_column="realized_vol",
        )
        result = stage.process(frame, empty_context)
        assert result["regime"][0] == RegimeLabel.BULL

    def test_volatility_custom_thresholds(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """VOLATILITY_THRESHOLD 方法：使用自定义阈值。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12],
                "volatility": [0.05, 0.20, 0.40],
            }
        )
        stage = RegimeStage(
            method=RegimeMethod.VOLATILITY_THRESHOLD,
            low_vol_threshold=0.10,
            high_vol_threshold=0.30,
        )
        result = stage.process(frame, empty_context)
        regimes = result["regime"].to_list()
        assert regimes[0] == RegimeLabel.BULL
        assert regimes[1] == RegimeLabel.NEUTRAL
        assert regimes[2] == RegimeLabel.BEAR

    def test_frozen(self) -> None:
        """RegimeStage 是 frozen dataclass，不可修改属性。"""
        stage = RegimeStage()
        with pytest.raises(AttributeError):
            stage.method = RegimeMethod.VOLATILITY_THRESHOLD  # type: ignore[misc]


# ---------------------------------------------------------------------------
# RegimeStage 边界条件测试
# ---------------------------------------------------------------------------


class TestRegimeStageBoundary:
    """RegimeStage 边界条件测试。"""

    def test_empty_frame(self, empty_context: StrategyContext) -> None:
        """空 frame：返回空 frame，带 regime 列。"""
        empty_frame = pl.DataFrame(
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
        stage = RegimeStage(method=RegimeMethod.MA_CROSS)
        result = stage.process(empty_frame, empty_context)
        assert result.is_empty()
        assert "regime" in result.columns

    def test_missing_ma_columns(self, empty_context: StrategyContext) -> None:
        """MA_CROSS 方法：缺少 MA 列时填充 default_regime。"""
        frame = pl.DataFrame({"instrument_id": [10, 11]})
        stage = RegimeStage(method=RegimeMethod.MA_CROSS)
        result = stage.process(frame, empty_context)
        regimes = result["regime"].to_list()
        assert regimes[0] == RegimeLabel.NEUTRAL
        assert regimes[1] == RegimeLabel.NEUTRAL

    def test_missing_volatility_column(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """VOLATILITY_THRESHOLD 方法：缺少 volatility 列时填充 default_regime。"""
        frame = pl.DataFrame({"instrument_id": [10, 11]})
        stage = RegimeStage(method=RegimeMethod.VOLATILITY_THRESHOLD)
        result = stage.process(frame, empty_context)
        regimes = result["regime"].to_list()
        assert regimes[0] == RegimeLabel.NEUTRAL
        assert regimes[1] == RegimeLabel.NEUTRAL

    def test_null_values_ma(self, empty_context: StrategyContext) -> None:
        """MA_CROSS 方法：MA 列包含 null 时，对应行标记为 default_regime。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12],
                "ma_short": [1.10, None, 0.88],
                "ma_long": [1.00, 1.00, None],
            }
        )
        stage = RegimeStage(method=RegimeMethod.MA_CROSS, threshold=0.01)
        result = stage.process(frame, empty_context)
        regimes = result["regime"].to_list()
        # A: ratio=1.10 > 1.01 -> bull
        assert regimes[0] == RegimeLabel.BULL
        # B: ma_short is null -> neutral (otherwise fallback)
        assert regimes[1] == RegimeLabel.NEUTRAL
        # C: ma_long is null -> neutral (otherwise fallback)
        assert regimes[2] == RegimeLabel.NEUTRAL

    def test_null_values_volatility(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """VOLATILITY_THRESHOLD 方法：vol 列含 null 时，对应行标记为 default_regime。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12],
                "volatility": [0.10, None, 0.40],
            }
        )
        stage = RegimeStage(method=RegimeMethod.VOLATILITY_THRESHOLD)
        result = stage.process(frame, empty_context)
        regimes = result["regime"].to_list()
        # A: vol=0.10 < 0.15 -> bull
        assert regimes[0] == RegimeLabel.BULL
        # B: null -> neutral (otherwise fallback)
        assert regimes[1] == RegimeLabel.NEUTRAL
        # C: vol=0.40 > 0.30 -> bear
        assert regimes[2] == RegimeLabel.BEAR

    def test_single_row(self, empty_context: StrategyContext) -> None:
        """单行 frame：正确识别 regime。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "ma_short": [1.05],
                "ma_long": [1.00],
            }
        )
        stage = RegimeStage(method=RegimeMethod.MA_CROSS, threshold=0.01)
        result = stage.process(frame, empty_context)
        assert result.shape == (1, 4)
        assert result["regime"][0] == RegimeLabel.BULL

    def test_multi_instrument(self, empty_context: StrategyContext) -> None:
        """多标的 frame：所有标的获得相同 regime（市场级判断）。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3, 6],
                "ma_short": [1.12, 1.12, 1.12, 1.12],
                "ma_long": [1.00, 1.00, 1.00, 1.00],
            }
        )
        stage = RegimeStage(method=RegimeMethod.MA_CROSS, threshold=0.01)
        result = stage.process(frame, empty_context)
        regimes = result["regime"].to_list()
        assert all(r == RegimeLabel.BULL for r in regimes)

    def test_custom_default_regime(self, empty_context: StrategyContext) -> None:
        """自定义 default_regime：缺失列时填充指定的默认值。"""
        frame = pl.DataFrame({"instrument_id": [10]})
        stage = RegimeStage(
            method=RegimeMethod.MA_CROSS,
            default_regime=RegimeLabel.BULL,
        )
        result = stage.process(frame, empty_context)
        assert result["regime"][0] == RegimeLabel.BULL

    def test_custom_output_column(self, empty_context: StrategyContext) -> None:
        """自定义 output_column：输出到指定列名。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "ma_short": [1.05],
                "ma_long": [1.00],
            }
        )
        stage = RegimeStage(
            method=RegimeMethod.MA_CROSS,
            output_column="market_regime",
        )
        result = stage.process(frame, empty_context)
        assert "market_regime" in result.columns
        assert "regime" not in result.columns
        assert result["market_regime"][0] == RegimeLabel.BULL

    def test_ma_cross_exact_boundary_bull(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """MA_CROSS 方法：ratio 恰好等于 1+threshold 时为 neutral（不含边界）。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "ma_short": [1.01],
                "ma_long": [1.00],
            }
        )
        stage = RegimeStage(method=RegimeMethod.MA_CROSS, threshold=0.01)
        result = stage.process(frame, empty_context)
        # ratio = 1.01 == 1+threshold -> not > -> neutral
        assert result["regime"][0] == RegimeLabel.NEUTRAL

    def test_ma_cross_exact_boundary_bear(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """MA_CROSS 方法：ratio 恰好等于 1-threshold 时为 neutral（不含边界）。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "ma_short": [0.99],
                "ma_long": [1.00],
            }
        )
        stage = RegimeStage(method=RegimeMethod.MA_CROSS, threshold=0.01)
        result = stage.process(frame, empty_context)
        # ratio = 0.99 == 1-threshold -> not < -> neutral
        assert result["regime"][0] == RegimeLabel.NEUTRAL

    def test_volatility_exact_boundary_low(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """VOLATILITY_THRESHOLD 方法：vol 恰好等于 low_threshold 时为 neutral。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "volatility": [0.15],
            }
        )
        stage = RegimeStage(method=RegimeMethod.VOLATILITY_THRESHOLD)
        result = stage.process(frame, empty_context)
        # vol=0.15 == low_vol_threshold -> not < -> neutral
        assert result["regime"][0] == RegimeLabel.NEUTRAL

    def test_volatility_exact_boundary_high(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """VOLATILITY_THRESHOLD 方法：vol 恰好等于 high_threshold 时为 neutral。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "volatility": [0.30],
            }
        )
        stage = RegimeStage(method=RegimeMethod.VOLATILITY_THRESHOLD)
        result = stage.process(frame, empty_context)
        # vol=0.30 == high_vol_threshold -> not > -> neutral
        assert result["regime"][0] == RegimeLabel.NEUTRAL
