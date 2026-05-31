"""BacktestBrokerage unit tests."""

from datetime import datetime

import pytest
from ditto_backtest.brokerage import BacktestBrokerage
from ditto_backtest.simulation import BrokerageModel
from ditto_backtest.simulation.settlement import (
    AShareSettlementModel,
    SimpleSettlementModel,
)
from ditto_backtest.simulation.slippage import FixedBpsSlippage
from ditto_execution.brokerage import ProcessInput
from ditto_execution.orders.book import OrderBook
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.journal import InMemoryOrderEventJournal
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.trigger import OrderTrigger
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import (
    FeeSchedule,
    InstrumentDefinition,
    MarketSnapshot,
    TradingRuleSet,
)
from ditto_portfolio.accounting import (
    Account,
    CashBook,
    Position,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _account(initial_cash: float = 1_000_000.0) -> Account:
    return Account(
        cash=CashBook(available=initial_cash, settled=initial_cash, frozen=0.0),
    )


def _order_book() -> OrderBook:
    return OrderBook(journal=InMemoryOrderEventJournal())


def _order(
    order_id: str = "ORD-001",
    instrument_id: int = 1,
    order_type: OrderType = OrderType.MARKET,
    direction: OrderSide = OrderSide.BUY,
    quantity: int = 1000,
    price: float | None = None,
) -> Order:
    return Order(
        client_id=ClientOrderId(value=order_id),
        instrument_id=instrument_id,
        order_type=order_type,
        direction=direction,
        quantity=quantity,
        price=price,
    )


def _market_snapshot(
    instrument_id: int = 1,
    close: float = 10.5,
    low: float = 10.0,
    high: float = 11.0,
) -> MarketSnapshot:
    return MarketSnapshot(
        trade_date="2026-01-01",
        instrument_id=instrument_id,
        open=close,
        high=high,
        low=low,
        close=close,
        prev_close=close,
        volume=1_000_000.0,
        amount=10_000_000.0,
    )


def _process_input(
    step_time: datetime | None = None,
    bars: dict[int, MarketSnapshot] | None = None,
) -> ProcessInput:
    return ProcessInput(
        step_time=step_time or datetime(2026, 3, 1, 15, 0),
        trade_date="2026-01-01",
        bars=bars or {1: _market_snapshot()},
    )


@pytest.fixture
def brokerage() -> BacktestBrokerage:
    return BacktestBrokerage(
        account=_account(),
        order_book=_order_book(),
        model=BrokerageModel(
            slippage_model=FixedBpsSlippage(bps=0),
        ),
    )


# ---------------------------------------------------------------------------
# connect / get_account
# ---------------------------------------------------------------------------


class TestConnectGetAccount:
    def test_connect_is_noop(self, brokerage: BacktestBrokerage) -> None:
        brokerage.connect()  # Should not raise

    def test_get_account_view(self, brokerage: BacktestBrokerage) -> None:
        view = brokerage.get_account()
        assert view.cash.available == pytest.approx(1_000_000.0)
        assert len(view.positions) == 0

    def test_get_order_book_returns_readonly_view(
        self, brokerage: BacktestBrokerage
    ) -> None:
        from ditto_execution.orders.book import OrderBookReadOnly

        view = brokerage.get_order_book()
        assert isinstance(view, OrderBookReadOnly)

    def test_get_order_book_reflects_submitted_order(
        self, brokerage: BacktestBrokerage
    ) -> None:
        order = _order()
        brokerage.place_order(order)

        view = brokerage.get_order_book()
        pending = view.get_pending()
        assert len(pending) == 1
        assert pending[0].order.order_id == "ORD-001"


# ---------------------------------------------------------------------------
# mark-to-market
# ---------------------------------------------------------------------------


class TestMarkToMarket:
    def test_process_pending_marks_existing_position_without_fills(self) -> None:
        account = Account(
            cash=CashBook(available=1000.0, settled=1000.0, frozen=0.0),
            positions={
                1: Position(
                    instrument_id=1,
                    quantity=100,
                    available_quantity=100,
                    average_cost=10.0,
                    market_value=1000.0,
                    unrealized_pnl=0.0,
                    realized_pnl=0.0,
                    total_fees=0.0,
                ),
            },
        )
        brokerage = BacktestBrokerage(
            account=account,
            order_book=_order_book(),
            model=BrokerageModel(
                slippage_model=FixedBpsSlippage(bps=0),
            ),
        )

        fills = brokerage.process_pending(
            _process_input(bars={1: _market_snapshot(close=9.0, low=8.9, high=9.1)})
        )

        assert fills == ()
        view = brokerage.get_account()
        assert view.positions[1].market_value == pytest.approx(900.0)
        assert view.positions[1].unrealized_pnl == pytest.approx(-100.0)
        assert view.nav == pytest.approx(1900.0)


# ---------------------------------------------------------------------------
# place_order
# ---------------------------------------------------------------------------


class TestPlaceOrder:
    def test_place_market_buy(self, brokerage: BacktestBrokerage) -> None:
        order = _order()
        ticket = brokerage.place_order(order)
        assert ticket.status == OrderStatus.SUBMITTED
        assert ticket.order.order_id == "ORD-001"

    def test_place_limit_sell(self, brokerage: BacktestBrokerage) -> None:
        order = _order(
            order_type=OrderType.LIMIT,
            direction=OrderSide.SELL,
            price=11.0,
        )
        ticket = brokerage.place_order(order)
        assert ticket.status == OrderStatus.SUBMITTED

    def test_placed_order_in_pending(self, brokerage: BacktestBrokerage) -> None:
        order = _order()
        brokerage.place_order(order)
        _ = brokerage.get_account()
        pending = brokerage._order_book.get_pending()
        assert len(pending) == 1
        assert pending[0].order.order_id == "ORD-001"


# ---------------------------------------------------------------------------
# process_pending — MARKET order
# ---------------------------------------------------------------------------


class TestProcessMarketOrder:
    def test_market_buy_fills(self, brokerage: BacktestBrokerage) -> None:
        order = _order(quantity=1000)
        brokerage.place_order(order)
        sd = _process_input()
        fills = brokerage.process_pending(sd)
        assert len(fills) == 1
        fill = fills[0]
        assert fill.order_id == "ORD-001"
        assert fill.fill_price == pytest.approx(10.5)
        assert fill.filled_quantity == 1000

    def test_market_buy_updates_account(self, brokerage: BacktestBrokerage) -> None:
        order = _order(quantity=1000)
        brokerage.place_order(order)
        sd = _process_input()
        brokerage.process_pending(sd)

        view = brokerage.get_account()
        # Position created
        assert 1 in view.positions
        pos = view.positions[1]
        assert pos.quantity == 1000
        assert pos.average_cost == pytest.approx(10.5)

        # Cash debited: 10.5 * 1000 + fee
        expected_fee = max(5.0, abs(10.5 * 1000) * 0.0003)
        expected_cash = 1_000_000.0 - 10.5 * 1000 - expected_fee
        assert view.cash.available == pytest.approx(expected_cash, rel=1e-9)

    def test_event_time_from_slice(self, brokerage: BacktestBrokerage) -> None:
        order = _order()
        brokerage.place_order(order)
        step_time = datetime(2026, 6, 15, 10, 30)
        sd = _process_input(step_time=step_time)
        fills = brokerage.process_pending(sd)
        assert fills[0].event_time == step_time


# ---------------------------------------------------------------------------
# process_pending — MARKET order with slippage
# ---------------------------------------------------------------------------


class TestProcessMarketWithSlippage:
    def test_buy_slippage_increases_price(self) -> None:
        brk = BacktestBrokerage(
            account=_account(),
            order_book=_order_book(),
            model=BrokerageModel(
                slippage_model=FixedBpsSlippage(bps=2),
            ),
        )
        order = _order(quantity=1000)
        brk.place_order(order)
        sd = _process_input()
        fills = brk.process_pending(sd)
        # close=10.5, slippage=10.5*2/10000=0.0021
        assert fills[0].fill_price == pytest.approx(10.5021)
        assert fills[0].slippage == pytest.approx(0.0021)

    def test_sell_slippage_decreases_price(self) -> None:
        # 先建仓
        brk = BacktestBrokerage(
            account=_account(),
            order_book=_order_book(),
            model=BrokerageModel(
                slippage_model=FixedBpsSlippage(bps=2),
            ),
        )
        buy_order = _order(order_id="BUY-1", quantity=1000)
        brk.place_order(buy_order)
        brk.process_pending(_process_input())

        # 再卖出
        sell_order = _order(
            order_id="SELL-1",
            direction=OrderSide.SELL,
            quantity=1000,
        )
        brk.place_order(sell_order)
        fills = brk.process_pending(_process_input())
        # close=10.5, slippage=-0.0021
        assert fills[0].fill_price == pytest.approx(10.5 - 0.0021)


# ---------------------------------------------------------------------------
# process_pending — LIMIT order
# ---------------------------------------------------------------------------


class TestProcessLimitOrder:
    def test_limit_in_range_fills(self, brokerage: BacktestBrokerage) -> None:
        order = _order(order_type=OrderType.LIMIT, price=10.3)
        brokerage.place_order(order)
        sd = _process_input()
        fills = brokerage.process_pending(sd)
        assert len(fills) == 1
        assert fills[0].fill_price == pytest.approx(10.3)

    def test_limit_below_range_invalid(self, brokerage: BacktestBrokerage) -> None:
        order = _order(order_type=OrderType.LIMIT, price=9.0)
        brokerage.place_order(order)
        sd = _process_input()
        fills = brokerage.process_pending(sd)
        assert len(fills) == 0

        # Ticket should be INVALID
        _ = brokerage.get_account()
        ticket = brokerage._order_book.get(ClientOrderId(value="ORD-001"))
        assert ticket is not None
        assert ticket.status == OrderStatus.INVALID

    def test_limit_above_range_invalid(self, brokerage: BacktestBrokerage) -> None:
        order = _order(order_type=OrderType.LIMIT, price=12.0)
        brokerage.place_order(order)
        sd = _process_input()
        brokerage.process_pending(sd)

        _ = brokerage.get_account()
        ticket = brokerage._order_book.get(ClientOrderId(value="ORD-001"))
        assert ticket is not None
        assert ticket.status == OrderStatus.INVALID

    def test_invalidate_appends_journal(self, brokerage: BacktestBrokerage) -> None:
        """invalidate 事件应写入 journal（与 submit/fill/cancel 一致）。"""
        cid = ClientOrderId(value="ORD-001")
        order = _order(order_type=OrderType.LIMIT, price=9.0)
        brokerage.place_order(order)
        sd = _process_input()
        brokerage.process_pending(sd)

        journal = brokerage._order_book._journal
        events = journal.events_for(cid)
        assert len(events) == 2  # SUBMIT + INVALIDATE
        assert events[1].trigger == OrderTrigger.INVALIDATE


# ---------------------------------------------------------------------------
# process_pending — NoFill(can_retry=True)
# ---------------------------------------------------------------------------


class TestNoFillRetryable:
    def test_can_retry_stays_submitted(self, brokerage: BacktestBrokerage) -> None:
        """NoFill with can_retry=True should keep ticket SUBMITTED.

        V1 SimpleFillModel 不产生 can_retry=True 的 NoFill,
        但 Brokerage 逻辑正确处理该情况。
        """
        # Use settlement model to simulate a scenario where order stays pending
        # Since our current models don't produce can_retry=True naturally,
        # we test indirectly: process with no bars for this instrument
        order = _order(instrument_id=999)
        brokerage.place_order(order)
        sd = _process_input(bars={})  # No bars → order stays pending
        fills = brokerage.process_pending(sd)
        assert len(fills) == 0

        _ = brokerage.get_account()
        ticket = brokerage._order_book.get(ClientOrderId(value="ORD-001"))
        assert ticket is not None
        assert ticket.status == OrderStatus.SUBMITTED


# ---------------------------------------------------------------------------
# cancel_order
# ---------------------------------------------------------------------------


class TestCancelOrder:
    def test_cancel_pending_order(self, brokerage: BacktestBrokerage) -> None:
        order = _order()
        brokerage.place_order(order)
        assert brokerage.cancel_order("ORD-001") is True

        _ = brokerage.get_account()
        ticket = brokerage._order_book.get(ClientOrderId(value="ORD-001"))
        assert ticket is not None
        assert ticket.status == OrderStatus.CANCELED

    def test_cancel_nonexistent_order(self, brokerage: BacktestBrokerage) -> None:
        assert brokerage.cancel_order("NONEXISTENT") is False

    def test_cancel_filled_order_is_noop(
        self,
        brokerage: BacktestBrokerage,
    ) -> None:
        """Filled 订单是终态, cancel 是 no-op（不抛异常）。"""
        order = _order(quantity=1000)
        brokerage.place_order(order)
        brokerage.process_pending(_process_input())
        # Ticket is now FILLED — cancel returns True (no error raised)
        assert brokerage.cancel_order("ORD-001") is True


# ---------------------------------------------------------------------------
# Terminal state irreversible
# ---------------------------------------------------------------------------


class TestTerminalState:
    def test_filled_is_terminal(self, brokerage: BacktestBrokerage) -> None:
        order = _order(quantity=1000)
        brokerage.place_order(order)
        brokerage.process_pending(_process_input())

        _ = brokerage.get_account()
        ticket = brokerage._order_book.get(ClientOrderId(value="ORD-001"))
        assert ticket is not None
        assert ticket.status == OrderStatus.FILLED
        assert ticket.status.is_terminal

    def test_invalid_cancel_is_noop(self, brokerage: BacktestBrokerage) -> None:
        order = _order(order_type=OrderType.LIMIT, price=9.0)
        brokerage.place_order(order)
        brokerage.process_pending(_process_input())

        # INVALID is terminal — cancel returns True (no error raised)
        assert brokerage.cancel_order("ORD-001") is True


# ---------------------------------------------------------------------------
# Cash conservation
# ---------------------------------------------------------------------------


class TestCashConservation:
    def test_buy_debits_cash(self, brokerage: BacktestBrokerage) -> None:
        initial = brokerage.get_account().cash.available
        order = _order(quantity=1000)
        brokerage.place_order(order)
        brokerage.process_pending(_process_input())

        final = brokerage.get_account().cash.available
        fill_amount = 10.5 * 1000
        fee = max(5.0, fill_amount * 0.0003)
        assert initial - final == pytest.approx(fill_amount + fee)

    def test_sell_credits_cash(self, brokerage: BacktestBrokerage) -> None:
        # Build a position first
        buy = _order(order_id="BUY-1", quantity=1000)
        brokerage.place_order(buy)
        brokerage.process_pending(_process_input())
        cash_after_buy = brokerage.get_account().cash.available

        # Now sell
        sell = _order(
            order_id="SELL-1",
            direction=OrderSide.SELL,
            quantity=1000,
        )
        brokerage.place_order(sell)
        brokerage.process_pending(_process_input())
        cash_after_sell = brokerage.get_account().cash.available

        fill_amount = 10.5 * 1000
        fee = max(5.0, fill_amount * 0.0003)
        assert cash_after_sell - cash_after_buy == pytest.approx(fill_amount - fee)

    def test_position_cleared_on_sell(self, brokerage: BacktestBrokerage) -> None:
        buy = _order(order_id="BUY-1", quantity=1000)
        brokerage.place_order(buy)
        brokerage.process_pending(_process_input())

        sell = _order(
            order_id="SELL-1",
            direction=OrderSide.SELL,
            quantity=1000,
        )
        brokerage.place_order(sell)
        brokerage.process_pending(_process_input())

        view = brokerage.get_account()
        assert 1 not in view.positions


# ---------------------------------------------------------------------------
# Multiple fills / cumulative
# ---------------------------------------------------------------------------


class TestMultipleFills:
    def test_sequential_fills_increment_counter(
        self,
        brokerage: BacktestBrokerage,
    ) -> None:
        order1 = _order(order_id="ORD-1")
        order2 = _order(order_id="ORD-2", instrument_id=2)
        brokerage.place_order(order1)
        brokerage.place_order(order2)
        sd = _process_input(
            bars={
                1: _market_snapshot(
                    instrument_id=1,
                    close=10.5,
                    low=10.0,
                    high=11.0,
                ),
                2: _market_snapshot(
                    instrument_id=2,
                    close=20.0,
                    low=19.0,
                    high=21.0,
                ),
            }
        )
        fills = brokerage.process_pending(sd)
        assert len(fills) == 2
        assert fills[0].fill_id == "fill-1"
        assert fills[1].fill_id == "fill-2"

    def test_fill_cumulative_and_leaves(self, brokerage: BacktestBrokerage) -> None:
        order = _order(quantity=1000)
        brokerage.place_order(order)
        sd = _process_input()
        fills = brokerage.process_pending(sd)
        assert fills[0].cumulative_quantity == 1000
        assert fills[0].leaves_quantity == 0


# ---------------------------------------------------------------------------
# Settlement model integration
# ---------------------------------------------------------------------------


class TestSettlementIntegration:
    def test_default_settlement_always_tradable(self) -> None:

        model = SimpleSettlementModel()
        rule = TradingRuleSet(
            instrument_id=1,
            as_of_date="2026-03-01",
            settlement_cycle=0,
            fund_settlement_cycle=0,
            price_limit_pct=None,
            order_types_supported=("market", "limit"),
            call_auction_sessions=(),
        )
        assert (
            model.is_tradable(
                1,
                "2026-03-01",
                OrderSide.BUY,
                None,
                rule,
            )
            is True
        )
        assert (
            model.is_tradable(
                1,
                "2020-01-01",
                OrderSide.SELL,
                None,
                rule,
            )
            is True
        )


# ---------------------------------------------------------------------------
# T+1 冻结逻辑
# ---------------------------------------------------------------------------

# 交易日历: 2026-03-02 ~ 2026-03-06 (工作日)
_TRADING_CALENDAR = (
    "2026-03-02",
    "2026-03-03",
    "2026-03-04",
    "2026-03-05",
    "2026-03-06",
)


def _t1_rules_getter(
    instrument_id: int,
    trade_date: str,
) -> tuple[InstrumentDefinition, TradingRuleSet, FeeSchedule]:
    """返回 T+1 规则 (settlement_cycle=1)。"""
    return (
        InstrumentDefinition(
            instrument_id=instrument_id,
            asset_class="etf",
            exchange="XSHE",
            currency="CNY",
            tick_size=0.001,
            lot_size=100,
            multiplier=1.0,
            board_segment="main",
            lifecycle_state="normal",
        ),
        TradingRuleSet(
            instrument_id=instrument_id,
            as_of_date=trade_date,
            settlement_cycle=1,
            fund_settlement_cycle=1,
            price_limit_pct=None,
            order_types_supported=("market", "limit"),
            call_auction_sessions=(),
        ),
        FeeSchedule(
            instrument_id=instrument_id,
            as_of_date=trade_date,
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.0,
            transfer_fee_rate=0.0,
        ),
    )


def _t1_process_input(
    trade_date: str,
    bars: dict[int, MarketSnapshot] | None = None,
) -> ProcessInput:
    """创建 T+1 场景的 ProcessInput。"""
    dt_parts = trade_date.split("-")
    step_time = datetime(int(dt_parts[0]), int(dt_parts[1]), int(dt_parts[2]), 15, 0)
    default_bars = {
        1: MarketSnapshot(
            trade_date=trade_date,
            instrument_id=1,
            open=10.5,
            high=11.0,
            low=10.0,
            close=10.5,
            prev_close=10.5,
            volume=1_000_000.0,
            amount=10_000_000.0,
        ),
    }
    return ProcessInput(
        step_time=step_time,
        trade_date=trade_date,
        bars=bars or default_bars,
    )


@pytest.fixture
def t1_brokerage() -> BacktestBrokerage:
    """T+1 冻结规则的回测经纪商。"""
    return BacktestBrokerage(
        account=_account(),
        order_book=_order_book(),
        model=BrokerageModel(
            slippage_model=FixedBpsSlippage(bps=0),
            settlement_model=AShareSettlementModel(
                trading_calendar=_TRADING_CALENDAR,
            ),
        ),
        rules_getter=_t1_rules_getter,
    )


class TestT1FreezeBasic:
    """T+1 冻结基础行为 — 买入当日不可卖。"""

    def test_buy_on_t_day_quantity_increases(
        self, t1_brokerage: BacktestBrokerage
    ) -> None:
        """T 日买入后, quantity 增加但 available_quantity 不变 (新仓)。"""
        order = _order(quantity=1000)
        t1_brokerage.place_order(order)
        t1_brokerage.process_pending(_t1_process_input("2026-03-02"))

        view = t1_brokerage.get_account()
        pos = view.positions[1]
        assert pos.quantity == 1000
        # T+1: 当日买入的份额不可卖
        assert pos.available_quantity == 0

    def test_buy_t0_no_freeze_with_simple_settlement(
        self,
        brokerage: BacktestBrokerage,
    ) -> None:
        """T+0 (SimpleSettlementModel) 买入后 available_quantity 立即可用。"""
        order = _order(quantity=1000)
        brokerage.place_order(order)
        brokerage.process_pending(_process_input())

        view = brokerage.get_account()
        pos = view.positions[1]
        assert pos.quantity == 1000
        assert pos.available_quantity == 1000


class TestT1FreezeThaw:
    """T+1 冻结 — T+1 日解冻后可卖。"""

    def test_thaw_on_next_trading_day(self, t1_brokerage: BacktestBrokerage) -> None:
        """T 日买入 → T+1 日 (2026-03-03) 解冻, available_quantity 恢复。"""
        # T 日买入
        order = _order(quantity=1000)
        t1_brokerage.place_order(order)
        t1_brokerage.process_pending(_t1_process_input("2026-03-02"))

        # T 日检查
        view = t1_brokerage.get_account()
        assert view.positions[1].available_quantity == 0

        # T+1 日 (下一个交易日)
        t1_brokerage.process_pending(_t1_process_input("2026-03-03"))

        # 解冻后 available_quantity 恢复
        view = t1_brokerage.get_account()
        assert view.positions[1].available_quantity == 1000

    def test_sell_after_thaw(self, t1_brokerage: BacktestBrokerage) -> None:
        """T+1 日解冻后可以卖出全部份额。"""
        # T 日买入
        buy = _order(order_id="BUY-1", quantity=1000)
        t1_brokerage.place_order(buy)
        t1_brokerage.process_pending(_t1_process_input("2026-03-02"))

        # T+1 日解冻 + 卖出
        sell = _order(order_id="SELL-1", direction=OrderSide.SELL, quantity=1000)
        t1_brokerage.place_order(sell)
        fills = t1_brokerage.process_pending(_t1_process_input("2026-03-03"))
        assert len(fills) == 1

        view = t1_brokerage.get_account()
        assert 1 not in view.positions

    def test_cannot_sell_on_t_day(self, t1_brokerage: BacktestBrokerage) -> None:
        """T 日买入的份额, 当日卖出因 available_quantity=0 应被阻止。

        SettlementModel.is_tradable 对 SELL 返回 True (冻结逻辑在 Brokerage),
        所以订单会提交并进入 process_pending, 但因 available_quantity=0,
        在 _update_position SELL 路径中 available_quantity 会变为负数。
        Brokerage 应在 apply_fill 之前检查 available_quantity。
        """
        # T 日买入
        buy = _order(order_id="BUY-1", quantity=1000)
        t1_brokerage.place_order(buy)
        t1_brokerage.process_pending(_t1_process_input("2026-03-02"))

        # T 日尝试卖出 — 因 SimpleSettlementModel always tradable,
        # 订单不会被 settlement 拦截, 但 available_quantity=0
        sell = _order(order_id="SELL-1", direction=OrderSide.SELL, quantity=1000)
        t1_brokerage.place_order(sell)
        # settlement_model.is_tradable returns True for SELL in AShare model,
        # 所以 sell 会进入 fill 流程。但我们通过 _apply_fill 保护:
        # 如果 available_quantity < sell_qty, 应该跳过 (不成交)
        fills = t1_brokerage.process_pending(_t1_process_input("2026-03-02"))
        # sell 因 insufficient available 被阻止
        assert len(fills) == 0


class TestT1FreezePartialSell:
    """T+1 冻结 — 部分解冻 + 部分卖出。"""

    def test_partial_sell_after_partial_thaw(
        self,
        t1_brokerage: BacktestBrokerage,
    ) -> None:
        """已有仓位 500 股可用 + 新买入 500 股冻结, 当日只能卖 500。"""
        # Day 1: 买入 500 (T+0, settlement_cycle=1 → 次日可卖)
        buy1 = _order(order_id="BUY-1", quantity=500)
        t1_brokerage.place_order(buy1)
        t1_brokerage.process_pending(_t1_process_input("2026-03-02"))

        # Day 2: 解冻 500 + 买入 500 (冻结)
        buy2 = _order(order_id="BUY-2", quantity=500)
        t1_brokerage.place_order(buy2)
        t1_brokerage.process_pending(_t1_process_input("2026-03-03"))

        view = t1_brokerage.get_account()
        pos = view.positions[1]
        assert pos.quantity == 1000
        # 500 from day1 thawed, 500 from day2 frozen
        assert pos.available_quantity == 500

        # Day 2: 尝试卖出 800, 只有 500 可用
        sell = _order(order_id="SELL-1", direction=OrderSide.SELL, quantity=800)
        t1_brokerage.place_order(sell)
        fills = t1_brokerage.process_pending(_t1_process_input("2026-03-03"))
        # 不成交 (available < sell_qty)
        assert len(fills) == 0

        # Day 2: 尝试卖出 500 (刚好可用)
        sell2 = _order(order_id="SELL-2", direction=OrderSide.SELL, quantity=500)
        t1_brokerage.place_order(sell2)
        fills2 = t1_brokerage.process_pending(_t1_process_input("2026-03-03"))
        # 注意: sell 订单在 order_book 中仍然是 SUBMITTED (被跳过),
        # sell2 应该成交
        # 实际上, 由于 fill_model 是 SimpleFillModel, sell2 会成交
        # 但 sell 还在 pending 且因为 insufficient available 被跳过
        assert len(fills2) == 1


class TestT1FreezeMultiInstrument:
    """T+1 冻结 — 多标的同时冻结/解冻。"""

    def test_freeze_per_instrument(self) -> None:
        """不同标的独立冻结。"""
        brk = BacktestBrokerage(
            account=_account(),
            order_book=_order_book(),
            model=BrokerageModel(
                slippage_model=FixedBpsSlippage(bps=0),
                settlement_model=AShareSettlementModel(
                    trading_calendar=_TRADING_CALENDAR,
                ),
            ),
            rules_getter=_t1_rules_getter,
        )

        bars_day1 = {
            1: MarketSnapshot(
                trade_date="2026-03-02",
                instrument_id=1,
                open=10.5,
                high=11.0,
                low=10.0,
                close=10.5,
                prev_close=10.5,
                volume=1_000_000.0,
                amount=10_000_000.0,
            ),
            2: MarketSnapshot(
                trade_date="2026-03-02",
                instrument_id=2,
                open=20.0,
                high=21.0,
                low=19.0,
                close=20.0,
                prev_close=20.0,
                volume=1_000_000.0,
                amount=20_000_000.0,
            ),
        }

        buy1 = _order(order_id="BUY-1", instrument_id=1, quantity=500)
        buy2 = _order(order_id="BUY-2", instrument_id=2, quantity=300)
        brk.place_order(buy1)
        brk.place_order(buy2)
        brk.process_pending(_t1_process_input("2026-03-02", bars=bars_day1))

        view = brk.get_account()
        assert view.positions[1].available_quantity == 0
        assert view.positions[2].available_quantity == 0

        # T+1 解冻
        brk.process_pending(_t1_process_input("2026-03-03", bars=bars_day1))

        view = brk.get_account()
        assert view.positions[1].available_quantity == 500
        assert view.positions[2].available_quantity == 300


class TestT1FreezeSettlementCycle0:
    """settlement_cycle=0 的标的 — T+0 交收, 无冻结。"""

    def _t0_rules_getter(
        self,
        instrument_id: int,
        trade_date: str,
    ) -> tuple[InstrumentDefinition, TradingRuleSet, FeeSchedule]:
        """返回 T+0 规则 (settlement_cycle=0)。"""
        return (
            InstrumentDefinition(
                instrument_id=instrument_id,
                asset_class="etf",
                exchange="XSHE",
                currency="CNY",
                tick_size=0.001,
                lot_size=100,
                multiplier=1.0,
                board_segment="main",
                lifecycle_state="normal",
            ),
            TradingRuleSet(
                instrument_id=instrument_id,
                as_of_date=trade_date,
                settlement_cycle=0,
                fund_settlement_cycle=0,
                price_limit_pct=None,
                order_types_supported=("market", "limit"),
                call_auction_sessions=(),
            ),
            FeeSchedule(
                instrument_id=instrument_id,
                as_of_date=trade_date,
                commission_rate=0.0003,
                min_commission=5.0,
                stamp_duty_rate=0.0,
                transfer_fee_rate=0.0,
            ),
        )

    def test_settlement_cycle_0_no_freeze(self) -> None:
        """settlement_cycle=0 标的, 买入即解冻。"""
        brk = BacktestBrokerage(
            account=_account(),
            order_book=_order_book(),
            model=BrokerageModel(
                slippage_model=FixedBpsSlippage(bps=0),
                settlement_model=AShareSettlementModel(
                    trading_calendar=_TRADING_CALENDAR,
                ),
            ),
            rules_getter=self._t0_rules_getter,
        )

        buy = _order(quantity=1000)
        brk.place_order(buy)
        brk.process_pending(_t1_process_input("2026-03-02"))

        view = brk.get_account()
        pos = view.positions[1]
        assert pos.quantity == 1000
        assert pos.available_quantity == 1000

    def test_sell_same_day_cycle_0(self) -> None:
        """settlement_cycle=0 标的, 买入当日即可卖出。"""
        brk = BacktestBrokerage(
            account=_account(),
            order_book=_order_book(),
            model=BrokerageModel(
                slippage_model=FixedBpsSlippage(bps=0),
                settlement_model=AShareSettlementModel(
                    trading_calendar=_TRADING_CALENDAR,
                ),
            ),
            rules_getter=self._t0_rules_getter,
        )

        buy = _order(order_id="BUY-1", quantity=1000)
        brk.place_order(buy)
        brk.process_pending(_t1_process_input("2026-03-02"))

        sell = _order(order_id="SELL-1", direction=OrderSide.SELL, quantity=1000)
        brk.place_order(sell)
        fills = brk.process_pending(_t1_process_input("2026-03-02"))
        assert len(fills) == 1

        view = brk.get_account()
        assert 1 not in view.positions


# ---------------------------------------------------------------------------
# _apply_fill 状态一致性 — event.status == ticket.status
# ---------------------------------------------------------------------------


class TestApplyFillStatusConsistency:
    """验证 _apply_fill 中 OrderEvent.status 与 FSM 计算的 ticket.status 一致。"""

    def test_full_fill_event_status_matches_ticket_status(
        self,
        brokerage: BacktestBrokerage,
    ) -> None:
        """全量成交: event.status 应等于 updated_ticket.status (FILLED)。"""
        order = _order(quantity=1000)
        brokerage.place_order(order)
        brokerage.process_pending(_process_input())

        ticket = brokerage._order_book.get(ClientOrderId(value="ORD-001"))
        assert ticket is not None
        assert ticket.status == OrderStatus.FILLED

        # 最后一个 order_event 的 status 应与 ticket.status 一致
        last_event = ticket.order_events[-1]
        assert last_event.status == OrderStatus.FILLED
        assert last_event.status == ticket.status

    def test_fill_event_status_derived_from_fsm(
        self,
        brokerage: BacktestBrokerage,
    ) -> None:
        """验证 event.status 由 FSM transition 计算而非手动判断。"""
        order = _order(quantity=1000)
        brokerage.place_order(order)
        brokerage.process_pending(_process_input())

        ticket = brokerage._order_book.get(ClientOrderId(value="ORD-001"))
        assert ticket is not None

        # ticket.status 由 FSM transition() 决定，event.status 必须一致
        last_event = ticket.order_events[-1]
        assert last_event.status == ticket.status

    def test_partial_fill_event_status_consistency(self) -> None:
        """部分成交场景（如果 V2 引入）event.status 也必须与 ticket.status 一致。

        当前 V1 fill model 是 all-or-nothing，但通过直接调用 _apply_fill
        验证部分成交时 event 与 ticket 状态一致性。
        """

        from ditto_portfolio.accounting import FillEvent

        brk = BacktestBrokerage(
            account=_account(),
            order_book=_order_book(),
        )
        order = _order(quantity=2000)
        ticket = brk.place_order(order)

        # 构造部分成交的 FillEvent (filled_quantity=1000, leaves_quantity=1000)
        partial_fill = FillEvent(
            fill_id="fill-partial",
            order_id=order.order_id,
            instrument_id=order.instrument_id,
            direction=order.direction,
            filled_quantity=1000,
            fill_price=10.5,
            fee=3.15,
            slippage=0.0,
            event_time=datetime(2026, 1, 1, 15, 0),
            cumulative_quantity=1000,
            leaves_quantity=1000,
        )
        brk._apply_fill(ticket, partial_fill, settle_date="2026-01-01")

        updated = brk._order_book.get(ClientOrderId(value="ORD-001"))
        assert updated is not None
        assert updated.status == OrderStatus.PARTIALLY_FILLED

        # event.status 必须与 ticket.status 一致
        last_event = updated.order_events[-1]
        assert last_event.status == OrderStatus.PARTIALLY_FILLED
        assert last_event.status == updated.status

    def test_full_fill_after_partial_event_status_consistency(self) -> None:
        """部分成交后再全量成交: 两次 event.status 分别与各自 ticket.status 一致。"""
        from ditto_portfolio.accounting import FillEvent

        brk = BacktestBrokerage(
            account=_account(),
            order_book=_order_book(),
        )
        order = _order(quantity=2000)
        ticket = brk.place_order(order)

        # 第一次部分成交
        partial_fill = FillEvent(
            fill_id="fill-1",
            order_id=order.order_id,
            instrument_id=order.instrument_id,
            direction=order.direction,
            filled_quantity=1000,
            fill_price=10.5,
            fee=3.15,
            slippage=0.0,
            event_time=datetime(2026, 1, 1, 15, 0),
            cumulative_quantity=1000,
            leaves_quantity=1000,
        )
        brk._apply_fill(ticket, partial_fill, settle_date="2026-01-01")

        ticket_after_partial = brk._order_book.get(ClientOrderId(value="ORD-001"))
        assert ticket_after_partial is not None
        assert ticket_after_partial.status == OrderStatus.PARTIALLY_FILLED
        last_event = ticket_after_partial.order_events[-1]
        assert last_event.status == OrderStatus.PARTIALLY_FILLED

        # 第二次全部成交剩余
        full_fill = FillEvent(
            fill_id="fill-2",
            order_id=order.order_id,
            instrument_id=order.instrument_id,
            direction=order.direction,
            filled_quantity=1000,
            fill_price=10.6,
            fee=3.18,
            slippage=0.0,
            event_time=datetime(2026, 1, 1, 15, 1),
            cumulative_quantity=2000,
            leaves_quantity=0,
        )
        brk._apply_fill(ticket_after_partial, full_fill, settle_date="2026-01-01")

        final_ticket = brk._order_book.get(ClientOrderId(value="ORD-001"))
        assert final_ticket is not None
        assert final_ticket.status == OrderStatus.FILLED
        assert final_ticket.order_events[-1].status == OrderStatus.FILLED
        assert final_ticket.order_events[-1].status == final_ticket.status


# ---------------------------------------------------------------------------
# T+1 冻结逻辑
# ---------------------------------------------------------------------------


class TestT1FreezeSellDeduction:
    """T+1 冻结 — 卖出时从 available_quantity 扣除。"""

    def test_sell_reduces_available_quantity(
        self, t1_brokerage: BacktestBrokerage
    ) -> None:
        """卖出后 available_quantity 减少相应数量。"""
        # 买入 → 解冻
        buy = _order(order_id="BUY-1", quantity=1000)
        t1_brokerage.place_order(buy)
        t1_brokerage.process_pending(_t1_process_input("2026-03-02"))
        t1_brokerage.process_pending(_t1_process_input("2026-03-03"))

        # 卖出 400
        sell = _order(order_id="SELL-1", direction=OrderSide.SELL, quantity=400)
        t1_brokerage.place_order(sell)
        t1_brokerage.process_pending(_t1_process_input("2026-03-03"))

        view = t1_brokerage.get_account()
        pos = view.positions[1]
        assert pos.quantity == 600
        assert pos.available_quantity == 600
