"""
Regime 评分引擎与 DecisionStage.

提供:
- RegimeScoreEngine: 多指标加权评分引擎
- RegimeStage: 市场状态检测 DecisionStage（向后兼容）
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from ditto_strategy.alpha.builtins.regime.regime_types import (
    RegimeConfig,
    RegimeLabel,
    RegimeMethod,
    RegimeResult,
)
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.frame import FrameCol, validate_frame

__all__ = [
    "RegimeScoreEngine",
    "RegimeStage",
]


# ---------------------------------------------------------------------------
# RegimeScoreEngine
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegimeScoreEngine:
    """
    Regime 评分引擎 -- 多指标加权合成.

    流程:
      1. 每个 indicator.compute(frame) → float (0-1)
      2. 加权平均: score = sum(w_i * v_i) / sum(w_i) * 100
      3. 根据阈值映射 label (BULL/NEUTRAL/BEAR)
      4. 根据 mapping 策略计算 position_ratio

    Attributes:
        config: 评分引擎配置。

    """

    config: RegimeConfig

    def score(self, frame: pl.DataFrame) -> RegimeResult:
        """计算综合 regime 评分."""
        indicator_values: dict[str, float] = {}
        weighted_sum = 0.0
        weight_total = 0.0

        for indicator in self.config.indicators:
            value = indicator.compute(frame)
            indicator_values[indicator.name] = value
            weighted_sum += indicator.weight * value
            weight_total += indicator.weight

        raw_score = 0.5 if weight_total == 0 else weighted_sum / weight_total

        score = raw_score * 100.0

        # 映射 label
        label = self._map_label(raw_score)

        # 计算 position_ratio
        position_ratio = self._map_position(label, score)

        return RegimeResult(
            score=score,
            label=label,
            position_ratio=position_ratio,
            indicator_values=indicator_values,
        )

    def _map_label(self, raw_score: float) -> RegimeLabel:
        """将归一化分数映射为 RegimeLabel."""
        if raw_score >= self.config.bull_threshold:
            return RegimeLabel.BULL
        if raw_score < self.config.bear_threshold:
            return RegimeLabel.BEAR
        return self.config.default_regime

    def _map_position(self, label: RegimeLabel, score: float) -> float:
        """根据 mapping 策略计算仓位比例."""
        if self.config.position_mapping == "linear":
            return score / 100.0
        # stepped
        if label == RegimeLabel.BULL:
            return self.config.bull_position
        if label == RegimeLabel.BEAR:
            return self.config.bear_position
        return self.config.neutral_position


# ---------------------------------------------------------------------------
# RegimeStage (向后兼容)
# ---------------------------------------------------------------------------


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
        validate_frame(frame, (FrameCol.INSTRUMENT_ID,))
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
