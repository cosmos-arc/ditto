"""目标差异计算 — target diff 与 pending delta."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_kernel.trading import InstrumentRules, MarketSnapshot
from ditto_portfolio.accounting import AccountView, Order, OrderBookReadOnly

from ditto_execution._planner_types import BlockedOrder, BlockSeverity
from ditto_execution.cost_estimate import get_estimated_price
from ditto_execution.quantity_rounding import (
    get_lot_size,
    round_buy_qty,
    sell_quantities,
    target_quantity,
)
from ditto_execution.targets import TargetPortfolioLike

__all__ = [
    "DiffContext",
    "DiffResult",
    "compute_diff",
    "compute_pending_delta",
]


type _MakeOrderFn = Callable[[InstrumentId, OrderSide, int], Order]

type _PreCheckFn = Callable[
    [InstrumentId, int, dict[InstrumentId, MarketSnapshot]],
    BlockedOrder | None,
]


@dataclass(frozen=True, slots=True)
class DiffContext:
    """compute_diff 的参数上下文 — 将 10 参数收束为结构化对象。"""

    # Portfolio state
    target: TargetPortfolioLike
    account_view: AccountView
    pending_delta: dict[InstrumentId, int]
    # Scope + Market data
    all_instruments: set[InstrumentId]
    instrument_rules: dict[InstrumentId, InstrumentRules]
    market_snapshots: dict[InstrumentId, MarketSnapshot]
    default_lot_size: int
    # Policy
    locked_instruments: set[InstrumentId]
    pre_check_fn: _PreCheckFn


@dataclass(frozen=True)
class DiffResult:
    """单个标的的调仓差异结果。"""

    diff_qty: int
    target_qty: int
    effective_qty: int
    lot_size: int


def compute_pending_delta(
    order_book: OrderBookReadOnly,
) -> dict[InstrumentId, int]:
    """计算 pending 订单的净数量变动。"""
    delta: dict[InstrumentId, int] = {}
    for ticket in order_book.get_pending():
        iid = ticket.order.instrument_id
        if ticket.order.direction == OrderSide.BUY:
            delta[iid] = delta.get(iid, 0) + ticket.leaves_quantity
        elif ticket.order.direction == OrderSide.SELL:
            delta[iid] = delta.get(iid, 0) - ticket.leaves_quantity
    return delta


def _instrument_diff(
    iid: InstrumentId,
    ctx: DiffContext,
) -> DiffResult | None:
    """计算单个标的的 diff。返回 None 表示无需调仓。"""
    weight = ctx.target.positions.get(iid, 0.0)
    lot_size = get_lot_size(ctx.instrument_rules, iid, ctx.default_lot_size)
    price = get_estimated_price(ctx.market_snapshots, iid)
    target_qty = target_quantity(
        weight,
        ctx.account_view.nav,
        lot_size,
        price,
    )

    position = ctx.account_view.positions.get(iid)
    current_qty = position.quantity if position else 0
    effective_qty = current_qty + ctx.pending_delta.get(iid, 0)
    diff_qty = target_qty - effective_qty

    if diff_qty == 0:
        return None
    return DiffResult(diff_qty, target_qty, effective_qty, lot_size)


def _handle_buy(
    dr: DiffResult,
    iid: InstrumentId,
    ctx: DiffContext,
    orders: list[Order],
    blocked: list[BlockedOrder],
    make_order: _MakeOrderFn,
) -> None:
    """处理买入逻辑 (100+1 取整, planner lock)。"""
    if dr.target_qty == 0 and dr.effective_qty <= 0:
        return

    rounded = round_buy_qty(dr.diff_qty, dr.lot_size)
    if iid in ctx.locked_instruments:
        blocked.append(
            BlockedOrder(
                instrument_id=iid,
                direction=OrderSide.BUY,
                intended_quantity=rounded,
                reason="risk_locked",
                severity=BlockSeverity.BLOCK,
            )
        )
    elif rounded > 0:
        orders.append(make_order(iid, OrderSide.BUY, rounded))


def _handle_sell(
    dr: DiffResult,
    iid: InstrumentId,
    ctx: DiffContext,
    orders: list[Order],
    blocked: list[BlockedOrder],
    make_order: _MakeOrderFn,
) -> None:
    """处理卖出逻辑 (T+1 上限, 100+1 拆分)。"""
    if dr.effective_qty <= 0:
        return

    sell_qty = -dr.diff_qty
    actual_sell = min(sell_qty, dr.effective_qty)

    # T+1 卖出上限
    position = ctx.account_view.positions.get(iid)
    if position and iid in ctx.instrument_rules:
        cycle = ctx.instrument_rules[iid][1].settlement_cycle
        if cycle > 0:
            sellable = position.available_quantity
            pending_sell = ctx.pending_delta.get(iid, 0)
            if pending_sell < 0:
                sellable = max(0, sellable + pending_sell)
            actual_sell = min(actual_sell, sellable)
            if actual_sell < sell_qty:
                blocked.append(
                    BlockedOrder(
                        instrument_id=iid,
                        direction=OrderSide.SELL,
                        intended_quantity=sell_qty - actual_sell,
                        reason="t_plus1_not_sellable",
                        severity=BlockSeverity.DEFER,
                    )
                )

    if actual_sell > 0:
        for qty in sell_quantities(actual_sell, dr.lot_size):
            orders.append(make_order(iid, OrderSide.SELL, qty))


def compute_diff(
    ctx: DiffContext,
    make_order: _MakeOrderFn,
) -> tuple[list[Order], list[BlockedOrder]]:
    """计算目标与实际持仓的差异，生成 orders + blocked_orders。"""
    orders: list[Order] = []
    blocked: list[BlockedOrder] = []

    for iid in ctx.all_instruments:
        dr = _instrument_diff(iid, ctx)
        if dr is None:
            continue

        pre = ctx.pre_check_fn(iid, dr.diff_qty, ctx.market_snapshots)
        if pre is not None:
            blocked.append(pre)
            continue

        if dr.diff_qty > 0:
            _handle_buy(dr, iid, ctx, orders, blocked, make_order)
        elif dr.diff_qty < 0:
            _handle_sell(dr, iid, ctx, orders, blocked, make_order)

    return orders, blocked
