"""Order 子域单元测试."""

from ditto_kernel.order import OrderSide


class TestOrderSide:
    """OrderSide 枚举测试."""

    def test_values(self) -> None:
        assert OrderSide.BUY.value == "buy"
        assert OrderSide.SELL.value == "sell"

    def test_from_string(self) -> None:
        assert OrderSide("buy") is OrderSide.BUY
        assert OrderSide("sell") is OrderSide.SELL

    def test_invalid_value_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError):
            OrderSide("hold")
