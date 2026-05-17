"""
Regime 类型定义 -- 枚举、Protocol、配置与结果.

提供:
- RegimeLabel: 市场状态标签枚举
- RegimeMethod: 市场状态检测方法枚举
- RegimeIndicator: 市场状态指标 Protocol
- RegimeConfig: 评分引擎配置
- RegimeResult: 评分结果
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import polars as pl

__all__ = [
    "RegimeConfig",
    "RegimeIndicator",
    "RegimeLabel",
    "RegimeMethod",
    "RegimeResult",
]


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
# RegimeIndicator Protocol
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


# ---------------------------------------------------------------------------
# RegimeConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegimeConfig:
    """
    Regime 评分引擎配置.

    Attributes:
        indicators: 参与评分的指标元组。
        bull_threshold: raw_score >= bull_threshold → BULL
            （raw_score 和 threshold 范围均为 0-1）。
        bear_threshold: raw_score < bear_threshold → BEAR
            （raw_score 和 threshold 范围均为 0-1）。
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


# ---------------------------------------------------------------------------
# RegimeResult
# ---------------------------------------------------------------------------


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
