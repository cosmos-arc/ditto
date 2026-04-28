"""Order subdomain — 订单方向。"""

from enum import StrEnum

__all__ = ["OrderSide"]


class OrderSide(StrEnum):
    """订单方向枚举。"""

    BUY = "buy"
    SELL = "sell"
