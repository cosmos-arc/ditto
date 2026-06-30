"""Order subdomain — 订单方向、订单类型。"""

from enum import StrEnum

__all__ = ["OrderSide", "OrderType"]


class OrderSide(StrEnum):
    """订单方向枚举。"""

    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    """订单类型枚举。"""

    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    MARKET_ON_CLOSE = "market_on_close"
    FAK = "fak"
    FAB = "fab"
    GTD = "gtd"
