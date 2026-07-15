"""Unit tests for quantity_rounding — round_buy_qty / sell_quantities."""

from ditto_execution.quantity_rounding import (
    round_buy_qty,
    sell_quantities,
    target_quantity,
)

# ---------------------------------------------------------------------------
# round_buy_qty
# ---------------------------------------------------------------------------


class TestRoundBuyQty:
    """Tests for round_buy_qty — 买入数量取整（最小1手）。"""

    def test_round_buy_qty_zero(self) -> None:
        """raw_qty=0 → 0（不买入）。"""
        assert round_buy_qty(0, lot_size=100) == 0

    def test_round_buy_qty_negative(self) -> None:
        """负数 → 0（不买入）。"""
        assert round_buy_qty(-5, lot_size=100) == 0
        assert round_buy_qty(-100, lot_size=100) == 0

    def test_round_buy_qty_normal_above_lot(self) -> None:
        """买入数量向下取整为整手，避免超过目标或现金上限。"""
        assert round_buy_qty(200, lot_size=100) == 200
        assert round_buy_qty(500, lot_size=100) == 500
        assert round_buy_qty(150, lot_size=100) == 100

    def test_round_buy_qty_normal_below_lot(self) -> None:
        """不足一手不强制买入。"""
        assert round_buy_qty(1, lot_size=100) == 0
        assert round_buy_qty(50, lot_size=100) == 0
        assert round_buy_qty(99, lot_size=100) == 0

    def test_round_buy_qty_exactly_lot(self) -> None:
        """raw_qty == lot_size → 原样返回。"""
        assert round_buy_qty(100, lot_size=100) == 100

    def test_round_buy_qty_custom_lot_size(self) -> None:
        """自定义 lot_size。"""
        assert round_buy_qty(5, lot_size=10) == 0
        assert round_buy_qty(15, lot_size=10) == 10


# ---------------------------------------------------------------------------
# sell_quantities
# ---------------------------------------------------------------------------


class TestSellQuantities:
    """Tests for sell_quantities — 卖出数量拆分（整手 + 零股）。"""

    def test_sell_quantities_zero(self) -> None:
        """raw_qty=0 → 空列表。"""
        assert sell_quantities(0, lot_size=100) == []

    def test_sell_quantities_negative(self) -> None:
        """负数 → 空列表。"""
        assert sell_quantities(-5, lot_size=100) == []

    def test_sell_quantities_exact_round_lot(self) -> None:
        """整手数量 → 只有整手部分。"""
        assert sell_quantities(200, lot_size=100) == [200]
        assert sell_quantities(300, lot_size=100) == [300]

    def test_sell_quantities_only_odd_lots(self) -> None:
        """不足一手 → 只有零股部分。"""
        assert sell_quantities(50, lot_size=100) == [50]
        assert sell_quantities(1, lot_size=100) == [1]

    def test_sell_quantities_mixed(self) -> None:
        """整手 + 零股 → 两段拆分。"""
        result = sell_quantities(250, lot_size=100)
        assert result == [200, 50]

    def test_sell_quantities_custom_lot_size(self) -> None:
        """自定义 lot_size 拆分。"""
        result = sell_quantities(25, lot_size=10)
        assert result == [20, 5]

    def test_sell_quantities_exactly_one_lot(self) -> None:
        """刚好 1 手 → 只有整手。"""
        assert sell_quantities(100, lot_size=100) == [100]


# ---------------------------------------------------------------------------
# target_quantity
# ---------------------------------------------------------------------------


class TestTargetQuantity:
    """Tests for target_quantity — 权重转股数（向下取整到 lot_size）。"""

    def test_target_quantity_zero_weight(self) -> None:
        """weight=0 → 0 股。"""
        assert target_quantity(0.0, nav=100_000, lot_size=100) == 0

    def test_target_quantity_tiny_weight(self) -> None:
        """极小权重 → target_value < 1 → 0 股。"""
        assert target_quantity(1e-9, nav=100_000, lot_size=100) == 0

    def test_target_quantity_with_price(self) -> None:
        """有价格 → shares = weight * nav / price，向下取整到 lot_size。"""
        # weight=0.3, nav=100_000, price=10, lot_size=100
        # target_value = 30000, shares = 3000, lots = 30, qty = 3000
        assert target_quantity(0.3, nav=100_000, lot_size=100, price=10.0) == 3000

    def test_target_quantity_with_price_truncates(self) -> None:
        """有价格时向下取整到 lot_size 整数倍。"""
        # weight=0.1, nav=100_000, price=3.0, lot_size=100
        # target_value = 10000, shares = 3333.33, lots = 33, qty = 3300
        assert target_quantity(0.1, nav=100_000, lot_size=100, price=3.0) == 3300

    def test_target_quantity_without_price(self) -> None:
        """无价格（price=0）→ lots = target_value / lot_size。"""
        # weight=0.5, nav=100_000, lot_size=100
        # target_value = 50000, lots = 500, qty = 50000
        assert target_quantity(0.5, nav=100_000, lot_size=100, price=0.0) == 50000

    def test_target_quantity_no_price_defaults(self) -> None:
        """price 参数默认为 0.0。"""
        assert target_quantity(0.5, nav=100_000, lot_size=100) == 50000
