"""NoShortSellCheck 单元测试。"""

from __future__ import annotations

from types import MappingProxyType
from unittest.mock import MagicMock

from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_portfolio.accounting import (
    AccountView,
    BuyingPowerModel,
    CashBook,
    Position,
)
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
        ),
        rules={},
        market_snapshots={},
        buying_power_model=MagicMock(spec=BuyingPowerModel),
    )


def _order(direction: OrderSide, quantity: int = 100) -> Order:
    return Order(
        client_id=ClientOrderId("o1"),
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
        assert result.order_id == "o1"
        assert result.reason is None
        assert result.triggered_checks == ()

    def test_sell_no_position_rejected(self) -> None:
        """无持仓时卖出被拒。"""
        result = self.check.check_order(_order(OrderSide.SELL), _ctx())
        assert result.decision == Decision.REJECT
        assert result.order_id == "o1"
        assert result.reason == (f"no_short_sell: {IID} available=0, requested=100")
        assert result.triggered_checks == ("no_short_sell",)

    def test_sell_insufficient_rejected(self) -> None:
        """持仓不足时卖出被拒。"""
        result = self.check.check_order(
            _order(OrderSide.SELL, quantity=500),
            _ctx(positions={IID: _pos(300, 300)}),
        )
        assert result.decision == Decision.REJECT
        assert result.order_id == "o1"
        assert result.reason == (f"no_short_sell: {IID} available=300, requested=500")
        assert result.triggered_checks == ("no_short_sell",)

    def test_sell_sufficient_accepted(self) -> None:
        """持仓充足时卖出通过。"""
        result = self.check.check_order(
            _order(OrderSide.SELL, quantity=100),
            _ctx(positions={IID: _pos(100, 100)}),
        )
        assert result.decision == Decision.ACCEPT
        assert result.order_id == "o1"
        assert result.reason is None
        assert result.triggered_checks == ()
