"""BuyingPowerCheck 单元测试。"""

from __future__ import annotations

from types import MappingProxyType
from unittest.mock import MagicMock

from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import MarketSnapshot
from ditto_portfolio.accounting.account import AccountView
from ditto_portfolio.accounting.buying_power import BuyingPowerModel
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.order_book import Order
from ditto_risk.pre_trade import BuyingPowerCheck, Decision, PreTradeContext

IID = InstrumentId(1)

ORDER = Order(
    order_id="o1",
    instrument_id=IID,
    order_type=OrderType.MARKET,
    direction=OrderSide.BUY,
    quantity=100,
)


def _ctx(buying_power: float = 10_000.0) -> PreTradeContext:
    bp = MagicMock(spec=BuyingPowerModel)
    bp.available_buying_power.return_value = buying_power
    account_view = AccountView(
        positions=MappingProxyType({}),
        cash=CashBook(available=50_000.0, settled=50_000.0, frozen=0.0),
        total_value=100_000.0,
        nav=100_000.0,
        exposure=0.0,
        pending_buy_value=0.0,
        order_book=MagicMock(),
    )
    return PreTradeContext(
        account_view=account_view,
        rules={},
        market_snapshots={
            IID: MarketSnapshot(
                trade_date="2026-01-02",
                instrument_id=IID,
                open=10.0,
                high=10.0,
                low=10.0,
                close=10.0,
                prev_close=10.0,
                volume=1_000_000.0,
                amount=10_000_000.0,
            ),
        },
        buying_power_model=bp,
    )


class TestBuyingPowerCheck:
    def setup_method(self) -> None:
        self.check = BuyingPowerCheck()

    def test_sell_accepted(self) -> None:
        """卖出不需要购买力，始终通过。"""
        order = Order(
            order_id="o1",
            instrument_id=IID,
            order_type=OrderType.MARKET,
            direction=OrderSide.SELL,
            quantity=100,
        )
        result = self.check.check_order(order, _ctx())
        assert result.decision == Decision.ACCEPT

    def test_sufficient_power(self) -> None:
        """购买力充足时通过。"""
        # cost = 100 * 10 = 1000, buying_power = 10000
        result = self.check.check_order(ORDER, _ctx(buying_power=10_000.0))
        assert result.decision == Decision.ACCEPT

    def test_insufficient_power(self) -> None:
        """购买力不足时拒绝。"""
        # cost = 100 * 10 = 1000, buying_power = 500
        result = self.check.check_order(ORDER, _ctx(buying_power=500.0))
        assert result.decision == Decision.REJECT
        assert result.reason is not None
        assert "buying_power" in result.reason

    def test_exact_power(self) -> None:
        """购买力恰好等于成本时通过。"""
        result = self.check.check_order(ORDER, _ctx(buying_power=1000.0))
        assert result.decision == Decision.ACCEPT
