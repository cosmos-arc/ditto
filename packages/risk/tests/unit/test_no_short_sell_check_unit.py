"""NoShortSellCheck 单元测试。"""

from __future__ import annotations

from types import MappingProxyType
from unittest.mock import MagicMock

from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting.account import AccountView
from ditto_portfolio.accounting.buying_power import BuyingPowerModel
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.order_book import Order, OrderType
from ditto_portfolio.accounting.position import Position
from ditto_risk.pre_trade import Decision, NoShortSellCheck, PreTradeContext

IID = InstrumentId(1)


def _pos(quantity: int, available: int) -> Position:
    return Position(
        instrument_id=IID,
        quantity=quantity,
        available_quantity=available,
        average_cost=10.0,
        market_value=10_000.0,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=0.0,
    )


def _ctx(positions: dict[InstrumentId, Position] | None = None) -> PreTradeContext:
    return PreTradeContext(
        account_view=AccountView(
            positions=MappingProxyType(positions or {}),
            cash=CashBook(available=50_000.0, settled=50_000.0, frozen=0.0),
            total_value=100_000.0,
            nav=100_000.0,
            exposure=50_000.0,
            pending_buy_value=0.0,
            order_book=MagicMock(),
        ),
        rules={},
        market_snapshots={},
        buying_power_model=MagicMock(spec=BuyingPowerModel),
    )


def _order(direction: OrderSide, quantity: int = 100) -> Order:
    return Order(
        order_id="o1",
        instrument_id=IID,
        order_type=OrderType.MARKET,
        direction=direction,
        quantity=quantity,
    )


class TestNoShortSellCheck:
    def setup_method(self) -> None:
        self.check = NoShortSellCheck()

    def test_buy_accepted(self) -> None:
        """BUY 始终通过。"""
        result = self.check.check_order(_order(OrderSide.BUY), _ctx())
        assert result.decision == Decision.ACCEPT

    def test_sell_no_position_rejected(self) -> None:
        """无持仓时卖出被拒。"""
        result = self.check.check_order(_order(OrderSide.SELL), _ctx())
        assert result.decision == Decision.REJECT
        assert "no_short_sell" in result.reason
        assert "available=0" in result.reason

    def test_sell_insufficient_rejected(self) -> None:
        """持仓不足时卖出被拒。"""
        result = self.check.check_order(
            _order(OrderSide.SELL, quantity=500),
            _ctx(positions={IID: _pos(300, 300)}),
        )
        assert result.decision == Decision.REJECT
        assert "available=300" in result.reason

    def test_sell_sufficient_accepted(self) -> None:
        """持仓充足时卖出通过。"""
        result = self.check.check_order(
            _order(OrderSide.SELL, quantity=100),
            _ctx(positions={IID: _pos(1000, 1000)}),
        )
        assert result.decision == Decision.ACCEPT
