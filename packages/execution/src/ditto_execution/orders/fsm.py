"""FSM 转换表 — OrderStatus 状态机。"""

from __future__ import annotations

from ditto_execution.errors import OrderStateError
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.trigger import OrderTrigger

__all__ = ["TRANSITIONS", "transition"]

TRANSITIONS: dict[tuple[OrderStatus, OrderTrigger], OrderStatus] = {
    (OrderStatus.NEW, OrderTrigger.SUBMIT): OrderStatus.SUBMITTED,
    (OrderStatus.NEW, OrderTrigger.INVALIDATE): OrderStatus.INVALID,
    (OrderStatus.SUBMITTED, OrderTrigger.FILL): OrderStatus.FILLED,
    (OrderStatus.SUBMITTED, OrderTrigger.CANCEL): OrderStatus.CANCELED,
    (OrderStatus.SUBMITTED, OrderTrigger.REJECT): OrderStatus.REJECTED,
    (OrderStatus.SUBMITTED, OrderTrigger.INVALIDATE): OrderStatus.INVALID,
    (OrderStatus.PARTIALLY_FILLED, OrderTrigger.FILL): OrderStatus.PARTIALLY_FILLED,
    (OrderStatus.PARTIALLY_FILLED, OrderTrigger.CANCEL): OrderStatus.CANCELED,
}


def transition(
    current: OrderStatus,
    trigger: OrderTrigger,
    *,
    fill_qty: int = 0,
    leaves_qty: int = 0,
) -> OrderStatus:
    """
    执行状态转换。

    Args:
        current: 当前状态
        trigger: 触发器
        fill_qty: 本次成交量（仅 FILL 触发器使用）
        leaves_qty: 剩余未成交量（仅 FILL 触发器使用）

    Returns:
        目标状态

    Raises:
        OrderStateError: 非法转换

    """
    if current.is_terminal:
        raise OrderStateError(f"Cannot transition from terminal state: {current.value}")

    if trigger == OrderTrigger.FILL:
        return _fill_transition(current, fill_qty=fill_qty, leaves_qty=leaves_qty)

    key = (current, trigger)
    target = TRANSITIONS.get(key)
    if target is None:
        raise OrderStateError(f"Invalid transition: {current.value} + {trigger.value}")
    return target


def _fill_transition(
    current: OrderStatus,
    *,
    fill_qty: int,
    leaves_qty: int,
) -> OrderStatus:
    if current not in (OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED):
        raise OrderStateError(f"FILL trigger not allowed from state: {current.value}")
    if fill_qty <= 0:
        raise OrderStateError(f"FILL requires positive fill_qty, got {fill_qty}")
    if fill_qty > 0 and leaves_qty > 0:
        return (
            OrderStatus.FILLED
            if fill_qty >= leaves_qty
            else OrderStatus.PARTIALLY_FILLED
        )
    target = TRANSITIONS.get((current, OrderTrigger.FILL))
    if target is None:
        raise OrderStateError(f"No default FILL target for state: {current.value}")
    return target
