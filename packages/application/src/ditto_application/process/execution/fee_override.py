"""
OverrideFeeModel — 使用 CostConfig 费率覆盖 FeeSchedule 对应字段.

build_fee_model 工厂: CostConfig | None → FeeModel
build_slippage_model 工厂: CostConfig | None → SlippageModel
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from ditto_engine.execution.reality.fee import AShareFeeModel, FeeModel
from ditto_engine.execution.reality.slippage import (
    FixedBpsSlippage,
    VolumeShareSlippage,
)
from ditto_engine.execution.rules import FeeSchedule
from ditto_portfolio.accounting.order_book import Order

from ditto_application.contracts import CostConfig

__all__ = ["OverrideFeeModel", "build_fee_model", "build_slippage_model"]


@dataclass(frozen=True)
class OverrideFeeModel:
    """覆盖费率的 FeeModel — 用 CostConfig 费率替换 FeeSchedule 对应字段."""

    _inner: AShareFeeModel
    _commission_rate: float
    _min_commission: float
    _stamp_duty_rate: float

    def calculate(
        self,
        order: Order,
        fill_price: float,
        fill_quantity: int,
        fee_schedule: FeeSchedule,
    ) -> float:
        """计算实际成交手续费 — 使用覆盖后费率."""
        overridden = self._override(fee_schedule)
        return self._inner.calculate(order, fill_price, fill_quantity, overridden)

    def estimate(
        self,
        order: Order,
        estimated_price: float,
        fee_schedule: FeeSchedule,
    ) -> float:
        """估算手续费（预交易）— 使用覆盖后费率."""
        overridden = self._override(fee_schedule)
        return self._inner.estimate(order, estimated_price, overridden)

    def _override(self, fee_schedule: FeeSchedule) -> FeeSchedule:
        """替换 FeeSchedule 中佣金/印花税字段."""
        return dataclasses.replace(
            fee_schedule,
            commission_rate=self._commission_rate,
            min_commission=self._min_commission,
            stamp_duty_rate=self._stamp_duty_rate,
        )


def build_fee_model(cost_config: CostConfig | None) -> FeeModel:
    """
    根据 CostConfig 构建 FeeModel.

    - cost_config=None → AShareFeeModel（默认费率）
    - cost_config=CostConfig(...) → OverrideFeeModel（覆盖费率）
    """
    if cost_config is None:
        return AShareFeeModel()
    return OverrideFeeModel(
        _inner=AShareFeeModel(),
        _commission_rate=cost_config.commission_rate,
        _min_commission=cost_config.commission_min,
        _stamp_duty_rate=cost_config.stamp_duty_rate,
    )


def build_slippage_model(
    cost_config: CostConfig | None,
) -> FixedBpsSlippage | VolumeShareSlippage:
    """
    根据 CostConfig 构建 SlippageModel.

    - cost_config=None 或 impact_model='none' → FixedBpsSlippage
    - impact_model='volume_share' → VolumeShareSlippage
    - 其他 → ValueError
    """
    if cost_config is None or cost_config.impact_model == "none":
        return FixedBpsSlippage(bps=cost_config.slippage_bps if cost_config else 2.0)
    if cost_config.impact_model == "volume_share":
        return VolumeShareSlippage(
            base_bps=cost_config.slippage_bps,
            impact_factor=0.1,
        )
    msg = f"Unknown impact model: {cost_config.impact_model}"
    raise ValueError(msg)
