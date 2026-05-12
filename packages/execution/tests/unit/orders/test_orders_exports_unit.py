"""T7: execution/orders/ barrel 导出验证。"""

from __future__ import annotations

import ditto_execution.orders as orders_pkg


class TestOrdersExports:
    """验证全部公开类型可从 orders 包导入。"""

    def test_all_exports_importable(self) -> None:
        for name in orders_pkg.__all__:
            assert hasattr(orders_pkg, name), f"Missing export: {name}"

    def test_key_types_present(self) -> None:
        expected = {
            "ClientOrderId",
            "BrokerOrderId",
            "OrderStatus",
            "OrderTrigger",
            "Order",
            "OrderEvent",
            "OrderEventJournal",
            "InMemoryOrderEventJournal",
            "OrderTicket",
            "OrderBook",
            "OrderBookReadOnly",
            "TRANSITIONS",
            "transition",
        }
        actual = set(orders_pkg.__all__)
        missing = expected - actual
        assert not missing, f"Missing from __all__: {missing}"
