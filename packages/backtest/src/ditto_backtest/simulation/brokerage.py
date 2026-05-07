"""BrokerageModel — 模型组合包."""

from __future__ import annotations

from dataclasses import dataclass, field

from ditto_execution.reality.fee import AShareFeeModel
from ditto_kernel.trading import FeeModel as _FeeModel

from ditto_backtest.simulation.fill import FillModel, SimpleFillModel
from ditto_backtest.simulation.settlement import (
    SettlementModel,
    SimpleSettlementModel,
)
from ditto_backtest.simulation.slippage import FixedBpsSlippage, SlippageModel

__all__ = ["BrokerageModel"]


@dataclass(frozen=True)
class BrokerageModel:
    """
    模型组合包 -- 打包 fill / slippage / fee / settlement 模型.

    BacktestBrokerage 持有此实例，通过组合调用子模型。
    """

    fill_model: FillModel = field(default_factory=SimpleFillModel)
    slippage_model: SlippageModel = field(default_factory=FixedBpsSlippage)
    fee_model: _FeeModel = field(default_factory=AShareFeeModel)
    settlement_model: SettlementModel = field(default_factory=SimpleSettlementModel)
