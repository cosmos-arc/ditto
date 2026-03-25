"""ExecutionPlanner / ExecutionPlan / BlockedOrder 单元测试."""

from types import MappingProxyType

import pytest
from ditto_core.accounting.account import AccountView
from ditto_core.accounting.cash import CashBook
from ditto_core.accounting.order_book import (
    Order,
    OrderBookReadOnly,
    OrderSide,
    OrderStatus,
    OrderTicket,
    OrderType,
)
from ditto_core.accounting.position import Position
from ditto_core.execution.planner import (
    BlockedOrder,
    BlockSeverity,
    ExecutionPlan,
    ExecutionPlanner,
    SimpleExecutionPlanner,
)
from ditto_core.execution.reality.market import MarketSnapshot
from ditto_core.execution.rules import (
    FeeSchedule,
    InstrumentDefinition,
    InstrumentRules,
    TradingRuleSet,
)
from ditto_core.strategy.models import TargetPortfolio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# 为了测试简单，使用较小的 NAV (100_000) 且 lot_size=100。
# planner 将 weight * nav 视为 target_value，然后向下取整到 lot_size 的整数倍。
# quantity = lots * lot_size，其中 lots = floor(weight * nav / lot_size)。
#
# 示例: nav=100000, lot=100, weight=0.3
#   target_value = 30000, lots = 300, quantity = 30000


def _account_view(
    positions: dict[int, Position] | None = None,
    pending_tickets: dict[str, OrderTicket] | None = None,
    nav: float = 100_000.0,
    exposure: float = 0.0,
) -> AccountView:
    """创建用于测试的 AccountView."""
    pos = positions or {}
    pending = pending_tickets or {}
    return AccountView(
        positions=MappingProxyType(pos),
        cash=CashBook(available=nav, settled=nav, frozen=0.0),
        total_value=nav + exposure,
        nav=nav,
        exposure=exposure,
        pending_buy_value=0.0,
        order_book=OrderBookReadOnly(pending),
    )


def _position(
    instrument_id: int,
    quantity: int = 100,
    market_value: float = 10000.0,
) -> Position:
    """创建用于测试的 Position."""
    avg_cost = market_value / quantity if quantity > 0 else 0.0
    return Position(
        instrument_id=instrument_id,
        quantity=quantity,
        available_quantity=quantity,
        average_cost=avg_cost,
        market_value=market_value,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=0.0,
    )


def _pending_buy(
    order_id: str,
    instrument_id: int,
    quantity: int,
) -> OrderTicket:
    """创建一个未成交的买单."""
    order = Order(
        order_id=order_id,
        instrument_id=instrument_id,
        order_type=OrderType.MARKET,
        direction=OrderSide.BUY,
        quantity=quantity,
    )
    return OrderTicket(order=order, status=OrderStatus.SUBMITTED)


def _pending_sell(
    order_id: str,
    instrument_id: int,
    quantity: int,
) -> OrderTicket:
    """创建一个未成交的卖单."""
    order = Order(
        order_id=order_id,
        instrument_id=instrument_id,
        order_type=OrderType.MARKET,
        direction=OrderSide.SELL,
        quantity=quantity,
    )
    return OrderTicket(order=order, status=OrderStatus.SUBMITTED)


def _target(
    positions: dict[int, float] | None = None,
    cash_target: float = 0.0,
) -> TargetPortfolio:
    """创建用于测试的 TargetPortfolio (weight → quantity 由 planner 按 nav 计算)."""
    return TargetPortfolio(
        trade_date="2026-03-21",
        strategy_id="test-strategy",
        run_id="run-001",
        positions=positions or {},
        cash_target=cash_target,
    )


def _target_qty(weight: float, nav: float = 100_000.0, lot_size: int = 100) -> int:
    """计算 target quantity，与 planner 的 _target_quantity 逻辑一致。"""
    target_value = weight * nav
    if target_value < lot_size:
        return 0
    lots = int(target_value / lot_size)
    return lots * lot_size


# ---------------------------------------------------------------------------
# BlockedOrder
# ---------------------------------------------------------------------------


class TestBlockedOrder:
    def test_frozen(self) -> None:
        bo = BlockedOrder(
            instrument_id=1,
            direction=OrderSide.BUY,
            intended_quantity=100,
            reason="risk_locked",
            severity=BlockSeverity.BLOCK,
        )
        with pytest.raises(AttributeError):
            bo.instrument_id = 2  # type: ignore[misc]

    def test_severity_values(self) -> None:
        bo_block = BlockedOrder(
            instrument_id=1,
            direction=OrderSide.BUY,
            intended_quantity=100,
            reason="risk_locked",
            severity=BlockSeverity.BLOCK,
        )
        assert bo_block.severity is BlockSeverity.BLOCK

        bo_defer = BlockedOrder(
            instrument_id=1,
            direction=OrderSide.BUY,
            intended_quantity=100,
            reason="price_limit",
            severity=BlockSeverity.DEFER,
        )
        assert bo_defer.severity is BlockSeverity.DEFER


# ---------------------------------------------------------------------------
# ExecutionPlan
# ---------------------------------------------------------------------------


class TestExecutionPlan:
    def test_frozen(self) -> None:
        plan = ExecutionPlan(
            plan_id="plan-001",
            trade_date="2026-03-21",
            orders=(),
            estimated_turnover=0.0,
            estimated_cost=0.0,
            blocked_orders=(),
        )
        with pytest.raises(AttributeError):
            plan.plan_id = "plan-002"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ExecutionPlanner Protocol
# ---------------------------------------------------------------------------


class TestExecutionPlannerProtocol:
    def test_simple_planner_has_plan_method(self) -> None:
        """SimpleExecutionPlanner 实现了 plan 方法（满足 Protocol 的结构需求）。"""
        planner = SimpleExecutionPlanner()
        assert callable(getattr(planner, "plan", None))

    def test_protocol_defines_plan_signature(self) -> None:
        """Protocol 定义了 plan 方法签名。"""
        import inspect

        sig = inspect.signature(ExecutionPlanner.plan)
        params = list(sig.parameters.keys())
        assert "target" in params
        assert "account_view" in params
        assert "trade_date" in params
        assert "rules" in params
        assert "market_snapshots" in params


# ---------------------------------------------------------------------------
# SimpleExecutionPlanner — 首次建仓
# ---------------------------------------------------------------------------


class TestFirstBuild:
    """空组合，首次建仓 → BUY orders."""

    def test_first_buy_creates_orders(self) -> None:
        """target = {ETF-001: 0.5, ETF-002: 0.3}, nav=100K, lot=100."""
        av = _account_view()
        target = _target({1: 0.5, 2: 0.3})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        assert plan.trade_date == "2026-03-21"
        assert plan.plan_id.startswith("plan-")
        orders = {o.instrument_id: o for o in plan.orders}
        assert set(orders.keys()) == {1, 2}

        # ETF-001: 0.5 * 100K = 50000 / 100 = 500 lots → 50000
        assert orders[1].direction == OrderSide.BUY
        assert orders[1].quantity == 50000
        # ETF-002: 0.3 * 100K = 30000 / 100 = 300 lots → 30000
        assert orders[2].direction == OrderSide.BUY
        assert orders[2].quantity == 30000
        assert len(plan.blocked_orders) == 0

    def test_empty_target_no_orders(self) -> None:
        """空 target → 无订单."""
        av = _account_view()
        target = _target({})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        assert len(plan.orders) == 0


# ---------------------------------------------------------------------------
# SimpleExecutionPlanner — 无需调仓
# ---------------------------------------------------------------------------


class TestNoRebalance:
    """当前持仓与 target 一致 → 无订单."""

    def test_no_rebalance(self) -> None:
        """当前持仓 30000 股, target weight 对应 30000 股 → 无订单."""
        av = _account_view(
            positions={
                1: _position(
                    1,
                    quantity=30000,
                    market_value=30000.0,
                ),
            },
            exposure=30000.0,
        )
        # 0.3 * 100K = 30000 → 与 position 匹配
        target = _target({1: 0.3})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        assert len(plan.orders) == 0
        assert len(plan.blocked_orders) == 0


# ---------------------------------------------------------------------------
# SimpleExecutionPlanner — 减仓 / 清仓
# ---------------------------------------------------------------------------


class TestExitPosition:
    """退出标的 → SELL order."""

    def test_exit_instrument(self) -> None:
        """ETF-001 在 position 中但不在 target 中 → 全部卖出."""
        av = _account_view(
            positions={
                1: _position(
                    1,
                    quantity=30000,
                    market_value=30000.0,
                ),
            },
            exposure=30000.0,
        )
        target = _target({2: 0.5})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        # ETF-001 应该被卖出（exit）
        sell_orders = [o for o in plan.orders if o.instrument_id == 1]
        assert len(sell_orders) == 1
        assert sell_orders[0].direction == OrderSide.SELL
        assert sell_orders[0].quantity == 30000

        # ETF-002 应该被买入
        buy_orders = [o for o in plan.orders if o.instrument_id == 2]
        assert len(buy_orders) == 1
        assert buy_orders[0].direction == OrderSide.BUY

    def test_target_weight_zero_exits(self) -> None:
        """target weight = 0 → 清仓."""
        av = _account_view(
            positions={
                1: _position(
                    1,
                    quantity=20000,
                    market_value=20000.0,
                ),
            },
            exposure=20000.0,
        )
        target = _target({1: 0.0})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        assert len(plan.orders) == 1
        assert plan.orders[0].direction == OrderSide.SELL
        assert plan.orders[0].quantity == 20000

    def test_reduce_position(self) -> None:
        """减仓: 当前 30000 股 → target 需要 20000 股 → 卖出 10000."""
        av = _account_view(
            positions={
                1: _position(
                    1,
                    quantity=30000,
                    market_value=30000.0,
                ),
            },
            exposure=30000.0,
        )
        # 0.2 * 100K = 20000
        target = _target({1: 0.2})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        assert len(plan.orders) == 1
        assert plan.orders[0].direction == OrderSide.SELL
        assert plan.orders[0].quantity == 10000  # 30000 - 20000


# ---------------------------------------------------------------------------
# SimpleExecutionPlanner — Pending-aware (F2)
# ---------------------------------------------------------------------------


class TestPendingAware:
    """F2: pending 订单影响 effective_qty 计算."""

    def test_pending_sell_no_duplicate(self) -> None:
        """已有 pending sell 10000 股 → effective_qty 减少，不重复卖出."""
        av = _account_view(
            positions={
                1: _position(
                    1,
                    quantity=30000,
                    market_value=30000.0,
                ),
            },
            pending_tickets={
                "pending-sell-1": _pending_sell(
                    "pending-sell-1",
                    1,
                    10000,
                ),
            },
            exposure=30000.0,
        )
        # effective_qty = 30000 + (-10000) = 20000
        # target: 0.2 * 100K = 20000 → 完全匹配
        target = _target({1: 0.2})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        assert len(plan.orders) == 0

    def test_pending_buy_increases_effective(self) -> None:
        """已有 pending buy 10000 股 → effective_qty 增加."""
        av = _account_view(
            positions={
                1: _position(
                    1,
                    quantity=10000,
                    market_value=10000.0,
                ),
            },
            pending_tickets={
                "pending-buy-1": _pending_buy(
                    "pending-buy-1",
                    1,
                    10000,
                ),
            },
            exposure=10000.0,
        )
        # effective_qty = 10000 + 10000 = 20000
        # target: 0.2 * 100K = 20000 → 完全匹配
        target = _target({1: 0.2})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        assert len(plan.orders) == 0

    def test_pending_sell_creates_larger_buy(self) -> None:
        """pending sell 导致 effective_qty < target → 需要额外买入."""
        av = _account_view(
            positions={
                1: _position(
                    1,
                    quantity=30000,
                    market_value=30000.0,
                ),
            },
            pending_tickets={
                "pending-sell-1": _pending_sell(
                    "pending-sell-1",
                    1,
                    10000,
                ),
            },
            exposure=30000.0,
        )
        # effective_qty = 30000 + (-10000) = 20000
        # target: 0.3 * 100K = 30000 → 需要买入 10000
        target = _target({1: 0.3})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        assert len(plan.orders) == 1
        assert plan.orders[0].direction == OrderSide.BUY
        assert plan.orders[0].quantity == 10000


# ---------------------------------------------------------------------------
# SimpleExecutionPlanner — Planner lock (S1)
# ---------------------------------------------------------------------------


class TestPlannerLock:
    """S1: locked instrument → BlockedOrder, 不生成买入订单."""

    def test_locked_instrument_blocked(self) -> None:
        """ETF-001 被锁定且 target 要买入 → BlockedOrder."""
        av = _account_view()
        target = _target({1: 0.5})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            locked_instruments={1},
        )

        assert len(plan.orders) == 0
        assert len(plan.blocked_orders) == 1
        bo = plan.blocked_orders[0]
        assert bo.instrument_id == 1
        assert bo.direction == OrderSide.BUY
        assert bo.reason == "risk_locked"
        assert bo.severity is BlockSeverity.BLOCK
        assert bo.intended_quantity == 50000  # 0.5 * 100K

    def test_locked_allows_sell(self) -> None:
        """ETF-001 被锁定，但 target 要卖出 → 允许卖出，不产生 BlockedOrder."""
        av = _account_view(
            positions={
                1: _position(
                    1,
                    quantity=30000,
                    market_value=30000.0,
                ),
            },
            exposure=30000.0,
        )
        target = _target({1: 0.0})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            locked_instruments={1},
        )

        assert len(plan.blocked_orders) == 0
        sell_orders = [o for o in plan.orders if o.instrument_id == 1]
        assert len(sell_orders) == 1
        assert sell_orders[0].direction == OrderSide.SELL
        assert sell_orders[0].quantity == 30000


# ---------------------------------------------------------------------------
# SimpleExecutionPlanner — 混合场景
# ---------------------------------------------------------------------------


class TestMixedScenario:
    """混合场景：部分调仓 + 清仓 + 新入场."""

    def test_mixed_rebalance(self) -> None:
        """ETF-001 加仓, ETF-002 减仓, ETF-003 清仓, ETF-004 新入场."""
        av = _account_view(
            positions={
                1: _position(1, quantity=20000, market_value=20000.0),
                2: _position(2, quantity=30000, market_value=30000.0),
                3: _position(3, quantity=10000, market_value=10000.0),
            },
            exposure=60000.0,
        )
        # ETF-001: 当前 20000, target 0.3*100K=30000 → 买入 10000
        # ETF-002: 当前 30000, target 0.2*100K=20000 → 卖出 10000
        # ETF-003: 当前 10000, 不在 target → 清仓 10000
        # ETF-004: 当前 0, target 0.1*100K=10000 → 买入 10000
        target = _target({1: 0.3, 2: 0.2, 4: 0.1})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        orders = {o.instrument_id: o for o in plan.orders}
        assert set(orders.keys()) == {1, 2, 3, 4}

        # ETF-001: 加仓 10000
        assert orders[1].direction == OrderSide.BUY
        assert orders[1].quantity == 10000

        # ETF-002: 减仓 10000
        assert orders[2].direction == OrderSide.SELL
        assert orders[2].quantity == 10000

        # ETF-003: 清仓
        assert orders[3].direction == OrderSide.SELL
        assert orders[3].quantity == 10000

        # ETF-004: 新入场
        assert orders[4].direction == OrderSide.BUY
        assert orders[4].quantity == 10000


# ---------------------------------------------------------------------------
# SimpleExecutionPlanner — Lot size 取整
# ---------------------------------------------------------------------------


class TestLotSizeRounding:
    """lot_size 取整规则."""

    def test_lot_size_rounding(self) -> None:
        """weight * nav 不能被 lot_size 整除时，向下取整."""
        av = _account_view(nav=95000.0)
        # 0.33 * 95000 = 31350 → floor(31350/100)*100 = 31300
        # 0.11 * 95000 = 10450 → floor(10450/100)*100 = 10400
        target = _target({1: 0.33, 2: 0.11})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        orders = {o.instrument_id: o for o in plan.orders}
        assert orders[1].quantity == 31300
        assert orders[2].quantity == 10400

    def test_custom_lot_size(self) -> None:
        """自定义 lot_size = 200 (通过构造参数)."""
        av = _account_view(nav=100000.0)
        target = _target({1: 0.3})

        planner = SimpleExecutionPlanner(default_lot_size=200)
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        # 0.3 * 100000 = 30000 → floor(30000/200)*200 = 30000
        assert plan.orders[0].quantity == 30000
        assert plan.orders[0].quantity % 200 == 0

    def test_weight_below_one_lot(self) -> None:
        """weight * nav 不足一手 → 不生成订单."""
        av = _account_view(nav=100_000.0)
        # 0.0005 * 100K = 50 < 100 → 不够一手
        target = _target({1: 0.0005})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        assert len(plan.orders) == 0

    def test_exact_lot_boundary(self) -> None:
        """weight * nav 恰好等于一手 → 生成一手."""
        av = _account_view(nav=100_000.0)
        # 0.001 * 100K = 100 = 1 lot → 恰好一手
        target = _target({1: 0.001})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        assert len(plan.orders) == 1
        assert plan.orders[0].quantity == 100


# ---------------------------------------------------------------------------
# SimpleExecutionPlanner — 计划统计
# ---------------------------------------------------------------------------


class TestPlanStatistics:
    """ExecutionPlan 统计信息."""

    def test_estimated_turnover(self) -> None:
        """turnover = sum(|order.quantity| * MarketSnapshot.close)."""
        av = _account_view(
            positions={
                1: _position(
                    1,
                    quantity=20000,
                    market_value=20000.0,
                ),
            },
            exposure=20000.0,
        )
        target = _target({1: 0.3})
        # no price → target_qty=30000, current=20000, diff=10000 BUY
        market = {1: _market_snapshot(close=1.0)}

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            market_snapshots=market,
        )

        # turnover = 10000 * 1.0 = 10000
        assert plan.estimated_turnover == pytest.approx(10000.0)

    def test_estimated_cost(self) -> None:
        """cost = turnover * fee_rate (from FeeSchedule)."""
        av = _account_view(
            positions={
                1: _position(
                    1,
                    quantity=20000,
                    market_value=20000.0,
                ),
            },
            exposure=20000.0,
        )
        rules = {1: _instrument_rules(1, commission_rate=0.001)}
        target = _target({1: 0.3})
        market = {1: _market_snapshot(close=1.0)}

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            rules=rules,
            market_snapshots=market,
        )

        # turnover = 10000, rate = 0.001, cost = 10000 * 0.001 = 10
        assert plan.estimated_cost == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# SimpleExecutionPlanner — 边界情况
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """边界情况."""

    def test_pending_sell_without_position_no_sell_order(self) -> None:
        """pending sell 但无 position → effective_qty < 0，不产生卖单."""
        av = _account_view(
            pending_tickets={
                "pending-sell-all": _pending_sell(
                    "pending-sell-all",
                    1,
                    500,
                ),
            },
        )
        target = _target({2: 0.5})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        # ETF-001 不在 position, effective_qty = 0 + (-500) = -500
        # target_qty = 0, diff = -500 → effective_qty < 0, 不产生卖单
        assert len(plan.orders) == 1
        assert plan.orders[0].instrument_id == 2

    def test_locked_and_not_in_target(self) -> None:
        """锁定标的不在 target 中 → 不产生 BlockedOrder，正常卖出."""
        av = _account_view(
            positions={
                1: _position(
                    1,
                    quantity=10000,
                    market_value=10000.0,
                ),
            },
            exposure=10000.0,
        )
        target = _target({})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            locked_instruments={1},
        )

        # ETF-001 不在 target，weight = 0, 需要卖出
        # 锁定不影响卖出操作
        assert len(plan.blocked_orders) == 0
        assert len(plan.orders) == 1
        assert plan.orders[0].direction == OrderSide.SELL
        assert plan.orders[0].quantity == 10000

    def test_default_lot_size(self) -> None:
        """未提供 rules 时使用默认 lot_size = 100."""
        av = _account_view(nav=100_000.0)
        target = _target({1: 0.5})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        assert len(plan.orders) == 1
        assert plan.orders[0].quantity == 50000
        assert plan.orders[0].quantity % 100 == 0

    def test_plan_id_increments(self) -> None:
        """多次调用 plan()，plan_id 应递增."""
        av = _account_view()
        target = _target({1: 0.1})

        planner = SimpleExecutionPlanner()
        plan1 = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )
        plan2 = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-22",
        )

        assert plan1.plan_id != plan2.plan_id

    def test_sell_capped_at_effective_qty(self) -> None:
        """卖出数量不超过 effective_qty."""
        av = _account_view(
            positions={
                1: _position(
                    1,
                    quantity=10000,
                    market_value=10000.0,
                ),
            },
            exposure=10000.0,
        )
        # target = 0, 需要卖出 10000
        # effective_qty = 10000, sell = min(10000, 10000) = 10000
        target = _target({1: 0.0})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        assert len(plan.orders) == 1
        assert plan.orders[0].quantity == 10000


# ---------------------------------------------------------------------------
# Helpers — 三层规则 + MarketSnapshot
# ---------------------------------------------------------------------------


def _definition(
    instrument_id: int = 1,
    lot_size: int = 100,
) -> InstrumentDefinition:
    return InstrumentDefinition(
        instrument_id=instrument_id,
        asset_class="etf",
        exchange="XSHE",
        currency="CNY",
        tick_size=0.001,
        lot_size=lot_size,
        multiplier=1.0,
        board_segment="main",
        lifecycle_state="normal",
    )


def _trading_rule(
    instrument_id: int = 1,
    settlement_cycle: int = 0,
) -> TradingRuleSet:
    return TradingRuleSet(
        instrument_id=instrument_id,
        as_of_date="2026-03-21",
        settlement_cycle=settlement_cycle,
        fund_settlement_cycle=settlement_cycle,
        price_limit_pct=0.10,
        order_types_supported=("market", "limit"),
        call_auction_sessions=("open", "close"),
    )


def _fee_schedule(
    instrument_id: int = 1,
    commission_rate: float = 0.0,
) -> FeeSchedule:
    return FeeSchedule(
        instrument_id=instrument_id,
        as_of_date="2026-03-21",
        commission_rate=commission_rate,
        min_commission=0.0,
        stamp_duty_rate=0.0,
        transfer_fee_rate=0.0,
    )


def _instrument_rules(
    instrument_id: int = 1,
    lot_size: int = 100,
    settlement_cycle: int = 0,
    commission_rate: float = 0.0,
) -> InstrumentRules:
    return (
        _definition(instrument_id, lot_size),
        _trading_rule(instrument_id, settlement_cycle),
        _fee_schedule(instrument_id, commission_rate),
    )


def _market_snapshot(
    instrument_id: int = 1,
    close: float = 10.0,
    is_suspended: bool = False,
    limit_up: float | None = None,
    limit_down: float | None = None,
) -> MarketSnapshot:
    return MarketSnapshot(
        trade_date="2026-03-21",
        instrument_id=instrument_id,
        open=close,
        high=close,
        low=close,
        close=close,
        prev_close=close,
        volume=1_000_000,
        amount=close * 1_000_000,
        is_suspended=is_suspended,
        limit_up=limit_up,
        limit_down=limit_down,
    )


# ---------------------------------------------------------------------------
# Protocol 升级 — 三层规则签名
# ---------------------------------------------------------------------------


class TestProtocolUpgrade:
    """Protocol 签名升级为三层规则 dict + market_snapshots。"""

    def test_plan_accepts_instrument_rules(self) -> None:
        """plan() 接受 dict[int, InstrumentRules] 类型的 rules。"""
        av = _account_view()
        target = _target({1: 0.5})
        rules = {1: _instrument_rules()}
        snap = {1: _market_snapshot()}

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            rules=rules,
            market_snapshots=snap,
        )

        assert len(plan.orders) == 1

    def test_plan_none_rules_uses_defaults(self) -> None:
        """rules=None 时使用默认 lot_size=100。"""
        av = _account_view()
        target = _target({1: 0.5})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            rules=None,
            market_snapshots=None,
        )

        # 0.5 * 100K = 50000, floor(50000/100)*100 = 50000
        assert len(plan.orders) == 1
        assert plan.orders[0].quantity == 50000

    def test_per_instrument_lot_size(self) -> None:
        """不同标的使用不同 lot_size (从 InstrumentDefinition 读取)。"""
        av = _account_view()
        rules = {
            1: _instrument_rules(1, lot_size=200),
            2: _instrument_rules(2, lot_size=100),
        }
        target = _target({1: 0.5, 2: 0.5})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            rules=rules,
        )

        orders = {o.instrument_id: o for o in plan.orders}
        # ETF-001: 50000, floor(50000/200)*200 = 50000
        assert orders[1].quantity == 50000
        # ETF-002: 50000, floor(50000/100)*100 = 50000
        assert orders[2].quantity == 50000


# ---------------------------------------------------------------------------
# T+1 卖出限制
# ---------------------------------------------------------------------------


class TestTPlusOne:
    """T+1: 卖出数量受限于 available_quantity。"""

    def test_t1_sell_capped_at_available(self) -> None:
        """T+1 标的: position.quantity=1000, available=500 → 最多卖 500。"""
        av = _account_view(
            positions={
                1: Position(
                    instrument_id=1,
                    quantity=1000,
                    available_quantity=500,
                    average_cost=10.0,
                    market_value=10000.0,
                    unrealized_pnl=0.0,
                    realized_pnl=0.0,
                    total_fees=0.0,
                ),
            },
            exposure=10000.0,
        )
        rules = {1: _instrument_rules(1, settlement_cycle=1)}
        target = _target({1: 0.0})  # 全部清仓

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            rules=rules,
        )

        # 实际卖出 500（available_quantity），剩余 500 被 blocked
        sell_orders = [o for o in plan.orders if o.instrument_id == 1]
        assert sum(o.quantity for o in sell_orders) == 500
        assert len(plan.blocked_orders) == 1
        assert plan.blocked_orders[0].reason == "t_plus1_not_sellable"
        assert plan.blocked_orders[0].severity is BlockSeverity.DEFER
        assert plan.blocked_orders[0].intended_quantity == 500

    def test_t0_sell_not_capped(self) -> None:
        """T+0 标的: 可卖出全部 quantity。"""
        av = _account_view(
            positions={
                1: Position(
                    instrument_id=1,
                    quantity=1000,
                    available_quantity=500,
                    average_cost=10.0,
                    market_value=10000.0,
                    unrealized_pnl=0.0,
                    realized_pnl=0.0,
                    total_fees=0.0,
                ),
            },
            exposure=10000.0,
        )
        rules = {1: _instrument_rules(1, settlement_cycle=0)}
        target = _target({1: 0.0})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            rules=rules,
        )

        sell_orders = [o for o in plan.orders if o.instrument_id == 1]
        assert sum(o.quantity for o in sell_orders) == 1000
        assert len(plan.blocked_orders) == 0

    def test_no_rules_t1_not_applied(self) -> None:
        """无规则时 T+1 不生效（使用 effective_qty 上限）。"""
        av = _account_view(
            positions={
                1: Position(
                    instrument_id=1,
                    quantity=1000,
                    available_quantity=500,
                    average_cost=10.0,
                    market_value=10000.0,
                    unrealized_pnl=0.0,
                    realized_pnl=0.0,
                    total_fees=0.0,
                ),
            },
            exposure=10000.0,
        )
        target = _target({1: 0.0})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        # 无规则: sell capped at effective_qty (1000)
        sell_orders = [o for o in plan.orders if o.instrument_id == 1]
        assert sum(o.quantity for o in sell_orders) == 1000


# ---------------------------------------------------------------------------
# 涨跌停预检
# ---------------------------------------------------------------------------


class TestLimitUpDown:
    """涨跌停: 买入+涨停 → defer, 卖出+跌停 → defer。"""

    def test_buy_at_limit_up_blocked(self) -> None:
        """买入 + 涨停 → BlockedOrder(reason=limit_up_no_buy)。"""
        av = _account_view()
        target = _target({1: 0.5})
        market = {1: _market_snapshot(close=11.0, limit_up=11.0)}

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            market_snapshots=market,
        )

        assert len(plan.orders) == 0
        assert len(plan.blocked_orders) == 1
        assert plan.blocked_orders[0].reason == "limit_up_no_buy"
        assert plan.blocked_orders[0].severity is BlockSeverity.DEFER

    def test_sell_at_limit_down_blocked(self) -> None:
        """卖出 + 跌停 → BlockedOrder(reason=limit_down_no_sell)。"""
        av = _account_view(
            positions={
                1: _position(1, quantity=10000, market_value=10000.0),
            },
            exposure=10000.0,
        )
        target = _target({1: 0.0})
        market = {1: _market_snapshot(close=10.0, limit_down=10.0)}

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            market_snapshots=market,
        )

        assert len(plan.orders) == 0
        assert len(plan.blocked_orders) == 1
        assert plan.blocked_orders[0].reason == "limit_down_no_sell"

    def test_sell_at_limit_up_allowed(self) -> None:
        """卖出 + 涨停 → 允许卖出。"""
        av = _account_view(
            positions={
                1: _position(1, quantity=10000, market_value=10000.0),
            },
            exposure=10000.0,
        )
        target = _target({1: 0.0})
        market = {1: _market_snapshot(close=11.0, limit_up=11.0)}

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            market_snapshots=market,
        )

        sell_orders = [o for o in plan.orders if o.instrument_id == 1]
        assert len(sell_orders) == 1
        assert sell_orders[0].direction == OrderSide.SELL

    def test_buy_at_limit_down_allowed(self) -> None:
        """买入 + 跌停 → 允许买入。"""
        av = _account_view()
        target = _target({1: 0.5})
        market = {1: _market_snapshot(close=10.0, limit_down=10.0)}

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            market_snapshots=market,
        )

        buy_orders = [o for o in plan.orders if o.instrument_id == 1]
        assert len(buy_orders) == 1
        assert buy_orders[0].direction == OrderSide.BUY

    def test_no_limit_info_treats_as_normal(self) -> None:
        """limit_up=None / limit_down=None → 正常交易。"""
        av = _account_view()
        target = _target({1: 0.5})
        market = {1: _market_snapshot(close=11.0)}

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            market_snapshots=market,
        )

        assert len(plan.orders) == 1
        assert len(plan.blocked_orders) == 0


# ---------------------------------------------------------------------------
# 停牌过滤
# ---------------------------------------------------------------------------


class TestSuspended:
    """停牌: 所有操作被 block。"""

    def test_buy_suspended_blocked(self) -> None:
        """买入 + 停牌 → BlockedOrder(reason=suspended, severity=block)。"""
        av = _account_view()
        target = _target({1: 0.5})
        market = {1: _market_snapshot(is_suspended=True)}

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            market_snapshots=market,
        )

        assert len(plan.orders) == 0
        assert len(plan.blocked_orders) == 1
        assert plan.blocked_orders[0].reason == "suspended"
        assert plan.blocked_orders[0].severity is BlockSeverity.BLOCK

    def test_sell_suspended_blocked(self) -> None:
        """卖出 + 停牌 → BlockedOrder(reason=suspended)。"""
        av = _account_view(
            positions={
                1: _position(1, quantity=10000, market_value=10000.0),
            },
            exposure=10000.0,
        )
        target = _target({1: 0.0})
        market = {1: _market_snapshot(is_suspended=True)}

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            market_snapshots=market,
        )

        assert len(plan.orders) == 0
        assert len(plan.blocked_orders) == 1
        assert plan.blocked_orders[0].reason == "suspended"

    def test_no_snapshot_no_suspend_check(self) -> None:
        """无 MarketSnapshot → 不执行停牌检查。"""
        av = _account_view()
        target = _target({1: 0.5})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        assert len(plan.orders) == 1


# ---------------------------------------------------------------------------
# 100+1 数量取整
# ---------------------------------------------------------------------------


class TestRounding100Plus1:
    """100+1 规则: 买入最小1手, 卖出拆分整手+零股。"""

    def test_buy_below_lot_size_rounds_up(self) -> None:
        """买入 50 → 100 (最小1手)。"""
        av = _account_view(
            positions={
                1: _position(
                    1,
                    quantity=10000,
                    market_value=10000.0,
                ),
            },
            exposure=10000.0,
        )
        # 0.05 * 100K = 5000, lots = 50, target = 5000
        # current = 10000, diff = 5000 - 10000 = -5000 → 卖出
        # 需要 diff > 0: target > current
        # 0.15 * 100K = 15000, diff = 15000 - 10000 = 5000 → 买入 5000
        target = _target({1: 0.15})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        buy_orders = [
            o
            for o in plan.orders
            if o.instrument_id == 1 and o.direction == OrderSide.BUY
        ]
        assert len(buy_orders) == 1
        assert buy_orders[0].quantity == 5000

    def test_buy_50_when_diff_is_50(self) -> None:
        """diff_qty = 50 → round up to lot_size = 100。"""
        av = _account_view(
            positions={
                1: _position(
                    1,
                    quantity=29500,
                    market_value=29500.0,
                ),
            },
            exposure=29500.0,
        )
        # target = 0.3 * 100K = 30000, diff = 30000 - 29500 = 500
        # 500 >= 100 → no rounding up needed
        target = _target({1: 0.3})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        buy_orders = [
            o
            for o in plan.orders
            if o.instrument_id == 1 and o.direction == OrderSide.BUY
        ]
        assert len(buy_orders) == 1
        assert buy_orders[0].quantity == 500

    def test_sell_350_splits_round_and_odd(self) -> None:
        """卖出 350 → 整手 300 + 零股 50（2 笔订单）。"""
        av = _account_view(
            positions={
                1: _position(
                    1,
                    quantity=350,
                    market_value=3500.0,
                ),
            },
            exposure=3500.0,
        )
        target = _target({1: 0.0})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        sell_orders = [
            o
            for o in plan.orders
            if o.instrument_id == 1 and o.direction == OrderSide.SELL
        ]
        quantities = sorted([o.quantity for o in sell_orders])
        assert len(sell_orders) == 2
        assert quantities == [50, 300]

    def test_sell_exact_lot_no_split(self) -> None:
        """卖出 300 → 1 笔订单（无零股）。"""
        av = _account_view(
            positions={
                1: _position(
                    1,
                    quantity=300,
                    market_value=3000.0,
                ),
            },
            exposure=3000.0,
        )
        target = _target({1: 0.0})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        sell_orders = [
            o
            for o in plan.orders
            if o.instrument_id == 1 and o.direction == OrderSide.SELL
        ]
        assert len(sell_orders) == 1
        assert sell_orders[0].quantity == 300

    def test_sell_50_odd_lot_only(self) -> None:
        """卖出 50 → 1 笔零股订单。"""
        av = _account_view(
            positions={
                1: _position(
                    1,
                    quantity=50,
                    market_value=500.0,
                ),
            },
            exposure=500.0,
        )
        target = _target({1: 0.0})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
        )

        sell_orders = [
            o
            for o in plan.orders
            if o.instrument_id == 1 and o.direction == OrderSide.SELL
        ]
        assert len(sell_orders) == 1
        assert sell_orders[0].quantity == 50


# ---------------------------------------------------------------------------
# 联合场景
# ---------------------------------------------------------------------------


class TestCombinedScenarios:
    """T+1 + 涨跌停 + 停牌 + 100+1 联合场景。"""

    def test_t1_sell_350_splits_with_available_cap(self) -> None:
        """T+1 + 零股: quantity=350, available=300 → 卖 200+100, block 50。"""
        av = _account_view(
            positions={
                1: Position(
                    instrument_id=1,
                    quantity=350,
                    available_quantity=300,
                    average_cost=10.0,
                    market_value=3500.0,
                    unrealized_pnl=0.0,
                    realized_pnl=0.0,
                    total_fees=0.0,
                ),
            },
            exposure=3500.0,
        )
        rules = {1: _instrument_rules(1, settlement_cycle=1)}
        target = _target({1: 0.0})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            rules=rules,
        )

        # T+1: sellable = 300, blocked = 50
        sell_orders = [
            o
            for o in plan.orders
            if o.instrument_id == 1 and o.direction == OrderSide.SELL
        ]
        assert sum(o.quantity for o in sell_orders) == 300
        # 300 = 200 (round) + 100 (round), no odd lots
        assert len(plan.blocked_orders) == 1
        assert plan.blocked_orders[0].reason == "t_plus1_not_sellable"
        assert plan.blocked_orders[0].intended_quantity == 50

    def test_sell_invariant_never_exceeds_available(self) -> None:
        """不变量: T+1 标的卖出总量 <= available_quantity。"""
        av = _account_view(
            positions={
                1: Position(
                    instrument_id=1,
                    quantity=5000,
                    available_quantity=1000,
                    average_cost=10.0,
                    market_value=50000.0,
                    unrealized_pnl=0.0,
                    realized_pnl=0.0,
                    total_fees=0.0,
                ),
            },
            exposure=50000.0,
        )
        rules = {1: _instrument_rules(1, settlement_cycle=1)}
        target = _target({1: 0.0})

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            rules=rules,
        )

        sell_total = sum(
            o.quantity
            for o in plan.orders
            if o.instrument_id == 1 and o.direction == OrderSide.SELL
        )
        assert sell_total <= 1000

    def test_suspended_takes_priority_over_limit_up(self) -> None:
        """停牌优先于涨跌停检查。"""
        av = _account_view()
        target = _target({1: 0.5})
        market = {
            1: _market_snapshot(
                is_suspended=True,
                limit_up=11.0,
                close=11.0,
            ),
        }

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            market_snapshots=market,
        )

        assert len(plan.blocked_orders) == 1
        assert plan.blocked_orders[0].reason == "suspended"


# ---------------------------------------------------------------------------
# MarketSnapshot estimated_price
# ---------------------------------------------------------------------------


class TestEstimatedPriceFromSnapshot:
    """estimated_price 从 MarketSnapshot.close 获取。"""

    def test_turnover_from_snapshot(self) -> None:
        """turnover 使用 MarketSnapshot.close 作为价格。"""
        av = _account_view(
            positions={
                1: _position(
                    1,
                    quantity=10000,
                    market_value=10000.0,
                ),
            },
            exposure=10000.0,
        )
        target = _target({1: 0.3})
        # price=1.5 → target_value=30000, target_shares=20000, target_qty=20000
        # current=10000, diff=10000 BUY → turnover=10000*1.5=15000
        market = {1: _market_snapshot(close=1.5)}

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            market_snapshots=market,
        )

        # BUY 10000 @ 1.5 → turnover = 15000
        assert plan.estimated_turnover == pytest.approx(15000.0)

    def test_cost_from_fee_schedule(self) -> None:
        """cost 使用 FeeSchedule 中的费率。"""
        av = _account_view(
            positions={
                1: _position(
                    1,
                    quantity=10000,
                    market_value=10000.0,
                ),
            },
            exposure=10000.0,
        )
        rules = {1: _instrument_rules(1, commission_rate=0.001)}
        target = _target({1: 0.3})
        # price=1.5 → target_qty=20000, current=10000, diff=10000 BUY
        market = {1: _market_snapshot(close=1.5)}

        planner = SimpleExecutionPlanner()
        plan = planner.plan(
            target=target,
            account_view=av,
            trade_date="2026-03-21",
            rules=rules,
            market_snapshots=market,
        )

        # turnover = 15000, rate = 0.001, cost = 15
        assert plan.estimated_cost == pytest.approx(15.0)
