"""BrokerageModel — 模型组合包."""

from __future__ import annotations

from dataclasses import dataclass, field

from ditto_engine.execution.reality.fee import AShareFeeModel, FeeModel
from ditto_engine.execution.reality.fill import FillModel, SimpleFillModel
from ditto_engine.execution.reality.settlement import (
    SettlementModel,
    SimpleSettlementModel,
)
from ditto_engine.execution.reality.slippage import FixedBpsSlippage, SlippageModel

__all__ = ["BrokerageModel"]


@dataclass(frozen=True)
class BrokerageModel:
    """
    模型组合包 -- 打包 fill / slippage / fee / settlement 模型.

    BacktestBrokerage 持有此实例，通过组合调用子模型。
    """

    fill_model: FillModel = field(default_factory=SimpleFillModel)
    slippage_model: SlippageModel = field(default_factory=FixedBpsSlippage)
    fee_model: FeeModel = field(default_factory=AShareFeeModel)
    settlement_model: SettlementModel = field(default_factory=SimpleSettlementModel)
