"""
Trading 域数据模型（dataclass 定义）.

本模块定义 Trading 域的逻辑密集型模型，使用 dataclass 表示。

设计原则:
- 逻辑密集型用 dataclass（对象传输）
- 支持状态管理和业务规则
- 类型安全（类型注解）
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ditto_kernel.enums import OrderSide as _KernelOrderSide

# OrderSide 已迁移到 ditto_kernel.enums，此处 re-export 保持向后兼容
OrderSide = _KernelOrderSide


class OrderStatus(StrEnum):
    """订单状态."""

    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Order:
    """
    订单模型.

    支持状态管理和业务规则验证。

    Attributes:
        order_id: 订单唯一标识
        instrument_id: 证券 ID（内部分配的长整型 ID）
        side: 订单方向
        quantity: 数量
        price: 价格（None 表示市价单）
        status: 订单状态
        created_at: 创建时间
        filled_at: 成交时间
        filled_quantity: 已成交数量
        filled_price: 成交价格

    """

    order_id: str
    instrument_id: int
    side: OrderSide
    quantity: int
    price: float | None
    status: OrderStatus
    created_at: datetime
    filled_at: datetime | None = None
    filled_quantity: int = 0
    filled_price: float | None = None

    def is_fully_filled(self) -> bool:
        """是否完全成交."""
        return (
            self.status == OrderStatus.FILLED and self.filled_quantity == self.quantity
        )


@dataclass(frozen=True)
class Trade:
    """
    成交记录模型.

    Attributes:
        trade_id: 成交记录唯一标识
        order_id: 关联的订单 ID
        instrument_id: 证券 ID
        side: 成交方向
        quantity: 成交数量
        price: 成交价格
        trade_time: 成交时间

    """

    trade_id: str
    order_id: str
    instrument_id: int
    side: OrderSide
    quantity: int
    price: float
    trade_time: datetime


__all__ = [
    "Order",
    "OrderSide",
    "OrderStatus",
    "Trade",
]
