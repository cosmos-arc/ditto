"""
PreTradeRiskCheck — 订单提交前逐单校验 (V3).

Facade module: 所有类型已迁移到 constraints/ 和 exposure/ 子模块，
此处仅做 re-export 以保持现有导入路径兼容。

V3 完整版包含六条规则：
  - NoShortSellCheck: 卖空校验
  - PriceValidityCheck: 价格有效性校验（涨跌停）
  - LotSizeCheck: 手数校验
  - BuyingPowerCheck: 购买力校验
  - ConcentrationPreCheck: 集中度校验
  - DailyTurnoverPreCheck: 日换手率校验

CompositePreTradeCheck 组合多条规则，支持 resize 后重检（A1）。

Design Doc: v3 §7.2
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

# Re-export InstrumentId for backward compatibility (used by consumers
# via `from ditto_risk.pre_trade import InstrumentId`)
from ditto_risk.constraints.context import (
    Decision,
    InstrumentId,
    OrderCheckResult,
    PreTradeContext,
)
from ditto_risk.exposure.checks import ConcentrationPreCheck

__all__ = [
    "BuyingPowerCheck",
    "CompositePreTradeCheck",
    "ConcentrationPreCheck",
    "DailyTurnoverPreCheck",
    "Decision",
    "InstrumentId",
    "LotSizeCheck",
    "NoShortSellCheck",
    "OrderCheckResult",
    "PreTradeContext",
    "PreTradeRiskCheck",
    "PriceValidityCheck",
]
