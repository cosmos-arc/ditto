"""OrderStatus — 订单状态枚举。"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["OrderStatus"]


class OrderStatus(StrEnum):
    """订单状态 — 7 状态 FSM。"""

    NEW = "new"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    INVALID = "invalid"

    @property
    def is_terminal(self) -> bool:
        """终态：FILLED / CANCELED / REJECTED / INVALID。"""
        return self in (
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED,
            OrderStatus.INVALID,
        )
