"""
Risk constraints — 可组合的风控约束规则。

实现单一约束（集中度限制、行业暴露上限、单笔交易限额等）
和组合约束检查器。每个约束实现统一的 Constraint Protocol，
可被 pre_trade / post_trade 检查流程按需编排。
"""

from __future__ import annotations

from ditto_risk.constraints.checks import (
    BuyingPowerCheck,
    CompositePreTradeCheck,
    DailyTurnoverPreCheck,
    LotSizeCheck,
    NoShortSellCheck,
    PreTradeRiskCheck,
    PriceValidityCheck,
)
from ditto_risk.constraints.context import (
    Decision,
    OrderCheckResult,
    PreTradeContext,
)

__all__ = [
    "BuyingPowerCheck",
    "CompositePreTradeCheck",
    "DailyTurnoverPreCheck",
    "Decision",
    "LotSizeCheck",
    "NoShortSellCheck",
    "OrderCheckResult",
    "PreTradeContext",
    "PreTradeRiskCheck",
    "PriceValidityCheck",
]
