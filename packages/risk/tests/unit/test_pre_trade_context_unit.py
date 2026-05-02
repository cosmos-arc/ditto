"""PreTradeContext 单元测试。"""

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
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_LOT_SIZE,
    DEFAULT_MIN_COMMISSION,
)
from ditto_portfolio.accounting.account import AccountView
from ditto_portfolio.accounting.buying_power import BuyingPowerModel
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.order_book import Order
from ditto_portfolio.accounting.position import Position
from ditto_risk.pre_trade import PreTradeContext

IID_A = InstrumentId(1)
IID_B = InstrumentId(2)


def _make_position(
    instrument_id: InstrumentId,
    quantity: int = 1000,
    available_quantity: int = 1000,
    average_cost: float = 10.0,
    market_value: float = 10_000.0,
) -> Position:
    return Position(
        instrument_id=instrument_id,
        quantity=quantity,
        available_quantity=available_quantity,
        average_cost=average_cost,
        market_value=market_value,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=0.0,
    )


def _make_snapshot(
    instrument_id: InstrumentId,
    close: float = 10.0,
    limit_up: float | None = None,
    limit_down: float | None = None,
) -> MarketSnapshot:
    return MarketSnapshot(
        trade_date="2026-01-02",
        instrument_id=instrument_id,
        open=close,
        high=close,
        low=close,
        close=close,
        prev_close=close,
        volume=1_000_000.0,
        amount=10_000_000.0,
        limit_up=limit_up,
        limit_down=limit_down,
    )


def _make_rules(instrument_id: InstrumentId, lot_size: int = 100) -> InstrumentRules:
    return (
        InstrumentDefinition(
            instrument_id=instrument_id,
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
            instrument_id=instrument_id,
            as_of_date="2026-01-02",
            settlement_cycle=1,
            fund_settlement_cycle=1,
            price_limit_pct=0.10,
            order_types_supported=("market", "limit"),
            call_auction_sessions=("open", "close"),
        ),
        FeeSchedule(
            instrument_id=instrument_id,
            as_of_date="2026-01-02",
            commission_rate=DEFAULT_COMMISSION_RATE,
            min_commission=DEFAULT_MIN_COMMISSION,
            stamp_duty_rate=0.0,
            transfer_fee_rate=0.0,
        ),
    )


def _make_account_view(
    cash: CashBook | None = None,
    positions: dict[InstrumentId, Position] | None = None,
    nav: float = 100_000.0,
    total_value: float | None = None,
    exposure: float | None = None,
) -> AccountView:
    actual_cash = cash or CashBook(available=50_000.0, settled=50_000.0, frozen=0.0)
    actual_positions = positions or {}
    actual_exposure = exposure if exposure is not None else 50_000.0
    actual_total = (
        total_value if total_value is not None else actual_cash.total + actual_exposure
    )
    return AccountView(
        positions=MappingProxyType(actual_positions),
        cash=actual_cash,
        total_value=actual_total,
        nav=nav,
        exposure=actual_exposure,
        pending_buy_value=0.0,
        order_book=MagicMock(),
    )


def _make_context(**overrides: object) -> PreTradeContext:
    defaults: dict[str, object] = {
        "account_view": _make_account_view(),
        "rules": {IID_A: _make_rules(IID_A)},
        "market_snapshots": {IID_A: _make_snapshot(IID_A)},
        "buying_power_model": MagicMock(spec=BuyingPowerModel),
    }
    defaults.update(overrides)
    return PreTradeContext(**defaults)  # type: ignore[arg-type]


class TestPriceFor:
    def test_price_for_found(self) -> None:
        """有快照时返回 close 价格。"""
        ctx = _make_context()
        assert ctx.price_for(IID_A) == 10.0

    def test_price_for_not_found(self) -> None:
        """无快照时返回 None。"""
        ctx = _make_context()
        assert ctx.price_for(IID_B) is None


class TestLotSizeFor:
    def test_lot_size_for_found(self) -> None:
        """有规则时返回 lot_size。"""
        ctx = _make_context(rules={IID_A: _make_rules(IID_A, lot_size=200)})
        assert ctx.lot_size_for(IID_A) == 200

    def test_lot_size_for_default(self) -> None:
        """无规则时返回 DEFAULT_LOT_SIZE。"""
        ctx = _make_context()
        assert ctx.lot_size_for(IID_B) == DEFAULT_LOT_SIZE


class TestFeeScheduleFor:
    def test_fee_schedule_for_found(self) -> None:
        """有规则时返回对应的 FeeSchedule。"""
        rules = _make_rules(IID_A)
        ctx = _make_context(rules={IID_A: rules})
        result = ctx.fee_schedule_for(IID_A)
        assert result.commission_rate == DEFAULT_COMMISSION_RATE

    def test_fee_schedule_for_default(self) -> None:
        """无规则时返回默认 FeeSchedule。"""
        ctx = _make_context()
        result = ctx.fee_schedule_for(IID_B)
        assert result.commission_rate == DEFAULT_COMMISSION_RATE
        assert result.min_commission == DEFAULT_MIN_COMMISSION


class TestEstimateOrderCost:
    def test_estimate_order_cost(self) -> None:
        """估算订单成本 = quantity * price + fee。"""
        fee_model = MagicMock()
        fee_model.estimate.return_value = 15.0
        ctx = _make_context(fee_model=fee_model)
        order = Order(
            order_id="o1",
            instrument_id=IID_A,
            order_type=OrderType.MARKET,
            direction=OrderSide.BUY,
            quantity=100,
        )
        cost = ctx.estimate_order_cost(order)
        assert cost == 100 * 10.0 + 15.0

    def test_estimate_order_cost_no_price(self) -> None:
        """无价格时返回 0。"""
        ctx = _make_context(market_snapshots={})
        order = Order(
            order_id="o1",
            instrument_id=IID_A,
            order_type=OrderType.MARKET,
            direction=OrderSide.BUY,
            quantity=100,
        )
        assert ctx.estimate_order_cost(order) == 0.0

    def test_estimate_order_cost_no_fee_model(self) -> None:
        """无 fee_model 时 cost = quantity * price。"""
        ctx = _make_context(fee_model=None)
        order = Order(
            order_id="o1",
            instrument_id=IID_A,
            order_type=OrderType.MARKET,
            direction=OrderSide.BUY,
            quantity=200,
        )
        assert ctx.estimate_order_cost(order) == 200 * 10.0


class TestWithOrderAccepted:
    def test_with_order_accepted_buy(self) -> None:
        """BUY: 扣减可用现金，增加冻结和 pending_buy_value。"""
        fee_model = MagicMock()
        fee_model.estimate.return_value = 10.0
        ctx = _make_context(
            fee_model=fee_model,
            account_view=_make_account_view(
                cash=CashBook(available=50_000.0, settled=50_000.0, frozen=0.0),
            ),
        )
        order = Order(
            order_id="o1",
            instrument_id=IID_A,
            order_type=OrderType.MARKET,
            direction=OrderSide.BUY,
            quantity=100,
        )
        new_ctx = ctx.with_order_accepted(order)
        estimated_cost = 100 * 10.0 + 10.0
        assert new_ctx.account_view.cash.available == 50_000.0 - estimated_cost
        assert new_ctx.account_view.cash.frozen == 0.0 + estimated_cost
        assert new_ctx.account_view.pending_buy_value == estimated_cost

    def test_with_order_accepted_sell(self) -> None:
        """SELL: 减少 available_quantity。"""
        pos = _make_position(IID_A, quantity=1000, available_quantity=800)
        ctx = _make_context(
            account_view=_make_account_view(positions={IID_A: pos}),
        )
        order = Order(
            order_id="o1",
            instrument_id=IID_A,
            order_type=OrderType.MARKET,
            direction=OrderSide.SELL,
            quantity=300,
        )
        new_ctx = ctx.with_order_accepted(order)
        new_pos = new_ctx.account_view.positions[IID_A]
        assert new_pos.available_quantity == 500

    def test_with_order_accepted_sell_insufficient(self) -> None:
        """SELL 超过持仓量时 available_quantity 为 0 而不报错。"""
        pos = _make_position(IID_A, quantity=1000, available_quantity=100)
        ctx = _make_context(
            account_view=_make_account_view(positions={IID_A: pos}),
        )
        order = Order(
            order_id="o1",
            instrument_id=IID_A,
            order_type=OrderType.MARKET,
            direction=OrderSide.SELL,
            quantity=500,
        )
        new_ctx = ctx.with_order_accepted(order)
        new_pos = new_ctx.account_view.positions[IID_A]
        assert new_pos.available_quantity == 0

    def test_with_order_accepted_sell_no_position(self) -> None:
        """SELL 无持仓时 account_view 不变（position 不存在跳过修改）。"""
        ctx = _make_context()
        order = Order(
            order_id="o1",
            instrument_id=IID_A,
            order_type=OrderType.MARKET,
            direction=OrderSide.SELL,
            quantity=100,
        )
        new_ctx = ctx.with_order_accepted(order)
        # 新上下文的 account_view 与原始相同（replace 但无字段变更）
        assert new_ctx.account_view is ctx.account_view

    def test_with_order_accepted_no_price(self) -> None:
        """无价格时返回原上下文。"""
        ctx = _make_context(market_snapshots={})
        order = Order(
            order_id="o1",
            instrument_id=IID_A,
            order_type=OrderType.MARKET,
            direction=OrderSide.BUY,
            quantity=100,
        )
        new_ctx = ctx.with_order_accepted(order)
        assert new_ctx is ctx


class TestTotalValueAndNav:
    def test_total_value_calculation(self) -> None:
        """total_value 来自 account_view，由 cash.total + exposure 组成。"""
        pos = _make_position(IID_A, market_value=20_000.0)
        ctx = _make_context(
            account_view=_make_account_view(
                cash=CashBook(available=30_000.0, settled=30_000.0, frozen=0.0),
                positions={IID_A: pos},
                nav=50_000.0,
                exposure=20_000.0,
            ),
        )
        assert ctx.account_view.total_value == 30_000.0 + 20_000.0

    def test_nav_equals_total_value(self) -> None:
        """nav 属性直接读取 account_view.nav。"""
        ctx = _make_context(
            account_view=_make_account_view(nav=88_888.0),
        )
        assert ctx.account_view.nav == 88_888.0
