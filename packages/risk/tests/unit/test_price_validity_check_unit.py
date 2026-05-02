"""PriceValidityCheck 单元测试。"""

from __future__ import annotations

from types import MappingProxyType
from unittest.mock import MagicMock

from ditto_execution.reality.market import MarketSnapshot
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting.account import AccountView
from ditto_portfolio.accounting.buying_power import BuyingPowerModel
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.order_book import Order, OrderType
from ditto_risk.pre_trade import Decision, PreTradeContext, PriceValidityCheck

IID = InstrumentId(1)


def _snapshot(
    limit_up: float | None = None,
    limit_down: float | None = None,
) -> MarketSnapshot:
    return MarketSnapshot(
        trade_date="2026-01-02",
        instrument_id=IID,
        open=10.0,
        high=11.0,
        low=9.0,
        close=10.0,
        prev_close=10.0,
        volume=1_000_000.0,
        amount=10_000_000.0,
        limit_up=limit_up,
        limit_down=limit_down,
    )


def _ctx(
    snapshots: dict[InstrumentId, MarketSnapshot] | None = None,
) -> PreTradeContext:
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
        rules={},
        market_snapshots=snapshots or {},
        buying_power_model=MagicMock(spec=BuyingPowerModel),
    )


def _order(price: float | None = None) -> Order:
    return Order(
        order_id="o1",
        instrument_id=IID,
        order_type=OrderType.LIMIT if price is not None else OrderType.MARKET,
        direction=OrderSide.BUY,
        quantity=100,
        price=price,
    )


class TestPriceValidityCheck:
    def setup_method(self) -> None:
        self.check = PriceValidityCheck()

    def test_market_order_accepted(self) -> None:
        """市价单始终通过。"""
        result = self.check.check_order(_order(price=None), _ctx())
        assert result.decision == Decision.ACCEPT

    def test_no_snapshot_accepted(self) -> None:
        """无行情快照时通过。"""
        result = self.check.check_order(
            _order(price=10.0),
            _ctx(snapshots={}),
        )
        assert result.decision == Decision.ACCEPT

    def test_no_limits_accepted(self) -> None:
        """涨跌停价格缺失时通过。"""
        result = self.check.check_order(
            _order(price=10.0),
            _ctx(snapshots={IID: _snapshot(limit_up=None, limit_down=None)}),
        )
        assert result.decision == Decision.ACCEPT

    def test_price_within_range(self) -> None:
        """价格在涨跌停范围内通过。"""
        result = self.check.check_order(
            _order(price=10.0),
            _ctx(snapshots={IID: _snapshot(limit_up=11.0, limit_down=9.0)}),
        )
        assert result.decision == Decision.ACCEPT

    def test_price_above_limit_rejected(self) -> None:
        """价格超过涨停价被拒。"""
        result = self.check.check_order(
            _order(price=12.0),
            _ctx(snapshots={IID: _snapshot(limit_up=11.0, limit_down=9.0)}),
        )
        assert result.decision == Decision.REJECT
        assert "price_validity" in result.reason

    def test_price_below_limit_rejected(self) -> None:
        """价格低于跌停价被拒。"""
        result = self.check.check_order(
            _order(price=8.0),
            _ctx(snapshots={IID: _snapshot(limit_up=11.0, limit_down=9.0)}),
        )
        assert result.decision == Decision.REJECT
        assert "price_validity" in result.reason

    def test_price_at_limit_boundary(self) -> None:
        """价格等于涨跌停边界通过。"""
        snap = _snapshot(limit_up=11.0, limit_down=9.0)
        ctx = _ctx(snapshots={IID: snap})
        result_up = self.check.check_order(_order(price=11.0), ctx)
        result_down = self.check.check_order(_order(price=9.0), ctx)
        assert result_up.decision == Decision.ACCEPT
        assert result_down.decision == Decision.ACCEPT
