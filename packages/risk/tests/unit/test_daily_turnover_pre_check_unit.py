"""DailyTurnoverPreCheck 单元测试。"""

from __future__ import annotations

from types import MappingProxyType
from unittest.mock import MagicMock

from ditto_execution.reality.market import MarketSnapshot
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_portfolio.accounting.account import AccountView
from ditto_portfolio.accounting.buying_power import BuyingPowerModel
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.order_book import Order, OrderTicket
from ditto_risk.pre_trade import DailyTurnoverPreCheck, Decision, PreTradeContext

IID_A = InstrumentId(1)
IID_B = InstrumentId(2)


def _snapshot(iid: InstrumentId, close: float = 10.0) -> MarketSnapshot:
    return MarketSnapshot(
        trade_date="2026-01-02",
        instrument_id=iid,
        open=close,
        high=close,
        low=close,
        close=close,
        prev_close=close,
        volume=1_000_000.0,
        amount=10_000_000.0,
    )


def _order(direction: OrderSide = OrderSide.BUY, quantity: int = 100) -> Order:
    return Order(
        order_id="o1",
        instrument_id=IID_A,
        order_type=OrderType.MARKET,
        direction=direction,
        quantity=quantity,
    )


def _ticket(
    iid: InstrumentId = IID_A,
    direction: OrderSide = OrderSide.BUY,
    quantity: int = 100,
    leaves: int = 100,
) -> OrderTicket:
    return OrderTicket(
        order=Order(
            order_id="t1",
            instrument_id=iid,
            order_type=OrderType.MARKET,
            direction=direction,
            quantity=quantity,
        ),
        filled_quantity=quantity - leaves,
    )


def _ctx(
    nav: float = 100_000.0,
    pending: tuple[OrderTicket, ...] = (),
    has_price: bool = True,
) -> PreTradeContext:
    snapshots: dict[InstrumentId, MarketSnapshot] = {}
    if has_price:
        snapshots[IID_A] = _snapshot(IID_A, close=10.0)
        snapshots[IID_B] = _snapshot(IID_B, close=10.0)
    return PreTradeContext(
        account_view=AccountView(
            positions=MappingProxyType({}),
            cash=CashBook(available=50_000.0, settled=50_000.0, frozen=0.0),
            total_value=100_000.0,
            nav=nav,
            exposure=0.0,
            pending_buy_value=0.0,
            order_book=MagicMock(),
        ),
        rules={},
        market_snapshots=snapshots,
        buying_power_model=MagicMock(spec=BuyingPowerModel),
        pending_tickets=pending,
    )


class TestDailyTurnoverPreCheck:
    def test_sell_accepted(self) -> None:
        """卖出始终通过。"""
        check = DailyTurnoverPreCheck(max_turnover=0.30)
        result = check.check_order(_order(OrderSide.SELL), _ctx())
        assert result.decision == Decision.ACCEPT

    def test_nav_zero_accepted(self) -> None:
        """NAV <= 0 时通过。"""
        check = DailyTurnoverPreCheck(max_turnover=0.30)
        result = check.check_order(_order(), _ctx(nav=0.0))
        assert result.decision == Decision.ACCEPT

    def test_no_price_accepted(self) -> None:
        """无价格时通过。"""
        check = DailyTurnoverPreCheck(max_turnover=0.30)
        result = check.check_order(_order(), _ctx(has_price=False))
        assert result.decision == Decision.ACCEPT

    def test_over_limit_rejected(self) -> None:
        """累计换手率超限被拒。"""
        # pending = 2500 shares * 10 = 25000, order = 100 * 10 = 1000
        # turnover = 26000 / 100000 = 26% < 30%, so need more
        pending = (_ticket(IID_A, OrderSide.BUY, quantity=300, leaves=300),)
        # pending = 300*10 = 3000, order = 100*10 = 1000
        # turnover = 4000 / 10000 = 40% > 30%
        check = DailyTurnoverPreCheck(max_turnover=0.30)
        result = check.check_order(
            _order(quantity=100),
            _ctx(nav=10_000.0, pending=pending),
        )
        assert result.decision == Decision.REJECT
        assert result.reason is not None
        assert "daily_turnover" in result.reason

    def test_within_limit_accepted(self) -> None:
        """累计换手率在限额内通过。"""
        # pending=0, order=100*10=1000, nav=100000, turnover=1%
        check = DailyTurnoverPreCheck(max_turnover=0.30)
        result = check.check_order(_order(quantity=100), _ctx(nav=100_000.0))
        assert result.decision == Decision.ACCEPT

    def test_pending_tickets_included(self) -> None:
        """已提交的 pending BUY 订单金额纳入累计。"""
        # pending BUY: 500*10=5000, order: 200*10=2000, total=7000
        # nav=20000, turnover=35% > 30%
        pending = (_ticket(IID_A, OrderSide.BUY, quantity=500, leaves=500),)
        check = DailyTurnoverPreCheck(max_turnover=0.30)
        result = check.check_order(
            _order(quantity=200),
            _ctx(nav=20_000.0, pending=pending),
        )
        assert result.decision == Decision.REJECT

    def test_pending_sell_tickets_ignored(self) -> None:
        """pending SELL 订单不影响换手率。"""
        pending = (_ticket(IID_A, OrderSide.SELL, quantity=500, leaves=500),)
        check = DailyTurnoverPreCheck(max_turnover=0.30)
        result = check.check_order(
            _order(quantity=100),
            _ctx(nav=100_000.0, pending=pending),
        )
        assert result.decision == Decision.ACCEPT
