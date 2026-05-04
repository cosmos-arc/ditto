"""Risk — 风险管理子域（PreTrade 逐单校验 + PostTrade 组合风控扫描）。"""

from __future__ import annotations

from ditto_risk.contracts import RiskSlice
from ditto_risk.post_trade import (
    CompositePostTradeGuard,
    ConcentrationLimitRule,
    MarketAnomalyRule,
    MaxDrawdownRule,
    PostTradeRiskGuard,
    RiskAction,
    RiskActionType,
    RiskSeverity,
    SingleLossLimitRule,
)
from ditto_risk.pre_trade import (
    BuyingPowerCheck,
    CompositePreTradeCheck,
    ConcentrationPreCheck,
    DailyTurnoverPreCheck,
    Decision,
    LotSizeCheck,
    NoShortSellCheck,
    OrderCheckResult,
    PreTradeContext,
    PreTradeRiskCheck,
    PriceValidityCheck,
)

__version__ = "0.1.0"

__all__ = [
    "BuyingPowerCheck",
    "CompositePostTradeGuard",
    "CompositePreTradeCheck",
    "ConcentrationLimitRule",
    "ConcentrationPreCheck",
    "DailyTurnoverPreCheck",
    "Decision",
    "LotSizeCheck",
    "MarketAnomalyRule",
    "MaxDrawdownRule",
    "NoShortSellCheck",
    "OrderCheckResult",
    "PostTradeRiskGuard",
    "PreTradeContext",
    "PreTradeRiskCheck",
    "PriceValidityCheck",
    "RiskAction",
    "RiskActionType",
    "RiskSeverity",
    "RiskSlice",
    "SingleLossLimitRule",
]
