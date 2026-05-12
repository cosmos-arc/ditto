"""Backtest invariant tests — 回测过程中的不变量验证.

确保核心数据结构语义正确、状态转换安全。
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

import pytest
from ditto_backtest.brokerage import BacktestBrokerage
from ditto_backtest.simulation import (
    BrokerageModel,
)
from ditto_backtest.statistics import ExecutionAuditCollector
from ditto_backtest.synchronizer import (
    BacktestSynchronizer,
)
from ditto_execution.brokerage import ProcessInput
from ditto_execution.errors import OrderStateError
from ditto_execution.orders.book import OrderBook
from ditto_execution.orders.event import OrderEvent
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.journal import InMemoryOrderEventJournal
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.ticket import OrderTicket
from ditto_execution.orders.trigger import OrderTrigger
from ditto_execution.planner import SimpleExecutionPlanner
from ditto_execution.reality import SimpleFeeModel
from ditto_kernel.clock import SimulatedClock
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import (
    FeeSchedule,
    InstrumentDefinition,
    InstrumentRules,
    MarketSnapshot,
    TradingRuleSet,
)
from ditto_portfolio.accounting import (
    Account,
    AccountView,
    CashAccountBuyingPower,
    CashBook,
)
from ditto_risk.pre_trade import (
    BuyingPowerCheck,
    CompositePreTradeCheck,
    LotSizeCheck,
    PreTradeContext,
)
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.pipeline import StrategyPipeline

_conftest_path = Path(__file__).parent / "conftest.py"
_spec = importlib.util.spec_from_file_location("_conftest", _conftest_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

INITIAL_CASH = _mod.INITIAL_CASH


def _ob() -> OrderBook:
    """构造默认 OrderBook（含 InMemoryOrderEventJournal）。"""
    return OrderBook(journal=InMemoryOrderEventJournal())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_market_snapshot(
    instrument_id: int,
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
    bars: dict[int, MarketSnapshot],
    trade_date: str = "2026-01-05",
) -> ProcessInput:
    """构建 ProcessInput 用于直接调用 BacktestBrokerage。"""
    return ProcessInput(
        step_time=datetime(2026, 1, 5, 15, 0),
        trade_date=trade_date,
        bars=bars,
    )


def _make_instrument_rules(
    instrument_id: int = 1,
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
    close_prices: dict[int, float] | None = None,
    fee_model: SimpleFeeModel | None = None,
    lot_size: int = 100,
) -> PreTradeContext:
    """构建 V3 PreTradeContext — 便捷 helper。"""
    prices = close_prices or {1: 10.0}
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
            client_id=ClientOrderId(value="o-1"),
            instrument_id=1,
            order_type=OrderType.MARKET,
            direction=OrderSide.BUY,
            quantity=100,
        )
        ticket = OrderTicket(order=order, status=OrderStatus.SUBMITTED)
        with pytest.raises(AttributeError):
            ticket.status = OrderStatus.FILLED  # type: ignore[misc]

    def test_account_view_positions_readonly(self) -> None:
        """AccountView.positions 是 MappingProxyType — 不可通过 view 修改。"""
        from ditto_portfolio.accounting import Position

        pos = Position(
            instrument_id=1,
            quantity=100,
            available_quantity=100,
            average_cost=10.0,
            market_value=1000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        view = AccountView(
            positions=MappingProxyType({1: pos}),
            cash=CashBook(available=500_000.0, settled=500_000.0, frozen=0.0),
            total_value=501_000.0,
            nav=501_000.0,
            exposure=1000.0,
        )
        with pytest.raises(TypeError):
            view.positions[2] = pos  # type: ignore[index]


# ---------------------------------------------------------------------------
# Terminal state invariants
# ---------------------------------------------------------------------------


class TestTerminalState:
    """终态不可逆验证。"""

    def test_filled_ticket_cannot_cancel(self) -> None:
        """FILLED 状态的 OrderTicket 不能撤销。"""
        order = Order(
            client_id=ClientOrderId(value="o-1"),
            instrument_id=1,
            order_type=OrderType.MARKET,
            direction=OrderSide.BUY,
            quantity=100,
        )
        ticket = OrderTicket(order=order, status=OrderStatus.SUBMITTED)

        fill_evt = OrderEvent(
            client_id=ClientOrderId(value="o-1"),
            trigger=OrderTrigger.FILL,
            status=OrderStatus.FILLED,
            fill_price=10.0,
            fill_quantity=100,
            timestamp=datetime(2026, 1, 5),
        )
        filled_ticket = ticket.with_fill(quantity=100, price=10.0, event=fill_evt)

        assert filled_ticket.status == OrderStatus.FILLED

        cancel_evt = OrderEvent(
            client_id=ClientOrderId(value="o-1"),
            trigger=OrderTrigger.CANCEL,
            status=OrderStatus.CANCELED,
            timestamp=datetime(2026, 1, 5),
        )
        with pytest.raises(OrderStateError):
            filled_ticket.with_cancel(cancel_evt)

    def test_invalid_ticket_cannot_cancel(self) -> None:
        """INVALID 状态也不能撤销。"""
        order = Order(
            client_id=ClientOrderId(value="o-1"),
            instrument_id=1,
            order_type=OrderType.MARKET,
            direction=OrderSide.BUY,
            quantity=100,
        )
        ticket = OrderTicket(order=order, status=OrderStatus.SUBMITTED)

        invalid_evt = OrderEvent(
            client_id=ClientOrderId(value="o-1"),
            trigger=OrderTrigger.INVALIDATE,
            status=OrderStatus.INVALID,
            message="test",
            timestamp=datetime(2026, 1, 5),
        )
        invalid_ticket = ticket.with_invalid(invalid_evt)

        cancel_evt = OrderEvent(
            client_id=ClientOrderId(value="o-1"),
            trigger=OrderTrigger.CANCEL,
            status=OrderStatus.CANCELED,
            timestamp=datetime(2026, 1, 5),
        )
        with pytest.raises(OrderStateError):
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
        brokerage = BacktestBrokerage(account=account, order_book=_ob())

        order = Order(
            client_id=ClientOrderId(value="o-missing"),
            instrument_id=999,  # 不存在
            order_type=OrderType.MARKET,
            direction=OrderSide.BUY,
            quantity=100,
        )
        brokerage.place_order(order)

        # bars 中没有 999
        process_input = _make_process_input(
            bars={
                1: _make_market_snapshot(
                    1,
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
        ctx1.lock_instrument(1, "stop-loss")

        assert ctx1.is_locked(1)

        # 新建 context — 锁定自动清除
        ctx2 = StrategyContext()
        assert not ctx2.is_locked(1)


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
        )
        ctx = _make_pre_trade_context(
            account_view=view,
            close_prices={1: 10.0},
        )

        order1 = Order(
            client_id=ClientOrderId(value="o-1"),
            instrument_id=1,
            order_type=OrderType.MARKET,
            direction=OrderSide.BUY,
            quantity=100,
        )
        ctx1 = ctx.with_order_accepted(order1)
        assert ctx1.account_view.cash.available < ctx.account_view.cash.available

        order2 = Order(
            client_id=ClientOrderId(value="o-2"),
            instrument_id=1,
            order_type=OrderType.MARKET,
            direction=OrderSide.BUY,
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
        from ditto_portfolio.accounting import Position

        pos = Position(
            instrument_id=1,
            quantity=500,
            available_quantity=500,
            average_cost=10.0,
            market_value=5000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )

        view = AccountView(
            positions=MappingProxyType({1: pos}),
            cash=CashBook(available=500_000.0, settled=500_000.0, frozen=0.0),
            total_value=505_000.0,
            nav=505_000.0,
            exposure=5000.0,
        )

        from ditto_strategy.alpha.models import TargetPortfolio

        # Target: 0 weight → wants to exit ETF-001
        target = TargetPortfolio(
            trade_date="2026-01-05",
            strategy_id="test",
            run_id="run",
            positions={},
        )

        # 提交 pending sell — 500 股
        ob = _ob()
        pending_sell = Order(
            client_id=ClientOrderId(value="pending-sell-1"),
            instrument_id=1,
            order_type=OrderType.MARKET,
            direction=OrderSide.SELL,
            quantity=500,
        )
        ob.submit(pending_sell)

        planner = SimpleExecutionPlanner()

        plan = planner.plan(
            target=target,
            account_view=view,
            trade_date="2026-01-05",
            order_book=ob,
        )

        # effective_qty = 500 (current) + (-500) (pending delta) = 0
        # diff = 0 - 0 = 0 → no new sell order
        sell_orders = [o for o in plan.orders if o.direction == OrderSide.SELL]
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
        )

        from ditto_strategy.alpha.models import TargetPortfolio

        target = TargetPortfolio(
            trade_date="2026-01-05",
            strategy_id="test",
            run_id="run",
            positions={1: 0.3, 2: 0.3, 3: 0.4},
        )

        planner = SimpleExecutionPlanner()

        plan = planner.plan(
            target=target,
            account_view=view,
            trade_date="2026-01-05",
            locked_instruments={1},
        )

        # ETF-001 应被 blocked，不生成 buy order
        buy_orders = [o for o in plan.orders if o.instrument_id == 1]
        assert len(buy_orders) == 0

        # ETF-001 应出现在 blocked_orders 中
        blocked_iids = {b.instrument_id for b in plan.blocked_orders}
        assert 1 in blocked_iids

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
        )
        ctx = _make_pre_trade_context(
            account_view=view,
            close_prices={1: 10.0},
        )
        composite = CompositePreTradeCheck(
            checks=(LotSizeCheck(), BuyingPowerCheck()),
        )

        # 350 → resize to 400 → cost 4000 + fee > 3500 → reject
        order = Order(
            client_id=ClientOrderId(value="o-resize"),
            instrument_id=1,
            order_type=OrderType.MARKET,
            direction=OrderSide.BUY,
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
        brokerage = BacktestBrokerage(account=account, order_book=_ob())

        view_before = brokerage.get_account()
        nav_before = view_before.nav

        order = Order(
            client_id=ClientOrderId(value="o-buy"),
            instrument_id=1,
            order_type=OrderType.MARKET,
            direction=OrderSide.BUY,
            quantity=100,
        )
        brokerage.place_order(order)

        process_input = _make_process_input(
            bars={
                1: _make_market_snapshot(
                    1,
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
        from ditto_portfolio.accounting import Position

        pos = Position(
            instrument_id=1,
            quantity=200,
            available_quantity=200,
            average_cost=10.0,
            market_value=2000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        account = Account(
            positions={1: pos},
            cash=CashBook(available=500_000.0, settled=500_000.0, frozen=0.0),
        )
        brokerage = BacktestBrokerage(account=account, order_book=_ob())

        view_before = brokerage.get_account()
        nav_before = view_before.nav

        order = Order(
            client_id=ClientOrderId(value="o-sell"),
            instrument_id=1,
            order_type=OrderType.MARKET,
            direction=OrderSide.SELL,
            quantity=100,
        )
        brokerage.place_order(order)

        process_input = _make_process_input(
            bars={
                1: _make_market_snapshot(
                    1,
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
        from ditto_portfolio.accounting import Position

        pos = Position(
            instrument_id=1,
            quantity=100,
            available_quantity=100,
            average_cost=10.0,
            market_value=1000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        account = Account(
            positions={1: pos},
            cash=CashBook(available=500_000.0, settled=500_000.0, frozen=0.0),
        )
        brokerage = BacktestBrokerage(account=account, order_book=_ob())

        # Try to sell 200 — only 100 available
        order = Order(
            client_id=ClientOrderId(value="o-oversell"),
            instrument_id=1,
            order_type=OrderType.MARKET,
            direction=OrderSide.SELL,
            quantity=200,
        )
        brokerage.place_order(order)

        process_input = _make_process_input(
            bars={
                1: _make_market_snapshot(
                    1,
                    close=10.0,
                    low=9.9,
                    high=10.1,
                ),
            },
        )
        fills = brokerage.process_pending(process_input)

        # BacktestBrokerage now checks available_quantity for SELL orders
        # leaves_quantity=200 > available=100 → skip (NoFill)
        assert len(fills) == 0

    def test_pre_trade_context_prevents_oversell_in_batch(self) -> None:
        """PreTradeContext.with_order_accepted 防止批内超卖。"""
        from ditto_portfolio.accounting import Position

        pos = Position(
            instrument_id=1,
            quantity=100,
            available_quantity=100,
            average_cost=10.0,
            market_value=1000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        view = AccountView(
            positions=MappingProxyType({1: pos}),
            cash=CashBook(available=500_000.0, settled=500_000.0, frozen=0.0),
            total_value=501_000.0,
            nav=501_000.0,
            exposure=1000.0,
        )
        ctx = _make_pre_trade_context(
            account_view=view,
            close_prices={1: 10.0},
        )

        sell = Order(
            client_id=ClientOrderId(value="o-sell"),
            instrument_id=1,
            order_type=OrderType.MARKET,
            direction=OrderSide.SELL,
            quantity=100,
        )
        new_ctx = ctx.with_order_accepted(sell)

        # available_quantity should be 0 (clamped)
        assert new_ctx.account_view.positions[1].available_quantity == 0


# ---------------------------------------------------------------------------
# Stats use post-fill snapshot (R3)
# ---------------------------------------------------------------------------


class TestStatsPostFillSnapshot:
    """统计 NAV = 成交后 NAV (R3)。"""

    def test_audit_collector_uses_post_fill_view(self) -> None:
        """ExecutionAuditCollector 应在 fill 后记录 AccountView。"""
        from ditto_backtest.statistics import (
            compute_portfolio_statistics,
        )

        account = Account(
            cash=CashBook(
                available=1_000_000.0,
                settled=1_000_000.0,
                frozen=0.0,
            ),
        )
        brokerage = BacktestBrokerage(account=account, order_book=_ob())
        collector = ExecutionAuditCollector()

        # Record pre-fill view
        view_before = brokerage.get_account()
        collector.record_account_view("2026-01-05", view_before)

        # Execute a buy
        order = Order(
            client_id=ClientOrderId(value="o-buy"),
            instrument_id=1,
            order_type=OrderType.MARKET,
            direction=OrderSide.BUY,
            quantity=100,
        )
        brokerage.place_order(order)

        process_input = _make_process_input(
            bars={
                1: _make_market_snapshot(
                    1,
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

        stats = compute_portfolio_statistics(collector)
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
        instrument_id: int,
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
        from ditto_backtest.simulation import AShareFillModel

        model = BrokerageModel(fill_model=AShareFillModel())
        account = Account(
            cash=CashBook(
                available=INITIAL_CASH,
                settled=INITIAL_CASH,
                frozen=0.0,
            ),
        )
        brokerage = BacktestBrokerage(account=account, order_book=_ob(), model=model)

        # ETF-001: close=11.0 = limit_up (prev=10.0, +10%)
        order = Order(
            client_id=ClientOrderId(value="o-buy"),
            instrument_id=1,
            order_type=OrderType.MARKET,
            direction=OrderSide.BUY,
            quantity=100,
        )
        brokerage.place_order(order)

        snapshot = self._make_snapshot_with_limits(
            1,
            close=11.0,
            limit_up=11.0,
            limit_down=9.0,
            prev_close=10.0,
        )
        process_input = _make_process_input(bars={1: snapshot})
        fills = brokerage.process_pending(process_input)

        assert len(fills) == 0

    def test_limit_down_blocks_sell(self) -> None:
        """跌停卖出不成交 — close <= limit_down。"""
        from ditto_backtest.simulation import AShareFillModel
        from ditto_portfolio.accounting import Position

        pos = Position(
            instrument_id=1,
            quantity=100,
            available_quantity=100,
            average_cost=10.0,
            market_value=1000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        account = Account(
            positions={1: pos},
            cash=CashBook(
                available=500_000.0,
                settled=500_000.0,
                frozen=0.0,
            ),
        )
        model = BrokerageModel(fill_model=AShareFillModel())
        brokerage = BacktestBrokerage(account=account, order_book=_ob(), model=model)

        # ETF-001: close=9.0 = limit_down (prev=10.0, -10%)
        order = Order(
            client_id=ClientOrderId(value="o-sell"),
            instrument_id=1,
            order_type=OrderType.MARKET,
            direction=OrderSide.SELL,
            quantity=100,
        )
        brokerage.place_order(order)

        snapshot = self._make_snapshot_with_limits(
            1,
            close=9.0,
            limit_up=11.0,
            limit_down=9.0,
            prev_close=10.0,
        )
        process_input = _make_process_input(bars={1: snapshot})
        fills = brokerage.process_pending(process_input)

        assert len(fills) == 0

    def test_limit_up_allows_sell(self) -> None:
        """涨停可以卖出 — close >= limit_up + SELL → 正常成交。"""
        from ditto_backtest.simulation import AShareFillModel
        from ditto_portfolio.accounting import Position

        pos = Position(
            instrument_id=1,
            quantity=100,
            available_quantity=100,
            average_cost=10.0,
            market_value=1000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        account = Account(
            positions={1: pos},
            cash=CashBook(
                available=500_000.0,
                settled=500_000.0,
                frozen=0.0,
            ),
        )
        model = BrokerageModel(fill_model=AShareFillModel())
        brokerage = BacktestBrokerage(account=account, order_book=_ob(), model=model)

        order = Order(
            client_id=ClientOrderId(value="o-sell"),
            instrument_id=1,
            order_type=OrderType.MARKET,
            direction=OrderSide.SELL,
            quantity=100,
        )
        brokerage.place_order(order)

        snapshot = self._make_snapshot_with_limits(
            1,
            close=11.0,
            limit_up=11.0,
            limit_down=9.0,
            prev_close=10.0,
        )
        process_input = _make_process_input(bars={1: snapshot})
        fills = brokerage.process_pending(process_input)

        assert len(fills) == 1
        assert fills[0].filled_quantity == 100

    def test_limit_down_allows_buy(self) -> None:
        """跌停可以买入 — close <= limit_down + BUY → 正常成交。"""
        from ditto_backtest.simulation import AShareFillModel

        model = BrokerageModel(fill_model=AShareFillModel())
        account = Account(
            cash=CashBook(
                available=INITIAL_CASH,
                settled=INITIAL_CASH,
                frozen=0.0,
            ),
        )
        brokerage = BacktestBrokerage(account=account, order_book=_ob(), model=model)

        order = Order(
            client_id=ClientOrderId(value="o-buy"),
            instrument_id=1,
            order_type=OrderType.MARKET,
            direction=OrderSide.BUY,
            quantity=100,
        )
        brokerage.place_order(order)

        snapshot = self._make_snapshot_with_limits(
            1,
            close=9.0,
            limit_up=11.0,
            limit_down=9.0,
            prev_close=10.0,
        )
        process_input = _make_process_input(bars={1: snapshot})
        fills = brokerage.process_pending(process_input)

        assert len(fills) == 1
        assert fills[0].filled_quantity == 100

    def test_no_limit_allows_both_directions(self) -> None:
        """无涨跌停限制 — 买卖均可成交。"""
        from ditto_backtest.simulation import AShareFillModel
        from ditto_portfolio.accounting import Position

        pos = Position(
            instrument_id=1,
            quantity=100,
            available_quantity=100,
            average_cost=10.0,
            market_value=1000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        account = Account(
            positions={1: pos},
            cash=CashBook(
                available=500_000.0,
                settled=500_000.0,
                frozen=0.0,
            ),
        )
        model = BrokerageModel(fill_model=AShareFillModel())
        brokerage = BacktestBrokerage(account=account, order_book=_ob(), model=model)

        sell_order = Order(
            client_id=ClientOrderId(value="o-sell"),
            instrument_id=1,
            order_type=OrderType.MARKET,
            direction=OrderSide.SELL,
            quantity=100,
        )
        buy_order = Order(
            client_id=ClientOrderId(value="o-buy"),
            instrument_id=2,
            order_type=OrderType.MARKET,
            direction=OrderSide.BUY,
            quantity=100,
        )
        brokerage.place_order(sell_order)
        brokerage.place_order(buy_order)

        snapshot_1 = self._make_snapshot_with_limits(
            1,
            close=10.0,
            limit_up=None,
            limit_down=None,
        )
        snapshot_2 = self._make_snapshot_with_limits(
            2,
            close=20.0,
            limit_up=None,
            limit_down=None,
        )
        process_input = _make_process_input(
            bars={1: snapshot_1, 2: snapshot_2},
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
        )
        ctx = _make_pre_trade_context(
            account_view=view,
            close_prices={1: 10.0},
        )
        composite = CompositePreTradeCheck(checks=(LotSizeCheck(),))

        # 50 股 → resize to 100
        order = Order(
            client_id=ClientOrderId(value="o-resize"),
            instrument_id=1,
            order_type=OrderType.MARKET,
            direction=OrderSide.BUY,
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
        )
        ctx = _make_pre_trade_context(
            account_view=view,
            close_prices={1: 10.0},
        )
        composite = CompositePreTradeCheck(checks=(LotSizeCheck(),))

        order = Order(
            client_id=ClientOrderId(value="o-ok"),
            instrument_id=1,
            order_type=OrderType.MARKET,
            direction=OrderSide.BUY,
            quantity=300,
        )
        result = composite.check_order(order, ctx)
        assert result.decision == "accept"
        assert result.resized_quantity is None

    def test_sell_not_affected_by_lot_size(self) -> None:
        """卖出不受 lot_size 限制（零股可卖）。"""
        from ditto_portfolio.accounting import Position

        pos = Position(
            instrument_id=1,
            quantity=350,
            available_quantity=350,
            average_cost=10.0,
            market_value=3500.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        view = AccountView(
            positions=MappingProxyType({1: pos}),
            cash=CashBook(
                available=500_000.0,
                settled=500_000.0,
                frozen=0.0,
            ),
            total_value=503_500.0,
            nav=503_500.0,
            exposure=3500.0,
        )
        ctx = _make_pre_trade_context(
            account_view=view,
            close_prices={1: 10.0},
        )
        composite = CompositePreTradeCheck(checks=(LotSizeCheck(),))

        # 卖出 350（含零股）→ 不被 resize
        order = Order(
            client_id=ClientOrderId(value="o-sell-350"),
            instrument_id=1,
            order_type=OrderType.MARKET,
            direction=OrderSide.SELL,
            quantity=350,
        )
        result = composite.check_order(order, ctx)
        assert result.decision == "accept"
        assert result.resized_quantity is None


# ---------------------------------------------------------------------------
# Suspended instrument E2E — 完整引擎管道不产生成交
# ---------------------------------------------------------------------------


class TestSuspendedE2E:
    """停牌标的 E2E — 完整引擎管道不产生成交。"""

    def test_no_fill_on_suspended_e2e(
        self,
        tmp_path,
    ) -> None:
        """is_suspended=True 的标的不产生成交。"""

        import polars as pl
        from ditto_backtest.engine import (
            EngineConfig,
            EngineLoop,
            EngineMode,
            EngineOptions,
        )
        from ditto_strategy.alpha.templates.etf_rotation import (
            ETFRotationConfig,
            build_etf_rotation_pipeline,
        )

        INSTRUMENT_IDS = _mod.INSTRUMENT_IDS
        TRADE_DATES_3 = _mod.TRADE_DATES_3
        build_test_data_feed = _mod.build_test_data_feed
        generate_3day_data = _mod.generate_3day_data
        write_parquet_data = _mod.write_parquet_data

        suspended_data: dict[int, pl.DataFrame] = {}
        for iid in INSTRUMENT_IDS:
            if iid == 1:
                # 全部日期 is_suspended=True
                df = pl.DataFrame(
                    {
                        "trade_date": TRADE_DATES_3,
                        "open": [10.0, 10.2, 10.1],
                        "high": [10.1, 10.3, 10.2],
                        "low": [9.9, 10.1, 10.0],
                        "close": [10.0, 10.2, 10.1],
                        "prev_close": [10.0, 10.0, 10.2],
                        "volume": [0.0, 0.0, 0.0],
                        "amount": [0.0, 0.0, 0.0],
                        "is_suspended": [True, True, True],
                    },
                )
            else:
                # 正常数据 — 直接复用 generate_3day_data
                base = generate_3day_data()
                df = base[iid]
            suspended_data[iid] = df

        # 写 parquet + 创建 DataFeed
        data_dir = write_parquet_data(tmp_path, suspended_data)
        data_feed = build_test_data_feed(
            parquet_dir=data_dir,
            start_date="2026-01-05",
            end_date="2026-01-07",
        )

        # 组装引擎
        config = EngineConfig(
            start_date="2026-01-05",
            end_date="2026-01-07",
            initial_cash=INITIAL_CASH,
            mode=EngineMode.BACKTEST,
            strategy_id="test-suspended",
            strategy_run_id="run-suspended",
        )
        pipeline = StrategyPipeline(
            build_etf_rotation_pipeline(
                ETFRotationConfig(top_k=3, cash_target=0.0),
            )
        )
        fee_model = SimpleFeeModel()
        account = Account(
            cash=CashBook(
                available=INITIAL_CASH,
                settled=INITIAL_CASH,
                frozen=0.0,
            ),
        )
        brokerage = BacktestBrokerage(
            account=account,
            order_book=_ob(),
            model=BrokerageModel(fee_model=fee_model),
        )
        planner = SimpleExecutionPlanner()
        pre_trade_check = CompositePreTradeCheck(
            checks=(LotSizeCheck(), BuyingPowerCheck()),
        )
        collector = ExecutionAuditCollector()

        clock = SimulatedClock(initial=datetime(2026, 1, 5, tzinfo=UTC))
        synchronizer = BacktestSynchronizer(
            data_feed=data_feed,
            clock=clock,
            start_date="2026-01-05",
        )
        engine = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            synchronizer=synchronizer,
            options=EngineOptions(
                fee_model=fee_model,
                audit_collector=collector,
            ),
        )
        result = engine.run()

        # 验证: 标的 1 不产生任何成交
        suspended_fills = [f for f in result.fills if f.instrument_id == 1]
        assert len(suspended_fills) == 0, (
            f"停牌标的 1 不应产生成交, 实际 {len(suspended_fills)} 笔"
        )

        # 验证: 审计收集器中标的 1 无成交
        audit_fills = collector.get_fills()
        suspended_audit_fills = [f for f in audit_fills if f.instrument_id == 1]
        assert len(suspended_audit_fills) == 0, "审计收集器中标的 1 不应有成交记录"


# ---------------------------------------------------------------------------
# Exit order rules — 退出标的卖出订单正确加载三层规则
# ---------------------------------------------------------------------------


class TestExitOrderRules:
    """退出标的卖出订单正确加载三层规则。"""

    def test_exit_order_has_rules(self, tmp_path) -> None:
        """持有标的不在 target 中 → 退出 SELL 订单获得三层规则校验。"""

        import polars as pl
        from ditto_backtest.engine import (
            EngineConfig,
            EngineLoop,
            EngineMode,
            EngineOptions,
        )
        from ditto_execution.rules import InMemoryRuleProvider
        from ditto_portfolio.accounting import Position
        from ditto_strategy.alpha.templates.etf_rotation import (
            ETFRotationConfig,
            build_etf_rotation_pipeline,
        )

        INSTRUMENT_IDS = _mod.INSTRUMENT_IDS
        TRADE_DATES_3 = _mod.TRADE_DATES_3
        build_test_data_feed = _mod.build_test_data_feed
        generate_3day_data = _mod.generate_3day_data
        write_parquet_data = _mod.write_parquet_data

        data = generate_3day_data()
        # 确保 ETF-003 跌幅最大 → 会被 top_k=2 排除
        data[3] = pl.DataFrame(
            {
                "trade_date": TRADE_DATES_3,
                "open": [5.0, 4.8, 4.5],
                "high": [5.1, 4.9, 4.6],
                "low": [4.9, 4.7, 4.4],
                "close": [5.0, 4.8, 4.5],
                "prev_close": [5.0, 5.0, 4.8],
                "volume": [1_000_000.0] * 3,
                "amount": [5_000_000.0, 4_800_000.0, 4_500_000.0],
                "is_suspended": [False] * 3,
            },
        )

        data_dir = write_parquet_data(tmp_path, data)
        data_feed = build_test_data_feed(
            parquet_dir=data_dir,
            start_date="2026-01-05",
            end_date="2026-01-07",
        )

        # 创建已有持仓 — ETF-001 持有 1000 股
        pos_etf001 = Position(
            instrument_id=1,
            quantity=1000,
            available_quantity=1000,
            average_cost=10.0,
            market_value=10_000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        account = Account(
            positions={1: pos_etf001},
            cash=CashBook(
                available=INITIAL_CASH,
                settled=INITIAL_CASH,
                frozen=0.0,
            ),
        )

        # InMemoryRuleProvider — 为所有 3 个 ETF 提供规则
        definitions: dict[str, InstrumentDefinition] = {}
        trading_rules: dict[str, list[TradingRuleSet]] = {}
        fee_schedules: dict[str, list[FeeSchedule]] = {}
        for iid in INSTRUMENT_IDS:
            rules = _make_instrument_rules(iid)
            definitions[iid] = rules[0]
            trading_rules[iid] = [rules[1]]
            fee_schedules[iid] = [rules[2]]

        rule_provider = InMemoryRuleProvider(
            definitions=definitions,
            trading_rules=trading_rules,
            fee_schedules=fee_schedules,
        )

        # top_k=2 — 只选前 2 名, 排除表现最差的 ETF-003
        pipeline = StrategyPipeline(
            build_etf_rotation_pipeline(
                ETFRotationConfig(top_k=2, cash_target=0.0),
            )
        )
        fee_model = SimpleFeeModel()
        brokerage = BacktestBrokerage(
            account=account,
            order_book=_ob(),
            model=BrokerageModel(fee_model=fee_model),
        )
        planner = SimpleExecutionPlanner()
        pre_trade_check = CompositePreTradeCheck(
            checks=(LotSizeCheck(), BuyingPowerCheck()),
        )
        collector = ExecutionAuditCollector()

        config = EngineConfig(
            start_date="2026-01-05",
            end_date="2026-01-07",
            initial_cash=INITIAL_CASH,
            mode=EngineMode.BACKTEST,
            strategy_id="test-exit-rules",
            strategy_run_id="run-exit",
        )

        clock = SimulatedClock(initial=datetime(2026, 1, 5, tzinfo=UTC))
        synchronizer = BacktestSynchronizer(
            data_feed=data_feed,
            clock=clock,
            start_date="2026-01-05",
        )
        engine = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            synchronizer=synchronizer,
            options=EngineOptions(
                fee_model=fee_model,
                rule_provider=rule_provider,
                audit_collector=collector,
            ),
        )
        result = engine.run()

        # 验证: pre_trade_log 中包含 ETF-001 的决策记录
        # ETF-001 已持有且权重已分配 → PreTrade 会有 buy/resize 决策
        # ETF-003 不在 top_k 中 → 如果 Day 1 被买入则 Day 2 会被卖出
        pre_trade_log = collector.get_pre_trade_log()
        etf001_decisions = [d for d in pre_trade_log if d.instrument_id == 1]
        assert len(etf001_decisions) > 0, (
            "标的 1 应有 PreTrade 决策记录 — 证明三层规则被正确加载"
        )

        # 验证: manifest 包含 rule_refs
        assert result.manifest is not None
        assert len(result.manifest.rule_refs) > 0, (
            "manifest 应包含 rule_refs — 证明 RuleRefCollector 工作正常"
        )


# ---------------------------------------------------------------------------
# RuleRefCollector — 保留跨日期的所有规则版本
# ---------------------------------------------------------------------------


class TestRuleRefsPreserved:
    """RuleRefCollector 保留跨日期的所有规则版本。"""

    def test_rule_refs_all_versions_preserved(self, tmp_path) -> None:
        """跨 3 日运行 — 不同 as_of_date 的规则版本都被保留。"""

        from ditto_backtest.engine import (
            EngineConfig,
            EngineLoop,
            EngineMode,
            EngineOptions,
        )
        from ditto_execution.rules import InMemoryRuleProvider
        from ditto_strategy.alpha.templates.etf_rotation import (
            ETFRotationConfig,
            build_etf_rotation_pipeline,
        )

        INSTRUMENT_IDS = _mod.INSTRUMENT_IDS
        build_test_data_feed = _mod.build_test_data_feed
        generate_3day_data = _mod.generate_3day_data
        write_parquet_data = _mod.write_parquet_data

        data = generate_3day_data()
        data_dir = write_parquet_data(tmp_path, data)
        data_feed = build_test_data_feed(
            parquet_dir=data_dir,
            start_date="2026-01-05",
            end_date="2026-01-07",
        )

        # 创建 InMemoryRuleProvider — ETF-001 有 3 个版本（每天一个）
        definitions: dict[str, InstrumentDefinition] = {}
        trading_rules: dict[str, list[TradingRuleSet]] = {}
        fee_schedules: dict[str, list[FeeSchedule]] = {}

        for iid in INSTRUMENT_IDS:
            rules = _make_instrument_rules(iid)
            definitions[iid] = rules[0]
            trading_rules[iid] = [rules[1]]
            fee_schedules[iid] = [rules[2]]

        # ETF-001 有 3 个 trading_rule 版本 — 不同 as_of_date
        trading_rules[1] = [
            TradingRuleSet(
                instrument_id=1,
                as_of_date="2025-12-01",
                settlement_cycle=1,
                fund_settlement_cycle=1,
                price_limit_pct=0.10,
                order_types_supported=("market", "limit"),
                call_auction_sessions=("open", "close"),
            ),
            TradingRuleSet(
                instrument_id=1,
                as_of_date="2026-01-03",
                settlement_cycle=1,
                fund_settlement_cycle=0,
                price_limit_pct=0.10,
                order_types_supported=("market", "limit"),
                call_auction_sessions=("open", "close"),
            ),
            TradingRuleSet(
                instrument_id=1,
                as_of_date="2026-01-06",
                settlement_cycle=0,
                fund_settlement_cycle=0,
                price_limit_pct=0.10,
                order_types_supported=("market", "limit"),
                call_auction_sessions=("open", "close"),
            ),
        ]

        rule_provider = InMemoryRuleProvider(
            definitions=definitions,
            trading_rules=trading_rules,
            fee_schedules=fee_schedules,
        )

        pipeline = StrategyPipeline(
            build_etf_rotation_pipeline(
                ETFRotationConfig(top_k=3, cash_target=0.0),
            )
        )
        fee_model = SimpleFeeModel()
        account = Account(
            cash=CashBook(
                available=INITIAL_CASH,
                settled=INITIAL_CASH,
                frozen=0.0,
            ),
        )
        brokerage = BacktestBrokerage(
            account=account,
            order_book=_ob(),
            model=BrokerageModel(fee_model=fee_model),
        )
        planner = SimpleExecutionPlanner()
        pre_trade_check = CompositePreTradeCheck(
            checks=(LotSizeCheck(), BuyingPowerCheck()),
        )

        config = EngineConfig(
            start_date="2026-01-05",
            end_date="2026-01-07",
            initial_cash=INITIAL_CASH,
            mode=EngineMode.BACKTEST,
            strategy_id="test-rule-refs",
            strategy_run_id="run-rule-refs",
        )

        clock = SimulatedClock(initial=datetime(2026, 1, 5, tzinfo=UTC))
        synchronizer = BacktestSynchronizer(
            data_feed=data_feed,
            clock=clock,
            start_date="2026-01-05",
        )
        engine = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            synchronizer=synchronizer,
            options=EngineOptions(
                fee_model=fee_model,
                rule_provider=rule_provider,
            ),
        )
        result = engine.run()

        # 验证: manifest 包含 rule_refs
        assert result.manifest is not None
        assert len(result.manifest.rule_refs) > 0, "manifest 应包含 rule_refs"

        # 验证: ETF-001 的 rule_refs 至少包含 2 个不同版本
        # RuleRefCollector 使用 first_observed 策略 (F3):
        # Day 1 (01-05): PIT 查询 → 2026-01-03 版本（最新 <= 01-05）
        # Day 2 (01-06): PIT 查询 → 2026-01-06 版本（新 key，被记录）
        # Day 3 (01-07): PIT 查询 → 2026-01-06 版本（已存在，不重复记录）
        # 所以标的 1 应有 2 个不同的 trading_rule_as_of
        etf001_refs = [r for r in result.manifest.rule_refs if r.instrument_id == 1]
        assert len(etf001_refs) >= 2, (
            f"标的 1 应至少有 2 个不同版本的 rule_refs (F3 first_observed), "
            f"实际 {len(etf001_refs)} 个: "
            f"{[r.trading_rule_as_of for r in etf001_refs]}"
        )

        # 验证: 所有 ETF 都有 rule_refs
        ref_iids = {r.instrument_id for r in result.manifest.rule_refs}
        assert ref_iids == set(INSTRUMENT_IDS), (
            f"所有标的都应有 rule_refs, 实际: {ref_iids}"
        )
