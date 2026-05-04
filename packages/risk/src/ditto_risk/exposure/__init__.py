"""
Risk exposure — 暴露度分析与监控。

计算组合在行业、风格因子、市场因子等维度的暴露度，
支持实时暴露度查询和暴露度超限预警。
与 constraints 配合，为约束检查提供数据输入。
"""

from __future__ import annotations

from ditto_risk.exposure.checks import ConcentrationPreCheck
from ditto_risk.exposure.rules import ConcentrationLimitRule, MarketAnomalyRule

__all__ = [
    "ConcentrationLimitRule",
    "ConcentrationPreCheck",
    "MarketAnomalyRule",
]
