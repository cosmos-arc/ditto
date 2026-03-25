"""
FeeModel — 手续费模型协议 + 简单实现 + A 股实现.

Phase 3 升级 (R6 三层分离签名):
  calculate(order, fill_price, fill_quantity, fee_schedule) -> float   # 实际成交
  estimate(order, estimated_price, fee_schedule) -> float  # 预交易估算
"""

from __future__ import annotations

from typing import Protocol

from ditto_kernel.enums import OrderSide as OrderDirection

from ditto_core.accounting.order_book import Order
from ditto_core.execution.rules import FeeSchedule

__all__ = ["AShareFeeModel", "FeeModel", "SimpleFeeModel"]


class FeeModel(Protocol):
    """手续费模型协议。"""

    def calculate(
        self,
        order: Order,
        fill_price: float,
        fill_quantity: int,
        fee_schedule: FeeSchedule,
    ) -> float:
        """计算实际成交手续费。"""
        ...

    def estimate(
        self,
        order: Order,
        estimated_price: float,
        fee_schedule: FeeSchedule,
    ) -> float:
        """估算手续费（预交易）。"""
        ...


class SimpleFeeModel:
    """
    简单手续费模型 — fallback + 测试用.

    fee = max(5.0, abs(price * quantity) * 0.0003)

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
        return max(5.0, abs(fill_price * fill_quantity) * 0.0003)

    def estimate(
        self,
        order: Order,
        estimated_price: float,
        fee_schedule: FeeSchedule,
    ) -> float:
        """估算手续费（预交易）。"""
        return max(5.0, abs(estimated_price * order.quantity) * 0.0003)


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
        direction: OrderDirection,
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
        if direction == OrderDirection.SELL:
            stamp = amount * fee_schedule.stamp_duty_rate

        return commission + stamp + transfer
