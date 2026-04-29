"""
ExecutionPlanner — 将 TargetPortfolio (目标权重) 转换为 Order 列表.

ExecutionPlanner 是策略决策层与执行层之间的桥梁：
  TargetPortfolio → ExecutionPlan (orders + blocked_orders).

Phase 2: 简单实现 (pending-aware, planner lock, lot size).
Phase 3: A 股完整规则 (T+1, 涨跌停, 停牌, 100+1, 三层规则).

依赖方向: execution → accounting (单向，无循环).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_kernel.tracing import traced

from ditto_engine.accounting.account import AccountView
from ditto_engine.accounting.order_book import (
    Order,
    OrderBookReadOnly,
    OrderType,
)
from ditto_engine.execution.reality.constants import DEFAULT_LOT_SIZE
from ditto_engine.execution.reality.market import MarketSnapshot
from ditto_engine.execution.rules import InstrumentRules
from ditto_engine.execution.targets import TargetPortfolioLike

__all__ = [
    "BlockSeverity",
    "BlockedOrder",
    "ExecutionPlan",
    "ExecutionPlanner",
    "SimpleExecutionPlanner",
]


@dataclass(frozen=True)
class _DiffResult:
    """单个标的的调仓差异结果。"""

    diff_qty: int
    target_qty: int
    effective_qty: int
    lot_size: int


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class BlockSeverity(StrEnum):
    """订单阻塞严重程度。"""

    BLOCK = "block"
    DEFER = "defer"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BlockedOrder:
    """
    被阻止的订单 — 因风险控制或规则限制无法执行。

    Attributes:
        instrument_id: 标的 ID
        direction: 原始订单方向
        intended_quantity: 原始计划数量
        reason: 阻止原因
        severity: 阻止严重程度

    """

    instrument_id: InstrumentId
    direction: OrderSide
    intended_quantity: int
    reason: str
    severity: BlockSeverity


@dataclass(frozen=True)
class ExecutionPlan:
    """
    执行计划 — planner 的输出。

    Attributes:
        plan_id: 计划 ID
        trade_date: 交易日期
        orders: 待执行订单列表
        estimated_turnover: 预估成交额
        estimated_cost: 预估交易成本
        blocked_orders: 被阻止的订单列表

    """

    plan_id: str
    trade_date: str
    orders: tuple[Order, ...]
    estimated_turnover: float
    estimated_cost: float
    blocked_orders: tuple[BlockedOrder, ...]


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

        pending_delta = self._compute_pending_delta(account_view.order_book)

        all_instruments = set(target.positions.keys())
        all_instruments |= set(account_view.positions.keys())
        all_instruments |= set(pending_delta.keys())

        orders, blocked_orders = self._compute_diff(
            target=target,
            account_view=account_view,
            pending_delta=pending_delta,
            locked_instruments=locked,
            all_instruments=all_instruments,
            instrument_rules=instrument_rules,
            market_snapshots=market,
        )

        turnover = self._calc_turnover(orders, market)
        cost = self._calc_cost(turnover, instrument_rules)

        return ExecutionPlan(
            plan_id=self._next_id(),
            trade_date=trade_date,
            orders=tuple(orders),
            estimated_turnover=turnover,
            estimated_cost=cost,
            blocked_orders=tuple(blocked_orders),
        )

    # -- lot size / price helpers -----------------------------------------

    def _get_lot_size(
        self,
        instrument_rules: dict[InstrumentId, InstrumentRules],
        iid: InstrumentId,
    ) -> int:
        """获取标的 lot_size，优先使用 InstrumentDefinition。"""
        if iid in instrument_rules:
            return instrument_rules[iid][0].lot_size
        return self._default_lot_size

    @staticmethod
    def _get_estimated_price(
        market: dict[InstrumentId, MarketSnapshot],
        iid: InstrumentId,
    ) -> float:
        """获取预估价格。"""
        snap = market.get(iid)
        return snap.close if snap else 0.0

    # -- pre-checks (suspended, limit up/down) ----------------------------

    @staticmethod
    def _pre_check(
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

        if (
            diff_qty < 0
            and snap.limit_down is not None
            and snap.close <= snap.limit_down
        ):
            return BlockedOrder(
                instrument_id=iid,
                direction=OrderSide.SELL,
                intended_quantity=-diff_qty,
                reason="limit_down_no_sell",
                severity=BlockSeverity.DEFER,
            )

        return None

    # -- 100+1 rounding ---------------------------------------------------

    @staticmethod
    def _round_buy_qty(raw_qty: int, lot_size: int) -> int:
        """买入数量取整 — 最小1手 (100+1 规则)。"""
        if raw_qty <= 0:
            return 0
        return max(lot_size, raw_qty)

    @staticmethod
    def _sell_quantities(raw_qty: int, lot_size: int) -> list[int]:
        """卖出数量拆分 — 整手 + 零股 (100+1 规则)。"""
        if raw_qty <= 0:
            return []
        round_lots = (raw_qty // lot_size) * lot_size
        odd_lots = raw_qty % lot_size
        result: list[int] = []
        if round_lots > 0:
            result.append(round_lots)
        if odd_lots > 0:
            result.append(odd_lots)
        return result

    # -- pending delta ----------------------------------------------------

    @staticmethod
    def _compute_pending_delta(
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

    # -- target quantity --------------------------------------------------

    @staticmethod
    def _target_quantity(
        weight: float,
        nav: float,
        lot_size: int,
        price: float = 0.0,
    ) -> int:
        """将目标权重转换为股数（向下取整到 lot_size 整数倍）。"""
        target_value = weight * nav
        if target_value < 1:
            return 0
        if price > 0:
            target_shares = target_value / price
            lots = int(target_shares / lot_size)
        else:
            lots = int(target_value / lot_size)
        return lots * lot_size

    # -- core diff computation --------------------------------------------

    def _compute_diff(
        self,
        target: TargetPortfolioLike,
        account_view: AccountView,
        pending_delta: dict[InstrumentId, int],
        locked_instruments: set[InstrumentId],
        all_instruments: set[InstrumentId],
        instrument_rules: dict[InstrumentId, InstrumentRules],
        market_snapshots: dict[InstrumentId, MarketSnapshot],
    ) -> tuple[list[Order], list[BlockedOrder]]:
        """计算目标与实际持仓的差异，生成 orders + blocked_orders。"""
        orders: list[Order] = []
        blocked: list[BlockedOrder] = []

        for iid in all_instruments:
            dr = self._instrument_diff(
                iid,
                target,
                account_view,
                pending_delta,
                instrument_rules,
                market_snapshots,
            )
            if dr is None:
                continue

            pre_check = self._pre_check(iid, dr.diff_qty, market_snapshots)
            if pre_check is not None:
                blocked.append(pre_check)
                continue

            if dr.diff_qty > 0:
                self._handle_buy(dr, iid, locked_instruments, orders, blocked)
            elif dr.diff_qty < 0:
                self._handle_sell(
                    dr,
                    iid,
                    account_view,
                    pending_delta,
                    instrument_rules,
                    orders,
                    blocked,
                )

        return orders, blocked

    def _instrument_diff(
        self,
        iid: InstrumentId,
        target: TargetPortfolioLike,
        account_view: AccountView,
        pending_delta: dict[InstrumentId, int],
        instrument_rules: dict[InstrumentId, InstrumentRules],
        market_snapshots: dict[InstrumentId, MarketSnapshot],
    ) -> _DiffResult | None:
        """计算单个标的的 diff。返回 None 表示无需调仓。"""
        weight = target.positions.get(iid, 0.0)
        lot_size = self._get_lot_size(instrument_rules, iid)
        price = self._get_estimated_price(market_snapshots, iid)
        target_qty = self._target_quantity(
            weight,
            account_view.nav,
            lot_size,
            price,
        )

        position = account_view.positions.get(iid)
        current_qty = position.quantity if position else 0
        effective_qty = current_qty + pending_delta.get(iid, 0)
        diff_qty = target_qty - effective_qty

        if diff_qty == 0:
            return None
        return _DiffResult(diff_qty, target_qty, effective_qty, lot_size)

    def _handle_buy(
        self,
        dr: _DiffResult,
        iid: InstrumentId,
        locked_instruments: set[InstrumentId],
        orders: list[Order],
        blocked: list[BlockedOrder],
    ) -> None:
        """处理买入逻辑 (100+1 取整, planner lock)。"""
        if dr.target_qty == 0 and dr.effective_qty <= 0:
            return

        rounded = self._round_buy_qty(dr.diff_qty, dr.lot_size)
        if iid in locked_instruments:
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
            orders.append(
                self._make_order(iid, OrderSide.BUY, rounded),
            )

    def _handle_sell(
        self,
        dr: _DiffResult,
        iid: InstrumentId,
        account_view: AccountView,
        pending_delta: dict[InstrumentId, int],
        instrument_rules: dict[InstrumentId, InstrumentRules],
        orders: list[Order],
        blocked: list[BlockedOrder],
    ) -> None:
        """处理卖出逻辑 (T+1 上限, 100+1 拆分)。"""
        if dr.effective_qty <= 0:
            return

        sell_qty = -dr.diff_qty
        actual_sell = min(sell_qty, dr.effective_qty)

        # T+1 卖出上限
        position = account_view.positions.get(iid)
        if position and iid in instrument_rules:
            cycle = instrument_rules[iid][1].settlement_cycle
            if cycle > 0:
                sellable = position.available_quantity
                pending_sell = pending_delta.get(iid, 0)
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
            for qty in self._sell_quantities(actual_sell, dr.lot_size):
                orders.append(
                    self._make_order(iid, OrderSide.SELL, qty),
                )

    # -- order creation & statistics ---------------------------------------

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

    @staticmethod
    def _calc_turnover(
        orders: list[Order],
        market: dict[InstrumentId, MarketSnapshot],
    ) -> float:
        """计算预估成交额。"""
        turnover = 0.0
        for o in orders:
            snap = market.get(o.instrument_id)
            price = snap.close if snap else 0.0
            turnover += abs(o.quantity) * price
        return turnover

    @staticmethod
    def _calc_cost(
        turnover: float,
        instrument_rules: dict[InstrumentId, InstrumentRules],
    ) -> float:
        """计算预估交易成本 (使用各标的最大费率)。"""
        if not instrument_rules or turnover == 0:
            return 0.0
        max_rate = max(
            r[2].commission_rate + r[2].stamp_duty_rate + r[2].transfer_fee_rate
            for r in instrument_rules.values()
        )
        return turnover * max_rate
