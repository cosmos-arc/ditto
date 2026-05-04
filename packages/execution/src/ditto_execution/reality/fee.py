"""手续费具体实现（SimpleFeeModel + AShareFeeModel）."""

from __future__ import annotations

from ditto_kernel.order import OrderSide
from ditto_kernel.trading import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_MIN_COMMISSION,
    FeeSchedule,
)
from ditto_portfolio.accounting.order_book import Order

__all__ = ["AShareFeeModel", "SimpleFeeModel"]


class SimpleFeeModel:
    """
    简单手续费模型 — fallback + 测试用.

    fee = max(DEFAULT_MIN_COMMISSION, abs(price * quantity) * DEFAULT_COMMISSION_RATE)

    忽略 fee_schedule 参数, 保持 Phase 2 简单逻辑。
    """

    def calculate(
        self,
        order: Order,
        fill_price: float,
        fill_quantity: int,
        fee_schedule: FeeSchedule,
    ) -> float:
        """计算实际成交手续费。"""
        amount = abs(fill_price * fill_quantity)
        return max(DEFAULT_MIN_COMMISSION, amount * DEFAULT_COMMISSION_RATE)

    def estimate(
        self,
        order: Order,
        estimated_price: float,
        fee_schedule: FeeSchedule,
    ) -> float:
        """估算手续费（预交易）。"""
        amount = abs(estimated_price * order.quantity)
        return max(DEFAULT_MIN_COMMISSION, amount * DEFAULT_COMMISSION_RATE)


class AShareFeeModel:
    """
    A 股费用计算模型.

    费用项:
    - 佣金: max(min_commission, amount * commission_rate)
    - 印花税: amount * stamp_duty_rate (仅卖出方向)
    - 过户费: amount * transfer_fee_rate
    """

    def calculate(
        self,
        order: Order,
        fill_price: float,
        fill_quantity: int,
        fee_schedule: FeeSchedule,
    ) -> float:
        """根据实际成交计算费用。"""
        return self._compute_fee(
            fill_price,
            fill_quantity,
            order.direction,
            fee_schedule,
        )

    def estimate(
        self,
        order: Order,
        estimated_price: float,
        fee_schedule: FeeSchedule,
    ) -> float:
        """根据预估价格估算费用。"""
        return self._compute_fee(
            estimated_price,
            order.quantity,
            order.direction,
            fee_schedule,
        )

    @staticmethod
    def _compute_fee(
        price: float,
        quantity: int,
        direction: OrderSide,
        fee_schedule: FeeSchedule,
    ) -> float:
        """核心费用计算 — 佣金 + 印花税(仅卖出) + 过户费。"""
        amount = price * quantity
        commission = max(
            fee_schedule.min_commission,
            amount * fee_schedule.commission_rate,
        )
        transfer = amount * fee_schedule.transfer_fee_rate

        stamp = 0.0
        if direction == OrderSide.SELL:
            stamp = amount * fee_schedule.stamp_duty_rate

        return commission + stamp + transfer
