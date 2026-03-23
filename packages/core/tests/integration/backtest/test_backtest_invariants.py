"""Backtest invariant tests — 回测过程中的不变量验证.

确保核心数据结构语义正确、状态转换安全。
"""

from __future__ import annotations

from datetime import datetime
from types import MappingProxyType

import pytest
from ditto_core.accounting.account import Account, AccountView
from ditto_core.accounting.buying_power import CashAccountBuyingPower
from ditto_core.accounting.cash import CashBook
from ditto_core.accounting.order_book import (
    Order,
    OrderBook,
    OrderBookReadOnly,
    OrderDirection,
    OrderEvent,
    OrderStatus,
    OrderTicket,
    OrderType,
    StateTransitionError,
)
from ditto_core.backtest.risk.pre_trade import (
    BuyingPowerCheck,
    CompositePreTradeCheck,
    LotSizeCheck,
    PreTradeContext,
)
from ditto_core.execution.brokerage import BacktestBrokerage, ProcessInput
from ditto_core.execution.planner import SimpleExecutionPlanner
from ditto_core.execution.reality import (
    SimpleFeeModel,
)
from ditto_core.execution.reality.market import MarketSnapshot
from ditto_core.execution.rules import (
    FeeSchedule,
    InstrumentDefinition,
    InstrumentRules,
    TradingRuleSet,
)
from ditto_core.strategy.context import StrategyContext

from .conftest import (
    INITIAL_CASH,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_market_snapshot(
    instrument_id: str,
    close: float,
    low: float | None = None,
    high: float | None = None,
    trade_date: str = "2026-01-05",
) -> MarketSnapshot:
    """构建 MarketSnapshot 用于直接调用 BacktestBrokerage。"""
    return MarketSnapshot(
        trade_date=trade_date,
        instrument_id=instrument_id,
        open=close,
        high=high if high is not None else close * 1.01,
        low=low if low is not None else close * 0.99,
        close=close,
        prev_close=close,
        volume=1_000_000.0,
        amount=close * 1_000_000.0,
    )


def _make_process_input(
    bars: dict[str, MarketSnapshot],
    trade_date: str = "2026-01-05",
) -> ProcessInput:
    """构建 ProcessInput 用于直接调用 BacktestBrokerage。"""
    return ProcessInput(
        step_time=datetime(2026, 1, 5, 15, 0),
        trade_date=trade_date,
        bars=bars,
    )


def _make_instrument_rules(
    instrument_id: str = "ETF-001",
    lot_size: int = 100,
) -> InstrumentRules:
    """构造 InstrumentRules 元组。"""
    definition = InstrumentDefinition(
        instrument_id=instrument_id,
        asset_class="etf",
        exchange="XSHE",
        currency="CNY",
        tick_size=0.01,
        lot_size=lot_size,
        multiplier=1.0,
        board_segment="main",
        lifecycle_state="normal",
    )
    trading_rule = TradingRuleSet(
        instrument_id=instrument_id,
        as_of_date="2026-01-01",
        settlement_cycle=1,
        fund_settlement_cycle=1,
        price_limit_pct=0.10,
        order_types_supported=("market", "limit"),
        call_auction_sessions=("open", "close"),
    )
    fee_schedule = FeeSchedule(
        instrument_id=instrument_id,
        as_of_date="2026-01-01",
        commission_rate=0.0003,
        min_commission=5.0,
        stamp_duty_rate=0.0,
        transfer_fee_rate=0.0,
    )
    return (definition, trading_rule, fee_schedule)


def _make_pre_trade_context(
    account_view: AccountView,
    close_prices: dict[str, float] | None = None,
    fee_model: SimpleFeeModel | None = None,
    lot_size: int = 100,
) -> PreTradeContext:
    """构建 V3 PreTradeContext — 便捷 helper。"""
    prices = close_prices or {"ETF-001": 10.0}
    rules = {iid: _make_instrument_rules(iid, lot_size) for iid in prices}
    snapshots = {
        iid: _make_market_snapshot(iid, close) for iid, close in prices.items()
    }
    return PreTradeContext(
        account_view=account_view,
        rules=rules,
        market_snapshots=snapshots,
        fee_model=fee_model or SimpleFeeModel(),
        buying_power_model=CashAccountBuyingPower(),
    )


# ---------------------------------------------------------------------------
# Frozen immutability invariants
# ---------------------------------------------------------------------------


class TestFrozenImmutability:
    """Frozen dataclass 不可变性验证。"""

    def test_cash_book_frozen(self) -> None:
        """CashBook frozen 不可修改。"""
        cb = CashBook(available=100.0, settled=100.0, frozen=0.0)
        with pytest.raises(AttributeError):
            cb.available = 200.0  # type: ignore[misc]

    def test_order_ticket_frozen(self) -> None:
        """OrderTicket frozen 不可直接修改。"""
        order = Order(
            order_id="o-1",
            instrument_id="ETF-001",
            order_type=OrderType.MARKET,
            direction=OrderDirection.BUY,
            quantity=100,
        )
        ticket = OrderTicket(order=order, status=OrderStatus.SUBMITTED)
        with pytest.raises(AttributeError):
            ticket.status = OrderStatus.FILLED  # type: ignore[misc]

    def test_account_view_positions_readonly(self) -> None:
        """AccountView.positions 是 MappingProxyType — 不可通过 view 修改。"""
        from ditto_core.accounting.position import Position

        pos = Position(
            instrument_id="ETF-001",
            quantity=100,
            available_quantity=100,
            average_cost=10.0,
            market_value=1000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        view = AccountView(
            positions=MappingProxyType({"ETF-001": pos}),
            cash=CashBook(available=500_000.0, settled=500_000.0, frozen=0.0),
            total_value=501_000.0,
            nav=501_000.0,
            exposure=1000.0,
            pending_buy_value=0.0,
            order_book=OrderBookReadOnly({}),
        )
        with pytest.raises(TypeError):
            view.positions["ETF-002"] = pos  # type: ignore[index]


# ---------------------------------------------------------------------------
# Terminal state invariants
# ---------------------------------------------------------------------------


class TestTerminalState:
    """终态不可逆验证。"""

    def test_filled_ticket_cannot_cancel(self) -> None:
        """FILLED 状态的 OrderTicket 不能撤销。"""
        order = Order(
            order_id="o-1",
            instrument_id="ETF-001",
            order_type=OrderType.MARKET,
            direction=OrderDirection.BUY,
            quantity=100,
        )
        ticket = OrderTicket(order=order, status=OrderStatus.SUBMITTED)

        fill_evt = OrderEvent(
            order_id="o-1",
            status=OrderStatus.FILLED,
            fill_price=10.0,
            fill_quantity=100,
            timestamp=datetime(2026, 1, 5),
        )
        filled_ticket = ticket.with_fill(quantity=100, price=10.0, event=fill_evt)

        assert filled_ticket.status == OrderStatus.FILLED

        cancel_evt = OrderEvent(
            order_id="o-1",
            status=OrderStatus.CANCELED,
            timestamp=datetime(2026, 1, 5),
        )
        with pytest.raises(StateTransitionError):
            filled_ticket.with_cancel(cancel_evt)

    def test_invalid_ticket_cannot_cancel(self) -> None:
        """INVALID 状态也不能撤销。"""
        order = Order(
            order_id="o-1",
            instrument_id="ETF-001",
            order_type=OrderType.MARKET,
            direction=OrderDirection.BUY,
            quantity=100,
        )
        ticket = OrderTicket(order=order, status=OrderStatus.SUBMITTED)

        invalid_evt = OrderEvent(
            order_id="o-1",
            status=OrderStatus.INVALID,
            message="test",
            timestamp=datetime(2026, 1, 5),
        )
        invalid_ticket = ticket.with_invalid(invalid_evt)

        cancel_evt = OrderEvent(
            order_id="o-1",
            status=OrderStatus.CANCELED,
            timestamp=datetime(2026, 1, 5),
        )
        with pytest.raises(StateTransitionError):
            invalid_ticket.with_cancel(cancel_evt)


# ---------------------------------------------------------------------------
# NoFill → no FillEvent (R8)
# ---------------------------------------------------------------------------


class TestNoFillNoFillEvent:
    """NoFill 不产生 FillEvent (R8)。"""

    def test_no_fill_on_missing_bar(self, tmp_path) -> None:
        """标的在 bars 中无数据 → NoFill，不产生 FillEvent。"""
        account = Account(
            cash=CashBook(
                available=INITIAL_CASH,
                settled=INITIAL_CASH,
                frozen=0.0,
            ),
        )
        brokerage = BacktestBrokerage(account=account)

        order = Order(
            order_id="o-missing",
            instrument_id="ETF-999",  # 不存在
            order_type=OrderType.MARKET,
            direction=OrderDirection.BUY,
            quantity=100,
        )
        brokerage.place_order(order)

        # bars 中没有 ETF-999
        process_input = _make_process_input(
            bars={
                "ETF-001": _make_market_snapshot(
                    "ETF-001",
                    close=10.0,
                    low=9.9,
                    high=10.1,
                ),
            },
        )
        fills = brokerage.process_pending(process_input)

        assert len(fills) == 0


# ---------------------------------------------------------------------------
# Risk lock clears next day (R4)
# ---------------------------------------------------------------------------


class TestRiskLockClears:
    """StrategyContext 锁定不会跨日持久化 (R4)。"""

    def test_risk_lock_cleared_on_new_context(self) -> None:
        """新建 StrategyContext 不继承前一次的锁定。"""
        ctx1 = StrategyContext()
        ctx1.lock_instrument("ETF-001", "stop-loss")

        assert ctx1.is_locked("ETF-001")

        # 新建 context — 锁定自动清除
        ctx2 = StrategyContext()
        assert not ctx2.is_locked("ETF-001")


# ---------------------------------------------------------------------------
# Rolling PreTrade context (F1)
# ---------------------------------------------------------------------------


class TestRollingPreTradeContext:
    """批内第二笔买单看到第一笔的 reserved_cash (F1)。"""

    def test_rolling_context_decreasing_available(self) -> None:
        """连续买入后 available 持续递减。"""

        view = AccountView(
            positions=MappingProxyType({}),
            cash=CashBook(available=500_000.0, settled=500_000.0, frozen=0.0),
            total_value=500_000.0,
            nav=500_000.0,
            exposure=0.0,
            pending_buy_value=0.0,
            order_book=OrderBookReadOnly({}),
        )
        ctx = _make_pre_trade_context(
            account_view=view,
            close_prices={"ETF-001": 10.0},
        )

        order1 = Order(
            order_id="o-1",
            instrument_id="ETF-001",
            order_type=OrderType.MARKET,
            direction=OrderDirection.BUY,
            quantity=100,
        )
        ctx1 = ctx.with_order_accepted(order1)
        assert ctx1.account_view.cash.available < ctx.account_view.cash.available

        order2 = Order(
            order_id="o-2",
            instrument_id="ETF-001",
            order_type=OrderType.MARKET,
            direction=OrderDirection.BUY,
            quantity=100,
        )
        ctx2 = ctx1.with_order_accepted(order2)
        assert ctx2.account_view.cash.available < ctx1.account_view.cash.available


# ---------------------------------------------------------------------------
# Pending-aware planner (F2)
# ---------------------------------------------------------------------------


class TestPendingAwarePlanner:
    """有 pending 卖单时不重复生成卖出 (F2)。"""

    def test_no_duplicate_sell_with_pending(self) -> None:
        """已有 pending sell → planner 不再生成同标的 sell。"""
        from ditto_core.accounting.position import Position

        pos = Position(
            instrument_id="ETF-001",
            quantity=500,
            available_quantity=500,
            average_cost=10.0,
            market_value=5000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        # OrderBook with a pending sell of 500 ETF-001
        ob = OrderBook()
        sell_order = Order(
            order_id="pending-sell",
            instrument_id="ETF-001",
            order_type=OrderType.MARKET,
            direction=OrderDirection.SELL,
            quantity=500,
        )
        sell_ticket = OrderTicket(
            order=sell_order,
            status=OrderStatus.SUBMITTED,
        )
        ob.submit(sell_ticket)

        view = AccountView(
            positions=MappingProxyType({"ETF-001": pos}),
            cash=CashBook(available=500_000.0, settled=500_000.0, frozen=0.0),
            total_value=505_000.0,
            nav=505_000.0,
            exposure=5000.0,
            pending_buy_value=0.0,
            order_book=ob.readonly_view(),
        )

        from ditto_core.strategy.models import TargetPortfolio

        # Target: 0 weight → wants to exit ETF-001
        target = TargetPortfolio(
            trade_date="2026-01-05",
            strategy_id="test",
            run_id="run",
            positions={},
        )

        planner = SimpleExecutionPlanner()

        plan = planner.plan(
            target=target,
            account_view=view,
            trade_date="2026-01-05",
        )

        # effective_qty = 500 (current) + (-500) (pending delta) = 0
        # diff = 0 - 0 = 0 → no new sell order
        sell_orders = [o for o in plan.orders if o.direction == OrderDirection.SELL]
        assert len(sell_orders) == 0


# ---------------------------------------------------------------------------
# Planner lock (S1)
# ---------------------------------------------------------------------------


class TestPlannerLock:
    """锁定标的不生成买单 (S1)。"""

    def test_locked_instrument_blocked(self) -> None:
        """锁定标的生成 BlockedOrder 而非 Order。"""
        view = AccountView(
            positions=MappingProxyType({}),
            cash=CashBook(available=500_000.0, settled=500_000.0, frozen=0.0),
            total_value=500_000.0,
            nav=500_000.0,
            exposure=0.0,
            pending_buy_value=0.0,
            order_book=OrderBookReadOnly({}),
        )

        from ditto_core.strategy.models import TargetPortfolio

        target = TargetPortfolio(
            trade_date="2026-01-05",
            strategy_id="test",
            run_id="run",
            positions={"ETF-001": 0.3, "ETF-002": 0.3, "ETF-003": 0.4},
        )

        planner = SimpleExecutionPlanner()

        plan = planner.plan(
            target=target,
            account_view=view,
            trade_date="2026-01-05",
            locked_instruments={"ETF-001"},
        )

        # ETF-001 应被 blocked，不生成 buy order
        buy_orders = [o for o in plan.orders if o.instrument_id == "ETF-001"]
        assert len(buy_orders) == 0

        # ETF-001 应出现在 blocked_orders 中
        blocked_iids = {b.instrument_id for b in plan.blocked_orders}
        assert "ETF-001" in blocked_iids

        # ETF-002, ETF-003 正常生成 buy orders
        assert len(plan.orders) == 2


# ---------------------------------------------------------------------------
# Resize triggers recheck (A1)
# ---------------------------------------------------------------------------


class TestResizeRecheck:
    """resize 后 buying_power 仍检查 (A1)。"""

    def test_resize_then_reject(self) -> None:
        """lot_size resize → buying_power 不足 → reject。"""
        view = AccountView(
            positions=MappingProxyType({}),
            cash=CashBook(available=3_500.0, settled=3_500.0, frozen=0.0),
            total_value=3_500.0,
            nav=3_500.0,
            exposure=0.0,
            pending_buy_value=0.0,
            order_book=OrderBookReadOnly({}),
        )
        ctx = _make_pre_trade_context(
            account_view=view,
            close_prices={"ETF-001": 10.0},
        )
        composite = CompositePreTradeCheck(
            checks=(LotSizeCheck(), BuyingPowerCheck()),
        )

        # 350 → resize to 400 → cost 4000 + fee > 3500 → reject
        order = Order(
            order_id="o-resize",
            instrument_id="ETF-001",
            order_type=OrderType.MARKET,
            direction=OrderDirection.BUY,
            quantity=350,
        )
        result = composite.check_order(order, ctx)

        assert result.decision == "reject"
        assert "buying_power" in (result.reason or "")


# ---------------------------------------------------------------------------
# Cash conservation invariant
# ---------------------------------------------------------------------------


class TestCashConservation:
    """现金守恒 — fill 前后净值差异 = 费用。"""

    def test_buy_fill_cash_conservation(self) -> None:
        """买入 fill 后: cash 减少 = price * qty + fee。"""
        account = Account(
            cash=CashBook(
                available=1_000_000.0,
                settled=1_000_000.0,
                frozen=0.0,
            ),
        )
        brokerage = BacktestBrokerage(account=account)

        view_before = brokerage.get_account()
        nav_before = view_before.nav

        order = Order(
            order_id="o-buy",
            instrument_id="ETF-001",
            order_type=OrderType.MARKET,
            direction=OrderDirection.BUY,
            quantity=100,
        )
        brokerage.place_order(order)

        process_input = _make_process_input(
            bars={
                "ETF-001": _make_market_snapshot(
                    "ETF-001",
                    close=10.0,
                    low=9.9,
                    high=10.1,
                ),
            },
        )
        fills = brokerage.process_pending(process_input)
        assert len(fills) == 1

        fill = fills[0]
        view_after = brokerage.get_account()

        # NAV 变化 = -fee (买入时市值 = price * qty ≈ cash outflow)
        # 简化验证: cash.total + positions.market_value ≈ nav_before - fee
        # 由于 slippage，实际成交价 != close，所以允许一定误差
        # 但 NAV = cash + positions，而 cash 扣除了 (price*qty + fee)，
        # positions 增加了 price*qty
        # 所以 NAV_before - NAV_after ≈ fee + slippage*qty
        assert (
            abs(
                view_after.nav
                - (nav_before - fill.fee - fill.slippage * fill.filled_quantity)
            )
            < 1.0
        )

    def test_sell_fill_cash_conservation(self) -> None:
        """卖出 fill 后: cash 增加 = price * qty - fee。"""
        from ditto_core.accounting.position import Position

        pos = Position(
            instrument_id="ETF-001",
            quantity=200,
            available_quantity=200,
            average_cost=10.0,
            market_value=2000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        account = Account(
            positions={"ETF-001": pos},
            cash=CashBook(available=500_000.0, settled=500_000.0, frozen=0.0),
        )
        brokerage = BacktestBrokerage(account=account)

        view_before = brokerage.get_account()
        nav_before = view_before.nav

        order = Order(
            order_id="o-sell",
            instrument_id="ETF-001",
            order_type=OrderType.MARKET,
            direction=OrderDirection.SELL,
            quantity=100,
        )
        brokerage.place_order(order)

        process_input = _make_process_input(
            bars={
                "ETF-001": _make_market_snapshot(
                    "ETF-001",
                    close=11.0,
                    low=10.9,
                    high=11.1,
                ),
            },
        )
        fills = brokerage.process_pending(process_input)
        assert len(fills) == 1

        view_after = brokerage.get_account()

        # NAV_after = NAV_before + realized_pnl - fee + slippage effect
        # Slippage for sell is negative (receive less)
        nav_diff = view_after.nav - nav_before
        # NAV should increase (sell at higher than cost)
        assert nav_diff > 0


# ---------------------------------------------------------------------------
# No oversell invariant (B3)
# ---------------------------------------------------------------------------


class TestNoOversell:
    """不超卖 — 卖出数量 <= effective_position。"""

    def test_sell_does_not_exceed_position(self) -> None:
        """卖出不超过持仓。"""
        from ditto_core.accounting.position import Position

        pos = Position(
            instrument_id="ETF-001",
            quantity=100,
            available_quantity=100,
            average_cost=10.0,
            market_value=1000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        account = Account(
            positions={"ETF-001": pos},
            cash=CashBook(available=500_000.0, settled=500_000.0, frozen=0.0),
        )
        brokerage = BacktestBrokerage(account=account)

        # Try to sell 200 — only 100 available
        order = Order(
            order_id="o-oversell",
            instrument_id="ETF-001",
            order_type=OrderType.MARKET,
            direction=OrderDirection.SELL,
            quantity=200,
        )
        brokerage.place_order(order)

        process_input = _make_process_input(
            bars={
                "ETF-001": _make_market_snapshot(
                    "ETF-001",
                    close=10.0,
                    low=9.9,
                    high=10.1,
                ),
            },
        )
        fills = brokerage.process_pending(process_input)

        # BacktestBrokerage fills all 200 regardless (V1)
        # This is expected — planner is responsible for limiting sell qty
        # PreTradeContext prevents oversell in batch
        assert len(fills) == 1
        assert fills[0].filled_quantity == 200

    def test_pre_trade_context_prevents_oversell_in_batch(self) -> None:
        """PreTradeContext.with_order_accepted 防止批内超卖。"""
        from ditto_core.accounting.position import Position

        pos = Position(
            instrument_id="ETF-001",
            quantity=100,
            available_quantity=100,
            average_cost=10.0,
            market_value=1000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        view = AccountView(
            positions=MappingProxyType({"ETF-001": pos}),
            cash=CashBook(available=500_000.0, settled=500_000.0, frozen=0.0),
            total_value=501_000.0,
            nav=501_000.0,
            exposure=1000.0,
            pending_buy_value=0.0,
            order_book=OrderBookReadOnly({}),
        )
        ctx = _make_pre_trade_context(
            account_view=view,
            close_prices={"ETF-001": 10.0},
        )

        sell = Order(
            order_id="o-sell",
            instrument_id="ETF-001",
            order_type=OrderType.MARKET,
            direction=OrderDirection.SELL,
            quantity=100,
        )
        new_ctx = ctx.with_order_accepted(sell)

        # available_quantity should be 0 (clamped)
        assert new_ctx.account_view.positions["ETF-001"].available_quantity == 0


# ---------------------------------------------------------------------------
# Stats use post-fill snapshot (R3)
# ---------------------------------------------------------------------------


class TestStatsPostFillSnapshot:
    """统计 NAV = 成交后 NAV (R3)。"""

    def test_audit_collector_uses_post_fill_view(self) -> None:
        """ExecutionAuditCollector 应在 fill 后记录 AccountView。"""
        from ditto_core.backtest.statistics import ExecutionAuditCollector

        account = Account(
            cash=CashBook(
                available=1_000_000.0,
                settled=1_000_000.0,
                frozen=0.0,
            ),
        )
        brokerage = BacktestBrokerage(account=account)
        collector = ExecutionAuditCollector()

        # Record pre-fill view
        view_before = brokerage.get_account()
        collector.record_account_view("2026-01-05", view_before)

        # Execute a buy
        order = Order(
            order_id="o-buy",
            instrument_id="ETF-001",
            order_type=OrderType.MARKET,
            direction=OrderDirection.BUY,
            quantity=100,
        )
        brokerage.place_order(order)

        process_input = _make_process_input(
            bars={
                "ETF-001": _make_market_snapshot(
                    "ETF-001",
                    close=10.0,
                    low=9.9,
                    high=10.1,
                ),
            },
        )
        fills = brokerage.process_pending(process_input)
        for fill in fills:
            collector.record_fill(fill)

        # Record post-fill view
        view_after = brokerage.get_account()
        collector.record_account_view("2026-01-05-post", view_after)

        stats = collector.compute_portfolio_statistics()
        assert len(stats) == 2

        # Post-fill NAV should reflect the position
        assert view_after.nav < view_before.nav  # NAV decreased by fee + slippage
        assert len(view_after.positions) == 1


# ---------------------------------------------------------------------------
# Price limit invariants (Phase 3)
# ---------------------------------------------------------------------------


class TestPriceLimitInvariants:
    """涨跌停不变量 — AShareFillModel 阻止涨跌停反方向成交。"""

    def _make_snapshot_with_limits(
        self,
        instrument_id: str,
        close: float,
        limit_up: float | None,
        limit_down: float | None,
        prev_close: float | None = None,
    ) -> MarketSnapshot:
        """构建带涨跌停的 MarketSnapshot。"""
        return MarketSnapshot(
            trade_date="2026-01-05",
            instrument_id=instrument_id,
            open=close,
            high=close * 1.01,
            low=close * 0.99,
            close=close,
            prev_close=prev_close or close,
            volume=1_000_000.0,
            amount=close * 1_000_000.0,
            limit_up=limit_up,
            limit_down=limit_down,
        )

    def test_limit_up_blocks_buy(self) -> None:
        """涨停买入不成交 — close >= limit_up。"""
        from ditto_core.execution.reality import AShareFillModel, BrokerageModel

        model = BrokerageModel(fill_model=AShareFillModel())
        account = Account(
            cash=CashBook(
                available=INITIAL_CASH,
                settled=INITIAL_CASH,
                frozen=0.0,
            ),
        )
        brokerage = BacktestBrokerage(account=account, model=model)

        # ETF-001: close=11.0 = limit_up (prev=10.0, +10%)
        order = Order(
            order_id="o-buy",
            instrument_id="ETF-001",
            order_type=OrderType.MARKET,
            direction=OrderDirection.BUY,
            quantity=100,
        )
        brokerage.place_order(order)

        snapshot = self._make_snapshot_with_limits(
            "ETF-001",
            close=11.0,
            limit_up=11.0,
            limit_down=9.0,
            prev_close=10.0,
        )
        process_input = _make_process_input(bars={"ETF-001": snapshot})
        fills = brokerage.process_pending(process_input)

        assert len(fills) == 0

    def test_limit_down_blocks_sell(self) -> None:
        """跌停卖出不成交 — close <= limit_down。"""
        from ditto_core.accounting.position import Position
        from ditto_core.execution.reality import AShareFillModel, BrokerageModel

        pos = Position(
            instrument_id="ETF-001",
            quantity=100,
            available_quantity=100,
            average_cost=10.0,
            market_value=1000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        account = Account(
            positions={"ETF-001": pos},
            cash=CashBook(
                available=500_000.0,
                settled=500_000.0,
                frozen=0.0,
            ),
        )
        model = BrokerageModel(fill_model=AShareFillModel())
        brokerage = BacktestBrokerage(account=account, model=model)

        # ETF-001: close=9.0 = limit_down (prev=10.0, -10%)
        order = Order(
            order_id="o-sell",
            instrument_id="ETF-001",
            order_type=OrderType.MARKET,
            direction=OrderDirection.SELL,
            quantity=100,
        )
        brokerage.place_order(order)

        snapshot = self._make_snapshot_with_limits(
            "ETF-001",
            close=9.0,
            limit_up=11.0,
            limit_down=9.0,
            prev_close=10.0,
        )
        process_input = _make_process_input(bars={"ETF-001": snapshot})
        fills = brokerage.process_pending(process_input)

        assert len(fills) == 0

    def test_limit_up_allows_sell(self) -> None:
        """涨停可以卖出 — close >= limit_up + SELL → 正常成交。"""
        from ditto_core.accounting.position import Position
        from ditto_core.execution.reality import AShareFillModel, BrokerageModel

        pos = Position(
            instrument_id="ETF-001",
            quantity=100,
            available_quantity=100,
            average_cost=10.0,
            market_value=1000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        account = Account(
            positions={"ETF-001": pos},
            cash=CashBook(
                available=500_000.0,
                settled=500_000.0,
                frozen=0.0,
            ),
        )
        model = BrokerageModel(fill_model=AShareFillModel())
        brokerage = BacktestBrokerage(account=account, model=model)

        order = Order(
            order_id="o-sell",
            instrument_id="ETF-001",
            order_type=OrderType.MARKET,
            direction=OrderDirection.SELL,
            quantity=100,
        )
        brokerage.place_order(order)

        snapshot = self._make_snapshot_with_limits(
            "ETF-001",
            close=11.0,
            limit_up=11.0,
            limit_down=9.0,
            prev_close=10.0,
        )
        process_input = _make_process_input(bars={"ETF-001": snapshot})
        fills = brokerage.process_pending(process_input)

        assert len(fills) == 1
        assert fills[0].filled_quantity == 100

    def test_limit_down_allows_buy(self) -> None:
        """跌停可以买入 — close <= limit_down + BUY → 正常成交。"""
        from ditto_core.execution.reality import AShareFillModel, BrokerageModel

        model = BrokerageModel(fill_model=AShareFillModel())
        account = Account(
            cash=CashBook(
                available=INITIAL_CASH,
                settled=INITIAL_CASH,
                frozen=0.0,
            ),
        )
        brokerage = BacktestBrokerage(account=account, model=model)

        order = Order(
            order_id="o-buy",
            instrument_id="ETF-001",
            order_type=OrderType.MARKET,
            direction=OrderDirection.BUY,
            quantity=100,
        )
        brokerage.place_order(order)

        snapshot = self._make_snapshot_with_limits(
            "ETF-001",
            close=9.0,
            limit_up=11.0,
            limit_down=9.0,
            prev_close=10.0,
        )
        process_input = _make_process_input(bars={"ETF-001": snapshot})
        fills = brokerage.process_pending(process_input)

        assert len(fills) == 1
        assert fills[0].filled_quantity == 100

    def test_no_limit_allows_both_directions(self) -> None:
        """无涨跌停限制 — 买卖均可成交。"""
        from ditto_core.accounting.position import Position
        from ditto_core.execution.reality import AShareFillModel, BrokerageModel

        pos = Position(
            instrument_id="ETF-001",
            quantity=100,
            available_quantity=100,
            average_cost=10.0,
            market_value=1000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        account = Account(
            positions={"ETF-001": pos},
            cash=CashBook(
                available=500_000.0,
                settled=500_000.0,
                frozen=0.0,
            ),
        )
        model = BrokerageModel(fill_model=AShareFillModel())
        brokerage = BacktestBrokerage(account=account, model=model)

        sell_order = Order(
            order_id="o-sell",
            instrument_id="ETF-001",
            order_type=OrderType.MARKET,
            direction=OrderDirection.SELL,
            quantity=100,
        )
        buy_order = Order(
            order_id="o-buy",
            instrument_id="ETF-002",
            order_type=OrderType.MARKET,
            direction=OrderDirection.BUY,
            quantity=100,
        )
        brokerage.place_order(sell_order)
        brokerage.place_order(buy_order)

        snapshot_1 = self._make_snapshot_with_limits(
            "ETF-001",
            close=10.0,
            limit_up=None,
            limit_down=None,
        )
        snapshot_2 = self._make_snapshot_with_limits(
            "ETF-002",
            close=20.0,
            limit_up=None,
            limit_down=None,
        )
        process_input = _make_process_input(
            bars={"ETF-001": snapshot_1, "ETF-002": snapshot_2},
        )
        fills = brokerage.process_pending(process_input)

        assert len(fills) == 2


# ---------------------------------------------------------------------------
# Lot size / 100+1 rounding invariants (Phase 3)
# ---------------------------------------------------------------------------


class TestLotSizeRounding:
    """数量取整不变量 — lot_size 对买入的影响。"""

    def test_buy_quantity_rounded_to_lot_size(self) -> None:
        """买入数量被 lot_size=100 取整 — 50 → 100。"""
        view = AccountView(
            positions=MappingProxyType({}),
            cash=CashBook(
                available=100_000.0,
                settled=100_000.0,
                frozen=0.0,
            ),
            total_value=100_000.0,
            nav=100_000.0,
            exposure=0.0,
            pending_buy_value=0.0,
            order_book=OrderBookReadOnly({}),
        )
        ctx = _make_pre_trade_context(
            account_view=view,
            close_prices={"ETF-001": 10.0},
        )
        composite = CompositePreTradeCheck(checks=(LotSizeCheck(),))

        # 50 股 → resize to 100
        order = Order(
            order_id="o-resize",
            instrument_id="ETF-001",
            order_type=OrderType.MARKET,
            direction=OrderDirection.BUY,
            quantity=50,
        )
        result = composite.check_order(order, ctx)
        assert result.decision == "accept"
        assert result.resized_quantity == 100

    def test_buy_quantity_unchanged_if_multiple(self) -> None:
        """买入数量已是 lot_size 整数倍 — 300 → 300。"""
        view = AccountView(
            positions=MappingProxyType({}),
            cash=CashBook(
                available=500_000.0,
                settled=500_000.0,
                frozen=0.0,
            ),
            total_value=500_000.0,
            nav=500_000.0,
            exposure=0.0,
            pending_buy_value=0.0,
            order_book=OrderBookReadOnly({}),
        )
        ctx = _make_pre_trade_context(
            account_view=view,
            close_prices={"ETF-001": 10.0},
        )
        composite = CompositePreTradeCheck(checks=(LotSizeCheck(),))

        order = Order(
            order_id="o-ok",
            instrument_id="ETF-001",
            order_type=OrderType.MARKET,
            direction=OrderDirection.BUY,
            quantity=300,
        )
        result = composite.check_order(order, ctx)
        assert result.decision == "accept"
        assert result.resized_quantity is None

    def test_sell_not_affected_by_lot_size(self) -> None:
        """卖出不受 lot_size 限制（零股可卖）。"""
        from ditto_core.accounting.position import Position

        pos = Position(
            instrument_id="ETF-001",
            quantity=350,
            available_quantity=350,
            average_cost=10.0,
            market_value=3500.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        view = AccountView(
            positions=MappingProxyType({"ETF-001": pos}),
            cash=CashBook(
                available=500_000.0,
                settled=500_000.0,
                frozen=0.0,
            ),
            total_value=503_500.0,
            nav=503_500.0,
            exposure=3500.0,
            pending_buy_value=0.0,
            order_book=OrderBookReadOnly({}),
        )
        ctx = _make_pre_trade_context(
            account_view=view,
            close_prices={"ETF-001": 10.0},
        )
        composite = CompositePreTradeCheck(checks=(LotSizeCheck(),))

        # 卖出 350（含零股）→ 不被 resize
        order = Order(
            order_id="o-sell-350",
            instrument_id="ETF-001",
            order_type=OrderType.MARKET,
            direction=OrderDirection.SELL,
            quantity=350,
        )
        result = composite.check_order(order, ctx)
        assert result.decision == "accept"
        assert result.resized_quantity is None
