"""
Reality — 成交/滑点/手续费/交收模型.

BrokerageModel 打包所有子模型，BacktestBrokerage 通过组合使用。
"""

from __future__ import annotations

from ditto_engine.execution.reality.brokerage import BrokerageModel
from ditto_engine.execution.reality.fee import AShareFeeModel, FeeModel, SimpleFeeModel
from ditto_engine.execution.reality.fill import (
    AShareFillModel,
    ClosingAuctionFillModel,
    FillModel,
    SimpleFillModel,
)
from ditto_engine.execution.reality.market import MarketSnapshot
from ditto_engine.execution.reality.settlement import (
    AShareSettlementModel,
    SettlementModel,
    SimpleSettlementModel,
)
from ditto_engine.execution.reality.slippage import (
    FixedBpsSlippage,
    SlippageModel,
    VolumeShareSlippage,
)

__all__ = [
    "AShareFeeModel",
    "AShareFillModel",
    "AShareSettlementModel",
    "BrokerageModel",
    "ClosingAuctionFillModel",
    "FeeModel",
    "FillModel",
    "FixedBpsSlippage",
    "MarketSnapshot",
    "SettlementModel",
    "SimpleFeeModel",
    "SimpleFillModel",
    "SimpleSettlementModel",
    "SlippageModel",
    "VolumeShareSlippage",
]
