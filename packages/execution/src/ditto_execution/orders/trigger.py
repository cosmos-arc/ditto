"""OrderTrigger — FSM 触发器枚举。"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["OrderTrigger"]


class OrderTrigger(StrEnum):
    """订单状态机触发器。"""

    SUBMIT = "submit"
    FILL = "fill"
    CANCEL = "cancel"
    REJECT = "reject"
    INVALIDATE = "invalidate"
