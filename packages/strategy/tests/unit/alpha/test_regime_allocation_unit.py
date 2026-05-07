"""Tests for RegimeAwareAllocationStage -- Regime 感知仓位缩放 Stage.

覆盖:
- 正常缩放（BULL/NEUTRAL/BEAR）
- BEAR + score < bear_cutoff → 完全空仓
- 缺失 regime 列 → 不缩放
- 自定义参数
- frozen dataclass
"""

from __future__ import annotations

import polars as pl
import pytest
from ditto_strategy.alpha.builtins.regime import RegimeLabel
from ditto_strategy.alpha.builtins.regime_allocation import RegimeAwareAllocationStage
from ditto_strategy.alpha.context import StrategyContext

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_context() -> StrategyContext:
    return StrategyContext()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRegimeAwareAllocationStage:
    """RegimeAwareAllocationStage 测试."""

    def test_bull_scale(self, empty_context: StrategyContext) -> None:
        """BULL + position_ratio=1.0 → weight 不变."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11],
                "weight": [0.5, 0.5],
                "regime_score": [80.0, 80.0],
                "regime_label": [RegimeLabel.BULL, RegimeLabel.BULL],
                "position_ratio": [1.0, 1.0],
            },
        )
        stage = RegimeAwareAllocationStage()
        result = stage.process(frame, empty_context)
        assert result["weight"][0] == pytest.approx(0.5)
        assert result["weight"][1] == pytest.approx(0.5)

    def test_neutral_scale(self, empty_context: StrategyContext) -> None:
        """NEUTRAL + position_ratio=0.7 → weight * 0.7."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "weight": [1.0],
                "regime_score": [50.0],
                "regime_label": [RegimeLabel.NEUTRAL],
                "position_ratio": [0.7],
            },
        )
        stage = RegimeAwareAllocationStage()
        result = stage.process(frame, empty_context)
        assert result["weight"][0] == pytest.approx(0.7)

    def test_bear_above_cutoff(self, empty_context: StrategyContext) -> None:
        """BEAR + score > bear_cutoff → weight * position_ratio."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "weight": [1.0],
                "regime_score": [25.0],
                "regime_label": [RegimeLabel.BEAR],
                "position_ratio": [0.3],
            },
        )
        stage = RegimeAwareAllocationStage(bear_cutoff=20.0)
        result = stage.process(frame, empty_context)
        assert result["weight"][0] == pytest.approx(0.3)

    def test_bear_below_cutoff_zero_weight(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """BEAR + score < bear_cutoff → weight = 0 (完全空仓)."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11],
                "weight": [0.5, 0.5],
                "regime_score": [15.0, 15.0],
                "regime_label": [RegimeLabel.BEAR, RegimeLabel.BEAR],
                "position_ratio": [0.3, 0.3],
            },
        )
        stage = RegimeAwareAllocationStage(bear_cutoff=20.0)
        result = stage.process(frame, empty_context)
        assert result["weight"][0] == 0.0
        assert result["weight"][1] == 0.0

    def test_missing_regime_columns(self, empty_context: StrategyContext) -> None:
        """缺失 regime 列 → 不缩放（weight 不变）."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "weight": [0.5],
            },
        )
        stage = RegimeAwareAllocationStage()
        result = stage.process(frame, empty_context)
        assert result["weight"][0] == pytest.approx(0.5)

    def test_missing_position_ratio_column(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """缺失 position_ratio 列 → 不缩放（weight 不变）."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "weight": [0.5],
                "regime_score": [80.0],
                "regime_label": [RegimeLabel.BULL],
            },
        )
        stage = RegimeAwareAllocationStage()
        result = stage.process(frame, empty_context)
        assert result["weight"][0] == pytest.approx(0.5)

    def test_missing_weight_column(self, empty_context: StrategyContext) -> None:
        """缺失 weight 列 → 不变."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "regime_score": [80.0],
                "regime_label": [RegimeLabel.BULL],
                "position_ratio": [1.0],
            },
        )
        stage = RegimeAwareAllocationStage()
        result = stage.process(frame, empty_context)
        assert "weight" not in result.columns

    def test_empty_frame(self, empty_context: StrategyContext) -> None:
        """空 frame → 返回空 frame."""
        frame = pl.DataFrame(
            {
                "instrument_id": [],
                "weight": [],
                "regime_score": [],
                "regime_label": [],
                "position_ratio": [],
            },
            schema={
                "instrument_id": pl.Int64,
                "weight": pl.Float64,
                "regime_score": pl.Float64,
                "regime_label": pl.Utf8,
                "position_ratio": pl.Float64,
            },
        )
        stage = RegimeAwareAllocationStage()
        result = stage.process(frame, empty_context)
        assert result.is_empty()

    def test_default_attributes(self) -> None:
        """默认属性值."""
        stage = RegimeAwareAllocationStage()
        assert stage.regime_score_column == "regime_score"
        assert stage.regime_label_column == "regime_label"
        assert stage.bear_cutoff == 20.0
        assert stage.default_regime == RegimeLabel.NEUTRAL

    def test_frozen(self) -> None:
        """frozen dataclass."""
        stage = RegimeAwareAllocationStage()
        with pytest.raises(AttributeError):
            stage.bear_cutoff = 30.0  # type: ignore[misc]

    def test_mixed_regime_labels(self, empty_context: StrategyContext) -> None:
        """混合 regime label → 分别处理."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11],
                "weight": [0.5, 0.5],
                "regime_score": [80.0, 15.0],
                "regime_label": [RegimeLabel.BULL, RegimeLabel.BEAR],
                "position_ratio": [1.0, 0.3],
            },
        )
        stage = RegimeAwareAllocationStage(bear_cutoff=20.0)
        result = stage.process(frame, empty_context)
        # BULL: weight stays 0.5 * 1.0 = 0.5
        assert result["weight"][0] == pytest.approx(0.5)
        # BEAR + score < 20: weight = 0
        assert result["weight"][1] == 0.0

    def test_custom_columns(self, empty_context: StrategyContext) -> None:
        """自定义列名."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "weight": [1.0],
                "my_score": [15.0],
                "my_label": [RegimeLabel.BEAR],
                "position_ratio": [0.3],
            },
        )
        stage = RegimeAwareAllocationStage(
            regime_score_column="my_score",
            regime_label_column="my_label",
        )
        result = stage.process(frame, empty_context)
        assert result["weight"][0] == 0.0

    def test_position_ratio_scaling(self, empty_context: StrategyContext) -> None:
        """使用 position_ratio 列进行缩放."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "weight": [1.0],
                "regime_score": [50.0],
                "regime_label": [RegimeLabel.NEUTRAL],
                "position_ratio": [0.6],
            },
        )
        stage = RegimeAwareAllocationStage()
        result = stage.process(frame, empty_context)
        assert result["weight"][0] == pytest.approx(0.6)

    def test_null_regime_score(self, empty_context: StrategyContext) -> None:
        """null regime_score → 不缩放."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10],
                "weight": [0.5],
                "regime_score": [None],
                "regime_label": [None],
                "position_ratio": [None],
            },
            schema={
                "instrument_id": pl.Int64,
                "weight": pl.Float64,
                "regime_score": pl.Float64,
                "regime_label": pl.Utf8,
                "position_ratio": pl.Float64,
            },
        )
        stage = RegimeAwareAllocationStage()
        result = stage.process(frame, empty_context)
        assert result["weight"][0] == pytest.approx(0.5)
