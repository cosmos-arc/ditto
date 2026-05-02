"""LotSizeCheck 单元测试。"""

from __future__ import annotations

from types import MappingProxyType
from unittest.mock import MagicMock

from ditto_execution.reality.market import MarketSnapshot
from ditto_execution.rules import (
    FeeSchedule,
    InstrumentDefinition,
    InstrumentRules,
    TradingRuleSet,
)
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_kernel.trading import DEFAULT_COMMISSION_RATE, DEFAULT_MIN_COMMISSION
from ditto_portfolio.accounting.account import AccountView
from ditto_portfolio.accounting.buying_power import BuyingPowerModel
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.order_book import Order, OrderType
from ditto_risk.pre_trade import Decision, LotSizeCheck, PreTradeContext

IID = InstrumentId(1)


def _rules(lot_size: int = 100) -> InstrumentRules:
    return (
        InstrumentDefinition(
            instrument_id=IID,
            asset_class="etf",
            exchange="XSHG",
            currency="CNY",
            tick_size=0.001,
            lot_size=lot_size,
            multiplier=1.0,
            board_segment="main",
            lifecycle_state="normal",
        ),
        TradingRuleSet(
            instrument_id=IID,
            as_of_date="2026-01-02",
            settlement_cycle=1,
            fund_settlement_cycle=1,
            price_limit_pct=0.10,
            order_types_supported=("market",),
            call_auction_sessions=("open",),
        ),
        FeeSchedule(
            instrument_id=IID,
            as_of_date="2026-01-02",
            commission_rate=DEFAULT_COMMISSION_RATE,
            min_commission=DEFAULT_MIN_COMMISSION,
            stamp_duty_rate=0.0,
            transfer_fee_rate=0.0,
        ),
    )


def _ctx(rules: dict[InstrumentId, InstrumentRules] | None = None) -> PreTradeContext:
    return PreTradeContext(
        account_view=AccountView(
            positions=MappingProxyType({}),
            cash=CashBook(available=50_000.0, settled=50_000.0, frozen=0.0),
            total_value=100_000.0,
            nav=100_000.0,
            exposure=0.0,
            pending_buy_value=0.0,
            order_book=MagicMock(),
        ),
        rules=rules or {IID: _rules(lot_size=100)},
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


class TestLotSizeCheck:
    def setup_method(self) -> None:
        self.check = LotSizeCheck()

    def test_sell_accepted(self) -> None:
        """卖出始终通过。"""
        result = self.check.check_order(_order(OrderSide.SELL), _ctx())
        assert result.decision == Decision.ACCEPT

    def test_zero_lot_size_accepted(self) -> None:
        """lot_size <= 0 时直接通过。"""
        result = self.check.check_order(
            _order(OrderSide.BUY, quantity=50),
            _ctx(rules={IID: _rules(lot_size=0)}),
        )
        assert result.decision == Decision.ACCEPT

    def test_valid_lot_multiple(self) -> None:
        """数量是 lot_size 整数倍时通过。"""
        result = self.check.check_order(
            _order(OrderSide.BUY, quantity=200),
            _ctx(),
        )
        assert result.decision == Decision.ACCEPT

    def test_invalid_lot_resized(self) -> None:
        """数量不是 lot_size 整数倍时 RESIZE。"""
        result = self.check.check_order(
            _order(OrderSide.BUY, quantity=150),
            _ctx(rules={IID: _rules(lot_size=100)}),
        )
        assert result.decision == Decision.RESIZE
        assert result.resized_quantity == 200

    def test_resize_rounds_up(self) -> None:
        """RESIZE 向上取整到下一个 lot_size 整数倍。"""
        result = self.check.check_order(
            _order(OrderSide.BUY, quantity=1),
            _ctx(rules={IID: _rules(lot_size=100)}),
        )
        assert result.decision == Decision.RESIZE
        assert result.resized_quantity == 100

    def test_zero_quantity_resized_to_lot(self) -> None:
        """数量为 0 时 resize 到 lot_size。"""
        result = self.check.check_order(
            _order(OrderSide.BUY, quantity=0),
            _ctx(rules={IID: _rules(lot_size=100)}),
        )
        assert result.decision == Decision.RESIZE
        assert result.resized_quantity == 100
