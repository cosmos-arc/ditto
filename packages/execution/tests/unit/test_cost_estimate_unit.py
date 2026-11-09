"""Unit tests for cost_estimate — get_estimated_price / calc_turnover / calc_cost."""

from __future__ import annotations

from dataclasses import replace

import pytest
from ditto_execution.cost_estimate import calc_cost, calc_turnover, get_estimated_price
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import FeeSchedule, InstrumentRules, MarketSnapshot

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_IID_A = InstrumentId(1)
_IID_B = InstrumentId(2)


def _snap(
    iid: InstrumentId = _IID_A,
    close: float = 10.0,
) -> MarketSnapshot:
    return MarketSnapshot(
        trade_date="2026-01-01",
        instrument_id=iid,
        open=close - 0.1,
        high=close + 0.1,
        low=close - 0.2,
        close=close,
        prev_close=close - 0.05,
        volume=1000000.0,
        amount=10000000.0,
    )


def _order(
    iid: InstrumentId = _IID_A,
    quantity: int = 100,
    direction: OrderSide = OrderSide.BUY,
) -> Order:
    return Order(
        client_id=ClientOrderId(value="ORD-001"),
        instrument_id=iid,
        order_type=OrderType.MARKET,
        direction=direction,
        quantity=quantity,
        price=None,
    )


def _fee_schedule(
    iid: InstrumentId = _IID_A,
    commission_rate: float = 0.0003,
    stamp_duty_rate: float = 0.0005,
    transfer_fee_rate: float = 0.00001,
) -> FeeSchedule:
    return FeeSchedule(
        instrument_id=iid,
        as_of_date="2026-01-01",
        commission_rate=commission_rate,
        min_commission=5.0,
        stamp_duty_rate=stamp_duty_rate,
        transfer_fee_rate=transfer_fee_rate,
    )


def _instrument_rules(
    iid: InstrumentId = _IID_A,
    commission_rate: float = 0.0003,
    stamp_duty_rate: float = 0.0005,
    transfer_fee_rate: float = 0.00001,
) -> dict[InstrumentId, InstrumentRules]:
    from ditto_kernel.trading import InstrumentDefinition, TradingRuleSet

    return {
        iid: (
            InstrumentDefinition(
                instrument_id=iid,
                asset_class="etf",
                exchange="XSHE",
                currency="CNY",
                tick_size=0.01,
                lot_size=100,
                multiplier=1.0,
                board_segment="main",
                lifecycle_state="active",
            ),
            TradingRuleSet(
                instrument_id=iid,
                as_of_date="2026-01-01",
                settlement_cycle=1,
                fund_settlement_cycle=1,
                price_limit_pct=0.10,
                order_types_supported=("market", "limit"),
                call_auction_sessions=(),
            ),
            _fee_schedule(iid, commission_rate, stamp_duty_rate, transfer_fee_rate),
        )
    }


# ---------------------------------------------------------------------------
# get_estimated_price
# ---------------------------------------------------------------------------


class TestGetEstimatedPrice:
    """Tests for get_estimated_price."""

    def test_returns_close_when_snapshot_exists(self) -> None:
        market = {_IID_A: _snap(_IID_A, close=15.5)}
        assert get_estimated_price(market, _IID_A) == 15.5

    def test_returns_zero_when_snapshot_missing(self) -> None:
        market: dict[InstrumentId, MarketSnapshot] = {}
        assert get_estimated_price(market, _IID_A) == 0.0


# ---------------------------------------------------------------------------
# calc_turnover
# ---------------------------------------------------------------------------


class TestCalcTurnover:
    """Tests for calc_turnover."""

    def test_single_order(self) -> None:
        orders = [_order(_IID_A, quantity=100)]
        market = {_IID_A: _snap(_IID_A, close=10.0)}
        # turnover = 100 * 10.0 = 1000.0
        assert calc_turnover(orders, market) == 1000.0

    def test_multiple_orders(self) -> None:
        orders = [
            _order(_IID_A, quantity=100),
            _order(_IID_B, quantity=200),
        ]
        market = {
            _IID_A: _snap(_IID_A, close=10.0),
            _IID_B: _snap(_IID_B, close=5.0),
        }
        # turnover = 100*10 + 200*5 = 2000.0
        assert calc_turnover(orders, market) == 2000.0

    def test_empty_orders(self) -> None:
        assert calc_turnover([], {_IID_A: _snap()}) == 0.0

    def test_order_with_missing_market_snapshot(self) -> None:
        orders = [_order(_IID_A, quantity=100)]
        # No market snapshot for _IID_A → price=0.0 → turnover=0.0
        assert calc_turnover(orders, {}) == 0.0

    def test_sell_order_uses_abs_quantity(self) -> None:
        orders = [_order(_IID_A, quantity=100, direction=OrderSide.SELL)]
        market = {_IID_A: _snap(_IID_A, close=10.0)}
        # abs(100) * 10.0 = 1000.0
        assert calc_turnover(orders, market) == 1000.0


# ---------------------------------------------------------------------------
# calc_cost
# ---------------------------------------------------------------------------


def test_cost_uses_actual_order_side_minimum_and_nominal_transfer() -> None:
    rules = _instrument_rules()
    definition, trading, fee = rules[_IID_A]
    rules[_IID_A] = (
        definition,
        trading,
        replace(
            fee,
            stamp_duty_rate=0.001,
            transfer_fee_rate=0.0,
            transfer_fee_per_share=0.0003,
        ),
    )
    orders = [_order(direction=OrderSide.BUY), _order(direction=OrderSide.SELL)]
    assert calc_cost(orders, {_IID_A: _snap()}, rules) == pytest.approx(11.06)
    assert calc_cost([], {}, {}) == 0.0


def test_cost_preserves_legacy_optional_inputs() -> None:
    assert calc_cost([_order()], {}, _instrument_rules()) == 0.0
    assert calc_cost([_order()], {_IID_A: _snap()}, {}) == 0.0
