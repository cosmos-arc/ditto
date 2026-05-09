"""ConcentrationPreCheck 单元测试。"""

from __future__ import annotations

from types import MappingProxyType
from unittest.mock import MagicMock

from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import MarketSnapshot
from ditto_portfolio.accounting import (
    AccountView,
    BuyingPowerModel,
    CashBook,
    Order,
    Position,
)
from ditto_risk.pre_trade import ConcentrationPreCheck, Decision, PreTradeContext

IID = InstrumentId(1)


def _pos(market_value: float = 10_000.0) -> Position:
    return Position(
        instrument_id=IID,
        quantity=1000,
        available_quantity=1000,
        average_cost=10.0,
        market_value=market_value,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=0.0,
    )


def _ctx(
    nav: float = 100_000.0,
    positions: dict[InstrumentId, Position] | None = None,
    has_price: bool = True,
) -> PreTradeContext:
    snapshots: dict[InstrumentId, MarketSnapshot] = {}
    if has_price:
        snapshots[IID] = MarketSnapshot(
            trade_date="2026-01-02",
            instrument_id=IID,
            open=10.0,
            high=10.0,
            low=10.0,
            close=10.0,
            prev_close=10.0,
            volume=1_000_000.0,
            amount=10_000_000.0,
        )
    return PreTradeContext(
        account_view=AccountView(
            positions=MappingProxyType(positions or {}),
            cash=CashBook(available=50_000.0, settled=50_000.0, frozen=0.0),
            total_value=100_000.0,
            nav=nav,
            exposure=50_000.0,
            pending_buy_value=0.0,
            order_book=MagicMock(),
        ),
        rules={},
        market_snapshots=snapshots,
        buying_power_model=MagicMock(spec=BuyingPowerModel),
    )


def _order(direction: OrderSide = OrderSide.BUY, quantity: int = 100) -> Order:
    return Order(
        order_id="o1",
        instrument_id=IID,
        order_type=OrderType.MARKET,
        direction=direction,
        quantity=quantity,
    )


class TestConcentrationPreCheck:
    def test_sell_accepted(self) -> None:
        """卖出始终通过。"""
        check = ConcentrationPreCheck(max_weight=0.20)
        result = check.check_order(_order(OrderSide.SELL), _ctx())
        assert result.decision == Decision.ACCEPT

    def test_nav_zero_accepted(self) -> None:
        """NAV <= 0 时通过。"""
        check = ConcentrationPreCheck(max_weight=0.20)
        result = check.check_order(_order(), _ctx(nav=0.0))
        assert result.decision == Decision.ACCEPT

    def test_no_price_accepted(self) -> None:
        """无价格时通过。"""
        check = ConcentrationPreCheck(max_weight=0.20)
        result = check.check_order(_order(), _ctx(has_price=False))
        assert result.decision == Decision.ACCEPT

    def test_over_limit_rejected(self) -> None:
        """持仓权重超限时拒绝。"""
        # nav=100000, existing position=30000, order=100*10=1000
        # total_weight = (30000 + 1000) / 100000 = 31% > 20%
        check = ConcentrationPreCheck(max_weight=0.20)
        result = check.check_order(
            _order(quantity=100),
            _ctx(nav=100_000.0, positions={IID: _pos(market_value=30_000.0)}),
        )
        assert result.decision == Decision.REJECT
        assert result.reason is not None
        assert "concentration" in result.reason

    def test_within_limit_accepted(self) -> None:
        """持仓权重在限额内通过。"""
        # nav=100000, no existing position, order=100*10=1000
        # total_weight = 1000 / 100000 = 1% < 20%
        check = ConcentrationPreCheck(max_weight=0.20)
        result = check.check_order(
            _order(quantity=100),
            _ctx(nav=100_000.0),
        )
        assert result.decision == Decision.ACCEPT
