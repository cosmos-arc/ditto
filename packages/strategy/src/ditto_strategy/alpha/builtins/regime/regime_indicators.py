"""
Regime 指标实现 -- 趋势、波动率、广度、动量.

提供:
- TrendIndicator: 趋势指标（MA 交叉）
- VolatilityIndicator: 波动率指标
- BreadthIndicator: 市场广度指标
- MomentumIndicator: 动量指标
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from ditto_strategy.alpha.builtins.regime.regime_types import RegimeLabel

__all__ = [
    "BreadthIndicator",
    "MomentumIndicator",
    "TrendIndicator",
    "VolatilityIndicator",
]


def _first_non_null(series: pl.Series) -> float | None:
    """返回 series 中第一个非 null 值，无则返回 None."""
    non_null = series.drop_nulls()
    if non_null.is_empty():
        return None
    val = non_null[0]
    return float(val)


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

    Limitations:
        - 仅基于单品种 close 价格，不依赖横截面排名
        - 当 lookback 内数据不足时返回 default_regime (NEUTRAL)
        - 不区分上涨/下跌动量的不对称性

    Attributes:
        name: 指标名称。
        weight: 指标权重。
        close_column: 收盘价列名。
        lookback: 回看天数。
        default_regime: 默认市场状态。
        momentum_low: 涨幅映射下界（对应输出 0.0）。
        momentum_high: 涨幅映射上界（对应输出 1.0）。

    """

    name: str = "momentum"
    weight: float = 1.0
    close_column: str = "close"
    lookback: int = 20
    default_regime: RegimeLabel = RegimeLabel.NEUTRAL
    momentum_low: float = -0.10
    momentum_high: float = 0.10

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

        # 将涨幅映射到 0-1: momentum_low → 0.0, momentum_high → 1.0
        span = self.momentum_high - self.momentum_low
        if span == 0:
            return 0.5
        return max(0.0, min(1.0, (change - self.momentum_low) / span))
