"""T1: Order ID + Status + Trigger 类型定义单元测试。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from ditto_execution.orders.ids import BrokerOrderId, ClientOrderId
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.trigger import OrderTrigger


class TestClientOrderId:
    """ClientOrderId 值对象。"""

    def test_generate_produces_ditto_prefixed_id(self) -> None:
        id_ = ClientOrderId.generate()
        assert id_.value.startswith("ditto-")

    def test_generate_produces_unique_ids(self) -> None:
        id_a = ClientOrderId.generate()
        id_b = ClientOrderId.generate()
        assert id_a != id_b

    def test_frozen_immutability(self) -> None:
        id_ = ClientOrderId.generate()
        with pytest.raises(FrozenInstanceError):
            id_.value = "hacked"  # type: ignore[misc]

    def test_from_known_value(self) -> None:
        id_ = ClientOrderId(value="test-123")
        assert id_.value == "test-123"


class TestBrokerOrderId:
    """BrokerOrderId 值对象。"""

    def test_from_value(self) -> None:
        id_ = BrokerOrderId(value="broker-abc")
        assert id_.value == "broker-abc"

    def test_frozen_immutability(self) -> None:
        id_ = BrokerOrderId(value="broker-abc")
        with pytest.raises(FrozenInstanceError):
            id_.value = "hacked"  # type: ignore[misc]

    def test_equality(self) -> None:
        a = BrokerOrderId(value="same")
        b = BrokerOrderId(value="same")
        assert a == b

    def test_inequality(self) -> None:
        a = BrokerOrderId(value="a")
        b = BrokerOrderId(value="b")
        assert a != b


class TestOrderStatus:
    """OrderStatus 枚举 + is_terminal。"""

    @pytest.mark.parametrize(
        "status",
        [
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED,
            OrderStatus.INVALID,
        ],
    )
    def test_terminal_states(self, status: OrderStatus) -> None:
        assert status.is_terminal is True

    @pytest.mark.parametrize(
        "status",
        [
            OrderStatus.NEW,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIALLY_FILLED,
        ],
    )
    def test_non_terminal_states(self, status: OrderStatus) -> None:
        assert status.is_terminal is False

    def test_has_seven_members(self) -> None:
        assert len(OrderStatus) == 7


class TestOrderTrigger:
    """OrderTrigger 枚举。"""

    def test_has_five_members(self) -> None:
        assert len(OrderTrigger) == 5

    def test_trigger_values_are_lowercase(self) -> None:
        for trigger in OrderTrigger:
            assert trigger.value == trigger.value.lower()
