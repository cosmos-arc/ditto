"""FeeModel unit tests — SimpleFeeModel + AShareFeeModel."""

import pytest
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_execution.reality.fee import AShareFeeModel, SimpleFeeModel
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import FeeSchedule

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _order(
    direction: OrderSide = OrderSide.BUY,
    quantity: int = 100,
    instrument_id: int = 1,
) -> Order:
    return Order(
        client_id=ClientOrderId(value="ORD-001"),
        instrument_id=instrument_id,
        order_type=OrderType.MARKET,
        direction=direction,
        quantity=quantity,
        price=None,
    )


_FEE_SCHEDULE = FeeSchedule(
    instrument_id=0,
    as_of_date="",
    commission_rate=0.0003,
    min_commission=5.0,
    stamp_duty_rate=0.0,
    transfer_fee_rate=0.0,
)

_FEE_ETF = FeeSchedule(
    instrument_id=1,
    as_of_date="2026-03-01",
    commission_rate=0.0003,
    min_commission=5.0,
    stamp_duty_rate=0.0,
    transfer_fee_rate=0.0,
)

_FEE_STOCK = FeeSchedule(
    instrument_id=3,
    as_of_date="2026-03-01",
    commission_rate=0.0003,
    min_commission=5.0,
    stamp_duty_rate=0.0005,
    transfer_fee_rate=0.00001,
)


# ---------------------------------------------------------------------------
# SimpleFeeModel
# ---------------------------------------------------------------------------


class TestSimpleFeeModel:
    def test_minimum_fee(self) -> None:
        model = SimpleFeeModel()
        order = _order(quantity=100)
        fee = model.estimate(order, 10.0, _FEE_SCHEDULE)
        assert fee == pytest.approx(5.0)

    def test_proportional_fee(self) -> None:
        model = SimpleFeeModel()
        order = _order(quantity=50_000)
        fee = model.estimate(order, 10.0, _FEE_SCHEDULE)
        assert fee == pytest.approx(150.0)

    def test_exact_threshold(self) -> None:
        model = SimpleFeeModel()
        order = _order(quantity=16_667)
        fee = model.estimate(order, 10.0, _FEE_SCHEDULE)
        assert fee == pytest.approx(50.001)

    def test_sell_same_as_buy(self) -> None:
        model = SimpleFeeModel()
        buy_order = _order(direction=OrderSide.BUY, quantity=50_000)
        sell_order = _order(direction=OrderSide.SELL, quantity=50_000)
        buy_fee = model.estimate(buy_order, 10.0, _FEE_SCHEDULE)
        sell_fee = model.estimate(sell_order, 10.0, _FEE_SCHEDULE)
        assert buy_fee == pytest.approx(sell_fee)

    def test_zero_price(self) -> None:
        model = SimpleFeeModel()
        order = _order(quantity=100)
        fee = model.estimate(order, 0.0, _FEE_SCHEDULE)
        assert fee == pytest.approx(5.0)

    def test_zero_quantity(self) -> None:
        model = SimpleFeeModel()
        order = _order(quantity=0)
        fee = model.estimate(order, 10.0, _FEE_SCHEDULE)
        assert fee == pytest.approx(5.0)

    def test_negative_price_absolute(self) -> None:
        """price 为负时 abs() 保证费用非负。"""
        model = SimpleFeeModel()
        order = _order(quantity=100)
        fee = model.estimate(order, -10.0, _FEE_SCHEDULE)
        assert fee == pytest.approx(5.0)

    def test_calculate_uses_fill_quantity(self) -> None:
        """calculate 方法使用显式传入的 fill_quantity 而非 order.quantity。"""
        model = SimpleFeeModel()
        order = _order(quantity=50_000)
        fee = model.calculate(order, 10.0, 100, _FEE_SCHEDULE)
        assert fee == pytest.approx(5.0)

    def test_calculate_large_fill(self) -> None:
        """calculate 方法大额成交费用。"""
        model = SimpleFeeModel()
        order = _order(quantity=50_000)
        fee = model.calculate(order, 10.0, 50_000, _FEE_SCHEDULE)
        assert fee == pytest.approx(150.0)


# ---------------------------------------------------------------------------
# AShareFeeModel
# ---------------------------------------------------------------------------


class TestAShareFeeModel:
    def test_etf_buy_minimum_commission(self) -> None:
        """ETF 买入 100@10: commission=max(5, 0.3)=5。"""
        model = AShareFeeModel()
        order = _order(quantity=100)
        fee = model.calculate(order, 10.0, 100, _FEE_ETF)
        assert fee == pytest.approx(5.0)

    def test_etf_sell_no_stamp_duty(self) -> None:
        """ETF 卖出: commission=5.0, stamp=0, transfer=0。"""
        model = AShareFeeModel()
        order = _order(direction=OrderSide.SELL, quantity=100)
        fee = model.calculate(order, 10.0, 100, _FEE_ETF)
        assert fee == pytest.approx(5.0)

    def test_stock_buy(self) -> None:
        """股票买入 100@10: commission=5, stamp=0, transfer=0.01。"""
        model = AShareFeeModel()
        order = _order(quantity=100)
        fee = model.calculate(order, 10.0, 100, _FEE_STOCK)
        assert fee == pytest.approx(5.01)

    def test_stock_sell_with_stamp_duty(self) -> None:
        """股票卖出 100@10: commission=5, stamp=0.5, transfer=0.01。"""
        model = AShareFeeModel()
        order = _order(direction=OrderSide.SELL, quantity=100)
        fee = model.calculate(order, 10.0, 100, _FEE_STOCK)
        assert fee == pytest.approx(5.51)

    def test_large_trade_commission_exceeds_minimum(self) -> None:
        """大额卖出 50000@10: commission=150, stamp=250, transfer=5。"""
        model = AShareFeeModel()
        order = _order(direction=OrderSide.SELL, quantity=50_000)
        fee = model.calculate(order, 10.0, 50_000, _FEE_STOCK)
        # commission = max(5, 500000*0.0003) = 150
        # stamp = 500000 * 0.0005 = 250
        # transfer = 500000 * 0.00001 = 5
        assert fee == pytest.approx(405.0)

    def test_estimate_matches_calculate(self) -> None:
        """estimate 和 calculate 对相同参数返回相同值。"""
        model = AShareFeeModel()
        order = _order(direction=OrderSide.SELL, quantity=1000)
        calc = model.calculate(order, 10.0, 1000, _FEE_STOCK)
        est = model.estimate(order, 10.0, _FEE_STOCK)
        assert est == pytest.approx(calc)

    def test_zero_price_returns_min_commission(self) -> None:
        model = AShareFeeModel()
        order = _order(quantity=100)
        fee = model.calculate(order, 0.0, 100, _FEE_STOCK)
        assert fee == pytest.approx(5.0)

    def test_zero_quantity_returns_min_commission(self) -> None:
        model = AShareFeeModel()
        order = _order(quantity=0)
        fee = model.calculate(order, 10.0, 0, _FEE_STOCK)
        assert fee == pytest.approx(5.0)

    def test_etf_large_sell(self) -> None:
        """ETF 大额卖出: 只有佣金，无印花税+过户费。"""
        model = AShareFeeModel()
        order = _order(direction=OrderSide.SELL, quantity=50_000)
        fee = model.calculate(order, 10.0, 50_000, _FEE_ETF)
        assert fee == pytest.approx(150.0)
