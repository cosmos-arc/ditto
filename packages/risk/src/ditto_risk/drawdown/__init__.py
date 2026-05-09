"""
Risk drawdown — 回撤分析与控制。

计算最大回撤、当前回撤、回撤持续时间等指标，
支持按策略/组合/时间段维度聚合。
为盘后风控审计和回撤熔断机制提供数据支持。
"""

from __future__ import annotations

from ditto_risk.drawdown.rules import (
    DrawdownStateSnapshot,
    MaxDrawdownRule,
    SingleLossLimitRule,
)

__all__ = ["DrawdownStateSnapshot", "MaxDrawdownRule", "SingleLossLimitRule"]
