"""
RegimeStage -- 市场状态检测 DecisionStage.

提供:
- RegimeLabel / RegimeMethod: 枚举类型
- RegimeStage: 市场状态检测 DecisionStage（向后兼容）
- RegimeIndicator: 市场状态指标 Protocol
- TrendIndicator / VolatilityIndicator: 从 RegimeStage 提取的指标
- BreadthIndicator / MomentumIndicator: 扩展指标
- RegimeConfig / RegimeResult: 评分引擎配置与结果
- RegimeScoreEngine: 多指标加权评分引擎
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import polars as pl

from ditto_engine.alpha.context import StrategyContext
from ditto_engine.alpha.frame import FrameCol, validate_frame

__all__ = [
    "BreadthIndicator",
    "MomentumIndicator",
    "RegimeConfig",
    "RegimeIndicator",
    "RegimeLabel",
    "RegimeMethod",
    "RegimeResult",
    "RegimeScoreEngine",
    "RegimeStage",
    "TrendIndicator",
    "VolatilityIndicator",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _first_non_null(series: pl.Series) -> float | None:
    """返回 series 中第一个非 null 值，无则返回 None."""
    non_null = series.drop_nulls()
    if non_null.is_empty():
        return None
    val = non_null[0]
    return float(val)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RegimeLabel(StrEnum):
    """市场状态标签。"""

    BULL = "bull"
    BEAR = "bear"
    NEUTRAL = "neutral"


class RegimeMethod(StrEnum):
    """市场状态检测方法。"""

    MA_CROSS = "ma_cross"  # 均线交叉
    VOLATILITY_THRESHOLD = "volatility_threshold"  # 波动率阈值


# ---------------------------------------------------------------------------
# RegimeIndicator Protocol + Config + Result
# ---------------------------------------------------------------------------


class RegimeIndicator(Protocol):
    """市场状态指标 Protocol — 从 DecisionFrame 计算 0-1 归一化分数."""

    @property
    def name(self) -> str:
        """指标名称."""
        ...

    @property
    def weight(self) -> float:
        """指标权重."""
        ...

    def compute(self, frame: pl.DataFrame) -> float:
        """从 DecisionFrame 计算 0-1 归一化分数."""
        ...


@dataclass(frozen=True)
class RegimeConfig:
    """
    Regime 评分引擎配置.

    Attributes:
        indicators: 参与评分的指标元组。
        bull_threshold: score >= bull_threshold * 100 → BULL。
        bear_threshold: score < bear_threshold * 100 → BEAR。
        position_mapping: 仓位映射策略 (``"linear"`` / ``"stepped"``)。
        bull_position: BULL 状态仓位比例。
        neutral_position: NEUTRAL 状态仓位比例。
        bear_position: BEAR 状态仓位比例。
        default_regime: 默认市场状态。

    """

    indicators: tuple[RegimeIndicator, ...]
    bull_threshold: float = 0.65
    bear_threshold: float = 0.35
    position_mapping: str = "stepped"
    bull_position: float = 1.0
    neutral_position: float = 0.7
    bear_position: float = 0.3
    default_regime: RegimeLabel = RegimeLabel.NEUTRAL


@dataclass(frozen=True)
class RegimeResult:
    """
    Regime 评分结果.

    Attributes:
        score: 综合评分 (0-100)。
        label: 市场状态标签。
        position_ratio: 仓位比例 (0-1)。
        indicator_values: 各指标原始值。

    """

    score: float
    label: RegimeLabel
    position_ratio: float
    indicator_values: dict[str, float]


# ---------------------------------------------------------------------------
# TrendIndicator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrendIndicator:
    """
    趋势指标 -- 从 MA 交叉判断趋势方向.

    ratio = short_ma / long_ma
    - ratio > 1 + threshold → 1.0 (bull)
    - ratio < 1 - threshold → 0.0 (bear)
    - 中间线性插值

    Attributes:
        name: 指标名称。
        weight: 指标权重。
        short_ma_column: 短期均线列名。
        long_ma_column: 长期均线列名。
        threshold: 偏离阈值。

    """

    name: str = "trend"
    weight: float = 1.0
    short_ma_column: str = "ma_short"
    long_ma_column: str = "ma_long"
    threshold: float = 0.01

    def compute(self, frame: pl.DataFrame) -> float:
        """从 frame 的 MA 列计算趋势分数 (0-1)."""
        if (
            self.short_ma_column not in frame.columns
            or self.long_ma_column not in frame.columns
            or frame.is_empty()
        ):
            return 0.5

        short_vals = frame[self.short_ma_column]
        long_vals = frame[self.long_ma_column]

        # 取第一行非 null 值计算
        short_val = _first_non_null(short_vals)
        long_val = _first_non_null(long_vals)

        if short_val is None or long_val is None or long_val == 0:
            return 0.5

        ratio = float(short_val) / float(long_val)
        upper = 1.0 + self.threshold
        lower = 1.0 - self.threshold

        if ratio >= upper:
            return 1.0
        if ratio <= lower:
            return 0.0
        # 线性插值: lower→0, upper→1
        return (ratio - lower) / (upper - lower)


# ---------------------------------------------------------------------------
# VolatilityIndicator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VolatilityIndicator:
    """
    波动率指标 -- 从波动率水平判断市场状态.

    - vol < low → 1.0 (bull, 低波动)
    - vol > high → 0.0 (bear, 高波动)
    - 中间线性插值

    Attributes:
        name: 指标名称。
        weight: 指标权重。
        volatility_column: 波动率列名。
        low_vol_threshold: 低波动阈值（低于此为 bull）。
        high_vol_threshold: 高波动阈值（高于此为 bear）。

    """

    name: str = "volatility"
    weight: float = 1.0
    volatility_column: str = "volatility"
    low_vol_threshold: float = 0.15
    high_vol_threshold: float = 0.30

    def compute(self, frame: pl.DataFrame) -> float:
        """从 frame 的波动率列计算分数 (0-1)."""
        if self.volatility_column not in frame.columns or frame.is_empty():
            return 0.5

        vol_vals = frame[self.volatility_column]
        vol_val = _first_non_null(vol_vals)

        if vol_val is None:
            return 0.5

        vol = float(vol_val)

        if vol <= self.low_vol_threshold:
            return 1.0
        if vol >= self.high_vol_threshold:
            return 0.0
        # 线性插值: low→1, high→0（反向）
        span = self.high_vol_threshold - self.low_vol_threshold
        if span == 0:
            return 0.5
        return 1.0 - (vol - self.low_vol_threshold) / span


# ---------------------------------------------------------------------------
# BreadthIndicator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BreadthIndicator:
    """
    市场广度指标 -- 涨跌比.

    ratio = up / (up + down) → 0-1
    缺失列 → 返回 0.5 (中性)

    Attributes:
        name: 指标名称。
        weight: 指标权重。
        up_count_column: 上涨数量列名。
        down_count_column: 下跌数量列名。

    """

    name: str = "breadth"
    weight: float = 1.0
    up_count_column: str = "up_count"
    down_count_column: str = "down_count"

    def compute(self, frame: pl.DataFrame) -> float:
        """从 frame 的涨跌计数列计算广度分数 (0-1)."""
        if (
            self.up_count_column not in frame.columns
            or self.down_count_column not in frame.columns
            or frame.is_empty()
        ):
            return 0.5

        up_vals = frame[self.up_count_column]
        down_vals = frame[self.down_count_column]

        up_val = _first_non_null(up_vals)
        down_val = _first_non_null(down_vals)

        if up_val is None or down_val is None:
            return 0.5

        up = float(up_val)
        down = float(down_val)
        total = up + down

        if total == 0:
            return 0.5

        return up / total


# ---------------------------------------------------------------------------
# MomentumIndicator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MomentumIndicator:
    """
    动量指标 -- N日涨幅 rank 分位.

    计算 close 列的 N 日涨幅，然后返回该涨幅作为分位值。
    缺失列 → 返回 0.5

    Attributes:
        name: 指标名称。
        weight: 指标权重。
        close_column: 收盘价列名。
        lookback: 回看天数。
        default_regime: 默认市场状态。

    """

    name: str = "momentum"
    weight: float = 1.0
    close_column: str = "close"
    lookback: int = 20
    default_regime: RegimeLabel = RegimeLabel.NEUTRAL

    def compute(self, frame: pl.DataFrame) -> float:
        """从 frame 的 close 列计算动量分位 (0-1)."""
        if self.close_column not in frame.columns or frame.is_empty():
            return 0.5

        close_vals = frame[self.close_column].drop_nulls()
        min_required_points = 2
        if close_vals.len() < min_required_points:
            return 0.5

        # 取最后两个值计算涨幅
        current = float(close_vals[-1])
        past_idx = max(0, close_vals.len() - self.lookback - 1)
        past = float(close_vals[past_idx])

        if past == 0:
            return 0.5

        change = (current - past) / past

        # 将涨幅映射到 0-1: -10% → 0.0, +10% → 1.0
        return max(0.0, min(1.0, (change + 0.10) / 0.20))


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
