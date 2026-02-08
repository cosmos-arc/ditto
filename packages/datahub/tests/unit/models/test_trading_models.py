"""Trading 模型单元测试."""

from datetime import datetime

from ditto_datahub.models.trading import Order, OrderSide, OrderStatus, Trade


class TestOrderSide:
    """OrderSide 枚举测试."""

    def test_order_side_values(self) -> None:
        """测试 OrderSide 枚举值."""
        assert OrderSide.BUY.value == "buy"
        assert OrderSide.SELL.value == "sell"

    def test_order_side_membership(self) -> None:
        """测试 OrderSide 成员判断."""
        assert OrderSide.BUY in OrderSide
        assert OrderSide.SELL in OrderSide


class TestOrderStatus:
    """OrderStatus 枚举测试."""

    def test_order_status_values(self) -> None:
        """测试 OrderStatus 枚举值."""
        assert OrderStatus.PENDING.value == "pending"
        assert OrderStatus.FILLED.value == "filled"
        assert OrderStatus.PARTIALLY_FILLED.value == "partially_filled"
        assert OrderStatus.CANCELLED.value == "cancelled"
        assert OrderStatus.REJECTED.value == "rejected"

    def test_order_status_count(self) -> None:
        """测试 OrderStatus 枚举数量."""
        assert len(OrderStatus) == 5


class TestOrder:
    """Order 模型测试."""

    def test_order_creation(self) -> None:
        """测试 Order 创建."""
        order = Order(
            order_id="order_001",
            instrument_id=1000001,
            side=OrderSide.BUY,
            quantity=100,
            price=10.5,
            status=OrderStatus.PENDING,
            created_at=datetime(2024, 1, 1, 9, 30, 0),
        )
        assert order.order_id == "order_001"
        assert order.instrument_id == 1000001
        assert order.side == OrderSide.BUY
        assert order.quantity == 100
        assert order.price == 10.5
        assert order.status == OrderStatus.PENDING

    def test_order_with_optional_fields(self) -> None:
        """测试带可选字段的 Order."""
        order = Order(
            order_id="order_002",
            instrument_id=1000002,
            side=OrderSide.SELL,
            quantity=200,
            price=11.0,
            status=OrderStatus.FILLED,
            created_at=datetime(2024, 1, 1, 9, 30, 0),
            filled_at=datetime(2024, 1, 1, 9, 31, 0),
            filled_quantity=200,
            filled_price=11.0,
        )
        assert order.filled_at == datetime(2024, 1, 1, 9, 31, 0)
        assert order.filled_quantity == 200
        assert order.filled_price == 11.0

    def test_order_is_market_order(self) -> None:
        """测试市价单判断."""
        market_order = Order(
            order_id="order_003",
            instrument_id=1000003,
            side=OrderSide.BUY,
            quantity=100,
            price=None,  # 市价单
            status=OrderStatus.PENDING,
            created_at=datetime(2024, 1, 1, 9, 30, 0),
        )
        assert market_order.price is None

    def test_order_is_fully_filled(self) -> None:
        """测试完全成交判断."""
        filled_order = Order(
            order_id="order_004",
            instrument_id=1000004,
            side=OrderSide.BUY,
            quantity=100,
            price=10.5,
            status=OrderStatus.FILLED,
            created_at=datetime(2024, 1, 1, 9, 30, 0),
            filled_at=datetime(2024, 1, 1, 9, 31, 0),
            filled_quantity=100,
            filled_price=10.5,
        )
        assert filled_order.is_fully_filled() is True

    def test_order_not_fully_filled(self) -> None:
        """测试未完全成交判断."""
        partial_order = Order(
            order_id="order_005",
            instrument_id=1000005,
            side=OrderSide.BUY,
            quantity=100,
            price=10.5,
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=datetime(2024, 1, 1, 9, 30, 0),
            filled_at=datetime(2024, 1, 1, 9, 31, 0),
            filled_quantity=50,
            filled_price=10.5,
        )
        assert partial_order.is_fully_filled() is False


class TestTrade:
    """Trade 模型测试."""

    def test_trade_creation(self) -> None:
        """测试 Trade 创建."""
        trade = Trade(
            trade_id="trade_001",
            order_id="order_001",
            instrument_id=1000001,
            side=OrderSide.BUY,
            quantity=100,
            price=10.5,
            trade_time=datetime(2024, 1, 1, 9, 31, 0),
        )
        assert trade.trade_id == "trade_001"
        assert trade.order_id == "order_001"
        assert trade.instrument_id == 1000001
        assert trade.side == OrderSide.BUY
        assert trade.quantity == 100
        assert trade.price == 10.5
        assert trade.trade_time == datetime(2024, 1, 1, 9, 31, 0)
