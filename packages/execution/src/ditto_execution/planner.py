"""
ExecutionPlanner — 将 TargetPortfolio (目标权重) 转换为 Order 列表.

ExecutionPlanner 是策略决策层与执行层之间的桥梁：
  TargetPortfolio → ExecutionPlan (orders + blocked_orders).

Phase 2: 简单实现 (pending-aware, planner lock, lot size).
Phase 3: A 股完整规则 (T+1, 涨跌停, 停牌, 100+1, 三层规则).

依赖方向: execution → accounting (单向，无循环).
"""

from __future__ import annotations

from typing import Protocol

from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.tracing import traced
from ditto_kernel.trading import DEFAULT_LOT_SIZE, InstrumentRules, MarketSnapshot
from ditto_portfolio.accounting import (
    AccountView,
    Order,
)

from ditto_execution._planner_types import (
    BlockedOrder,
    BlockSeverity,
    ExecutionPlan,
)
from ditto_execution.cost_estimate import calc_cost, calc_turnover
from ditto_execution.market_precheck import pre_check
from ditto_execution.target_diff import DiffContext, compute_diff, compute_pending_delta
from ditto_execution.targets import TargetPortfolioLike

__all__ = [
    "BlockSeverity",
    "BlockedOrder",
    "ExecutionPlan",
    "ExecutionPlanner",
    "SimpleExecutionPlanner",
]


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class ExecutionPlanner(Protocol):
    """ExecutionPlanner 协议 — 将 TargetPortfolio 转换为 ExecutionPlan."""

    def plan(
        self,
        target: TargetPortfolioLike,
        account_view: AccountView,
        trade_date: str,
        rules: dict[InstrumentId, InstrumentRules] | None = None,
        market_snapshots: dict[InstrumentId, MarketSnapshot] | None = None,
        locked_instruments: set[InstrumentId] | None = None,
    ) -> ExecutionPlan:
        """根据 target 和 account_view 生成执行计划。"""
        ...


# ---------------------------------------------------------------------------
# SimpleExecutionPlanner
# ---------------------------------------------------------------------------


class SimpleExecutionPlanner:
    """
    简单执行计划器 — 支持 A 股完整规则。

    特性：
    - F2 (pending-aware): 考虑 pending 订单的净变动
    - S1 (planner lock): 锁定标的生成 BlockedOrder
    - R2 (all_instruments merge): 包含待退出持仓
    - T+1: 卖出数量受限于 available_quantity
    - 涨跌停: 买入+涨停 或 卖出+跌停 → defer
    - 停牌: 停牌标的 → block
    - 100+1: 买入最小1手，卖出拆分整手+零股

    """

    def __init__(
        self,
        default_lot_size: int = DEFAULT_LOT_SIZE,
        default_order_type: OrderType = OrderType.MARKET,
    ) -> None:
        self._counter = 0
        self._default_lot_size = default_lot_size
        self._default_order_type = default_order_type

    @traced("engine.execution.plan")
    def plan(
        self,
        target: TargetPortfolioLike,
        account_view: AccountView,
        trade_date: str,
        rules: dict[InstrumentId, InstrumentRules] | None = None,
        market_snapshots: dict[InstrumentId, MarketSnapshot] | None = None,
        locked_instruments: set[InstrumentId] | None = None,
    ) -> ExecutionPlan:
        """生成执行计划。"""
        locked = locked_instruments or set()
        market = market_snapshots or {}
        instrument_rules = rules or {}

        pending_delta = compute_pending_delta(account_view.order_book)

        all_instruments = set(target.positions.keys())
        all_instruments |= set(account_view.positions.keys())
        all_instruments |= set(pending_delta.keys())

        ctx = DiffContext(
            target=target,
            account_view=account_view,
            pending_delta=pending_delta,
            all_instruments=all_instruments,
            instrument_rules=instrument_rules,
            market_snapshots=market,
            default_lot_size=self._default_lot_size,
            locked_instruments=locked,
            pre_check_fn=pre_check,
        )
        orders, blocked_orders = compute_diff(ctx, self._make_order)

        turnover = calc_turnover(orders, market)
        cost = calc_cost(turnover, instrument_rules)

        return ExecutionPlan(
            plan_id=self._next_id(),
            trade_date=trade_date,
            orders=tuple(orders),
            estimated_turnover=turnover,
            estimated_cost=cost,
            blocked_orders=tuple(blocked_orders),
        )

    # -- order creation & id generation -----------------------------------

    def _make_order(
        self,
        instrument_id: InstrumentId,
        direction: OrderSide,
        quantity: int,
        order_type: OrderType | None = None,
        price: float | None = None,
    ) -> Order:
        """创建 Order 对象。"""
        return Order(
            order_id=self._next_id(),
            instrument_id=instrument_id,
            order_type=order_type or self._default_order_type,
            direction=direction,
            quantity=quantity,
            price=price,
        )

    def _next_id(self) -> str:
        """生成唯一 ID。"""
        self._counter += 1
        return f"plan-order-{self._counter}"
