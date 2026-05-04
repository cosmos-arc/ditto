"""
Reality — 成交/滑点/手续费/交收模型.

BrokerageModel 打包所有子模型，BacktestBrokerage 通过组合使用。
"""

from __future__ import annotations

from ditto_execution.reality.brokerage import BrokerageModel
from ditto_execution.reality.fee import AShareFeeModel, SimpleFeeModel
from ditto_execution.reality.fill import (
    AShareFillModel,
    ClosingAuctionFillModel,
    FillModel,
    SimpleFillModel,
)
from ditto_execution.reality.settlement import (
    AShareSettlementModel,
    SettlementModel,
    SimpleSettlementModel,
)
from ditto_execution.reality.slippage import (
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
    "FillModel",
    "FixedBpsSlippage",
    "SettlementModel",
    "SimpleFeeModel",
    "SimpleFillModel",
    "SimpleSettlementModel",
    "SlippageModel",
    "VolumeShareSlippage",
]
