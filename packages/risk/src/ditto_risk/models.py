"""
Risk models — 风险领域数据模型。

定义风险指标（RiskMetrics）、暴露度数据（ExposureData）、
回撤统计（DrawdownStats）等不可变数据结构。
这些模型是风控检查的输入输出载体，不包含业务逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["DrawdownStats", "ExposureData", "RiskMetrics"]


@dataclass(frozen=True)
class RiskMetrics:
    """风控指标汇总."""

    max_drawdown: float
    current_drawdown: float
    sharpe_ratio: float
    volatility: float


@dataclass(frozen=True)
class ExposureData:
    """暴露度数据."""

    total_exposure: float
    top1_weight: float
    top5_weight: float
    sector_count: int


@dataclass(frozen=True)
class DrawdownStats:
    """回撤统计."""

    max_drawdown: float
    current_drawdown: float
    peak_date: str
    trough_date: str
    recovery_days: int
