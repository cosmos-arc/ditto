"""RegimeStage -- 市场状态检测 DecisionStage."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import polars as pl

from ditto_core.strategy.context import StrategyContext

__all__ = ["RegimeLabel", "RegimeMethod", "RegimeStage"]


class RegimeLabel(StrEnum):
    """市场状态标签。"""

    BULL = "bull"
    BEAR = "bear"
    NEUTRAL = "neutral"


class RegimeMethod(StrEnum):
    """市场状态检测方法。"""

    MA_CROSS = "ma_cross"  # 均线交叉
    VOLATILITY_THRESHOLD = "volatility_threshold"  # 波动率阈值


@dataclass(frozen=True)
class RegimeStage:
    """
    Regime Stage -- 市场状态检测。

    Attributes:
        method: 检测方法。
        output_column: 输出列名。
        short_ma_column: MA_CROSS 短期均线列名。
        long_ma_column: MA_CROSS 长期均线列名。
        threshold: MA_CROSS 阈值（ratio 偏离 1.0 的百分比）。
        volatility_column: VOLATILITY_THRESHOLD 波动率列名。
        low_vol_threshold: 低波动率阈值（低于此值为 bull）。
        high_vol_threshold: 高波动率阈值（高于此值为 bear）。
        default_regime: 缺失列或空 frame 时填充的默认状态。

    """

    method: RegimeMethod = RegimeMethod.MA_CROSS
    output_column: str = "regime"
    short_ma_column: str = "ma_short"
    long_ma_column: str = "ma_long"
    threshold: float = 0.01
    volatility_column: str = "volatility"
    low_vol_threshold: float = 0.15
    high_vol_threshold: float = 0.30
    default_regime: RegimeLabel = RegimeLabel.NEUTRAL

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """根据 method 检测市场状态并附加 regime 列。"""
        if self.method == RegimeMethod.MA_CROSS:
            return self._process_ma_cross(frame)
        # RegimeMethod.VOLATILITY_THRESHOLD
        return self._process_volatility_threshold(frame)

    def _process_ma_cross(self, frame: pl.DataFrame) -> pl.DataFrame:
        """MA 交叉法：ratio = short/long，偏离阈值判断状态。"""
        if (
            self.short_ma_column not in frame.columns
            or self.long_ma_column not in frame.columns
        ):
            return frame.with_columns(
                pl.lit(self.default_regime).alias(self.output_column),
            )

        ratio = pl.col(self.short_ma_column) / pl.col(self.long_ma_column)
        upper = 1.0 + self.threshold
        lower = 1.0 - self.threshold

        regime_expr = (
            pl.when(ratio > upper)
            .then(pl.lit(RegimeLabel.BULL))
            .when(ratio < lower)
            .then(pl.lit(RegimeLabel.BEAR))
            .otherwise(pl.lit(self.default_regime))
        )
        return frame.with_columns(regime_expr.alias(self.output_column))

    def _process_volatility_threshold(
        self,
        frame: pl.DataFrame,
    ) -> pl.DataFrame:
        """波动率阈值法：低波动 bull，高波动 bear。"""
        if self.volatility_column not in frame.columns:
            return frame.with_columns(
                pl.lit(self.default_regime).alias(self.output_column),
            )

        vol = pl.col(self.volatility_column)
        regime_expr = (
            pl.when(vol < self.low_vol_threshold)
            .then(pl.lit(RegimeLabel.BULL))
            .when(vol > self.high_vol_threshold)
            .then(pl.lit(RegimeLabel.BEAR))
            .otherwise(pl.lit(self.default_regime))
        )
        return frame.with_columns(regime_expr.alias(self.output_column))
