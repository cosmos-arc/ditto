"""市场预检 — 停牌、涨跌停规则."""

from __future__ import annotations

from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_kernel.trading import MarketSnapshot

from ditto_execution._planner_types import BlockedOrder, BlockSeverity

__all__ = [
    "pre_check",
]


def pre_check(
    iid: InstrumentId,
    diff_qty: int,
    market: dict[InstrumentId, MarketSnapshot],
) -> BlockedOrder | None:
    """市场预检 — 停牌、涨跌停。返回 BlockedOrder 表示应阻止。"""
    snap = market.get(iid)
    if snap is None:
        return None

    if snap.is_suspended:
        direction = OrderSide.BUY if diff_qty > 0 else OrderSide.SELL
        return BlockedOrder(
            instrument_id=iid,
            direction=direction,
            intended_quantity=abs(diff_qty),
            reason="suspended",
            severity=BlockSeverity.BLOCK,
        )

    if diff_qty > 0 and snap.limit_up is not None and snap.close >= snap.limit_up:
        return BlockedOrder(
            instrument_id=iid,
            direction=OrderSide.BUY,
            intended_quantity=diff_qty,
            reason="limit_up_no_buy",
            severity=BlockSeverity.DEFER,
        )

    if diff_qty < 0 and snap.limit_down is not None and snap.close <= snap.limit_down:
        return BlockedOrder(
            instrument_id=iid,
            direction=OrderSide.SELL,
            intended_quantity=-diff_qty,
            reason="limit_down_no_sell",
            severity=BlockSeverity.DEFER,
        )

    return None
