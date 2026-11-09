"""手续费具体实现（SimpleFeeModel + AShareFeeModel）."""

from __future__ import annotations

from ditto_kernel.order import OrderSide as _OrderSide
from ditto_kernel.trading import (
    DEFAULT_COMMISSION_RATE as _DEFAULT_COMMISSION_RATE,
)
from ditto_kernel.trading import (
    DEFAULT_MIN_COMMISSION as _DEFAULT_MIN_COMMISSION,
)
from ditto_kernel.trading import (
    FeeSchedule as _FeeSchedule,
)

from ditto_execution.orders.model import Order as _Order

__all__ = ["AShareFeeModel", "SimpleFeeModel"]


class SimpleFeeModel:
    """
    简单手续费模型 — fallback + 测试用.

    fee = max(DEFAULT_MIN_COMMISSION, abs(price * quantity) * DEFAULT_COMMISSION_RATE)

    忽略 fee_schedule 参数, 保持 Phase 2 简单逻辑。
    """

    def calculate(
        self,
        order: _Order,
        fill_price: float,
        fill_quantity: int,
        fee_schedule: _FeeSchedule,
    ) -> float:
        """计算实际成交手续费。"""
        amount = abs(fill_price * fill_quantity)
        return max(_DEFAULT_MIN_COMMISSION, amount * _DEFAULT_COMMISSION_RATE)

    def estimate(
        self,
        order: _Order,
        estimated_price: float,
        fee_schedule: _FeeSchedule,
    ) -> float:
        """估算手续费（预交易）。"""
        amount = abs(estimated_price * order.quantity)
        return max(_DEFAULT_MIN_COMMISSION, amount * _DEFAULT_COMMISSION_RATE)


class AShareFeeModel:
    """
    A 股费用计算模型.

    费用项:
    - 佣金: max(min_commission, amount * commission_rate)
    - 印花税: amount * stamp_duty_rate (仅卖出方向)
    - 过户费: amount * transfer_fee_rate + quantity * transfer_fee_per_share
    """

    def calculate(
        self,
        order: _Order,
        fill_price: float,
        fill_quantity: int,
        fee_schedule: _FeeSchedule,
    ) -> float:
        """根据实际成交计算费用。"""
        return sum(
            self.components(
                fill_price,
                fill_quantity,
                order.direction,
                fee_schedule,
            )
        )

    def estimate(
        self,
        order: _Order,
        estimated_price: float,
        fee_schedule: _FeeSchedule,
    ) -> float:
        """根据预估价格估算费用。"""
        return sum(
            self.components(
                estimated_price,
                order.quantity,
                order.direction,
                fee_schedule,
            )
        )

    @staticmethod
    def components(
        price: float,
        quantity: int,
        direction: _OrderSide,
        fee_schedule: _FeeSchedule,
    ) -> tuple[float, float, float]:
        """Return the commission, sell-side stamp duty and transfer charge in CNY."""
        amount = price * quantity
        commission = max(
            fee_schedule.min_commission,
            amount * fee_schedule.commission_rate,
        )
        transfer = (
            amount * fee_schedule.transfer_fee_rate
            + quantity * fee_schedule.transfer_fee_per_share
        )

        stamp = 0.0
        if direction == _OrderSide.SELL:
            stamp = amount * fee_schedule.stamp_duty_rate

        return commission, stamp, transfer
