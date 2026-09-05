"""T2: FSM 转换表 + transition() 函数单元测试。"""

from __future__ import annotations

import pytest
from ditto_execution.errors import OrderStateError
from ditto_execution.orders.fsm import transition
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.trigger import OrderTrigger


class TestValidTransitions:
    """合法 (status, trigger) 组合 → 正确目标状态。"""

    @pytest.mark.parametrize(
        ("current", "trigger", "expected"),
        [
            (OrderStatus.NEW, OrderTrigger.SUBMIT, OrderStatus.SUBMITTED),
            (OrderStatus.SUBMITTED, OrderTrigger.CANCEL, OrderStatus.CANCELED),
            (OrderStatus.SUBMITTED, OrderTrigger.REJECT, OrderStatus.REJECTED),
            (OrderStatus.NEW, OrderTrigger.INVALIDATE, OrderStatus.INVALID),
            (OrderStatus.SUBMITTED, OrderTrigger.INVALIDATE, OrderStatus.INVALID),
        ],
    )
    def test_simple_transitions(
        self,
        current: OrderStatus,
        trigger: OrderTrigger,
        expected: OrderStatus,
    ) -> None:
        assert transition(current, trigger) == expected

    def test_fill_complete(self) -> None:
        assert (
            transition(
                OrderStatus.SUBMITTED,
                OrderTrigger.FILL,
                fill_qty=100,
                leaves_qty=100,
            )
            == OrderStatus.FILLED
        )

    def test_single_share_fill_is_a_valid_boundary(self) -> None:
        assert (
            transition(
                OrderStatus.SUBMITTED,
                OrderTrigger.FILL,
                fill_qty=1,
                leaves_qty=1,
            )
            == OrderStatus.FILLED
        )

    def test_fill_from_partially_filled(self) -> None:
        assert (
            transition(
                OrderStatus.PARTIALLY_FILLED,
                OrderTrigger.FILL,
                fill_qty=30,
                leaves_qty=50,
            )
            == OrderStatus.PARTIALLY_FILLED
        )

    def test_fill_with_qty_equals_leaves(self) -> None:
        assert (
            transition(
                OrderStatus.SUBMITTED,
                OrderTrigger.FILL,
                fill_qty=100,
                leaves_qty=100,
            )
            == OrderStatus.FILLED
        )

    def test_fill_with_qty_less_than_leaves(self) -> None:
        assert (
            transition(
                OrderStatus.SUBMITTED,
                OrderTrigger.FILL,
                fill_qty=50,
                leaves_qty=100,
            )
            == OrderStatus.PARTIALLY_FILLED
        )

    def test_fill_partial_then_complete(self) -> None:
        partial = transition(
            OrderStatus.SUBMITTED,
            OrderTrigger.FILL,
            fill_qty=50,
            leaves_qty=100,
        )
        assert partial == OrderStatus.PARTIALLY_FILLED

        complete = transition(
            OrderStatus.PARTIALLY_FILLED,
            OrderTrigger.FILL,
            fill_qty=50,
            leaves_qty=50,
        )
        assert complete == OrderStatus.FILLED

    def test_fill_partial_then_partial(self) -> None:
        result = transition(
            OrderStatus.PARTIALLY_FILLED,
            OrderTrigger.FILL,
            fill_qty=30,
            leaves_qty=50,
        )
        assert result == OrderStatus.PARTIALLY_FILLED


class TestInvalidTransitions:
    """非法组合 → OrderStateError。"""

    @pytest.mark.parametrize(
        ("current", "trigger"),
        [
            # terminal states reject all triggers
            (OrderStatus.FILLED, OrderTrigger.FILL),
            (OrderStatus.FILLED, OrderTrigger.CANCEL),
            (OrderStatus.CANCELED, OrderTrigger.SUBMIT),
            (OrderStatus.REJECTED, OrderTrigger.FILL),
            (OrderStatus.INVALID, OrderTrigger.CANCEL),
            # NEW cannot be filled
            (OrderStatus.NEW, OrderTrigger.FILL),
            # cannot submit from non-NEW
            (OrderStatus.SUBMITTED, OrderTrigger.SUBMIT),
            (OrderStatus.PARTIALLY_FILLED, OrderTrigger.SUBMIT),
            # cannot reject from non-SUBMITTED
            (OrderStatus.NEW, OrderTrigger.REJECT),
            (OrderStatus.PARTIALLY_FILLED, OrderTrigger.REJECT),
        ],
    )
    def test_illegal_transition_raises(
        self,
        current: OrderStatus,
        trigger: OrderTrigger,
    ) -> None:
        with pytest.raises(OrderStateError):
            transition(current, trigger)

    @pytest.mark.parametrize(
        "status",
        [
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED,
            OrderStatus.INVALID,
        ],
    )
    def test_terminal_states_reject_all_triggers(
        self,
        status: OrderStatus,
    ) -> None:
        for trigger in OrderTrigger:
            with pytest.raises(OrderStateError):
                transition(status, trigger)

    def test_terminal_error_identifies_the_current_state(self) -> None:
        with pytest.raises(
            OrderStateError,
            match="Cannot transition from terminal state: filled",
        ):
            transition(OrderStatus.FILLED, OrderTrigger.CANCEL)

    def test_invalid_error_identifies_the_attempted_transition(self) -> None:
        with pytest.raises(
            OrderStateError,
            match=r"Invalid transition: submitted \+ submit",
        ):
            transition(OrderStatus.SUBMITTED, OrderTrigger.SUBMIT)

    def test_fill_error_identifies_the_invalid_source_state(self) -> None:
        with pytest.raises(
            OrderStateError,
            match="FILL trigger not allowed from state: new",
        ):
            transition(
                OrderStatus.NEW,
                OrderTrigger.FILL,
                fill_qty=1,
                leaves_qty=1,
            )


class TestFillQtyValidation:
    """fill_qty <= 0 → OrderStateError。"""

    @pytest.mark.parametrize("fill_qty", [0, -1])
    def test_rejects_non_positive_fill_qty(self, fill_qty: int) -> None:
        with pytest.raises(OrderStateError):
            transition(
                OrderStatus.SUBMITTED,
                OrderTrigger.FILL,
                fill_qty=fill_qty,
                leaves_qty=100,
            )

    @pytest.mark.parametrize("fill_qty", [0, -1])
    def test_rejects_non_positive_from_partially_filled(self, fill_qty: int) -> None:
        with pytest.raises(OrderStateError):
            transition(
                OrderStatus.PARTIALLY_FILLED,
                OrderTrigger.FILL,
                fill_qty=fill_qty,
                leaves_qty=50,
            )

    def test_rejects_fill_larger_than_remaining_quantity(self) -> None:
        """A direct FSM caller cannot turn an impossible overfill into FILLED."""
        with pytest.raises(OrderStateError, match="exceeds"):
            transition(
                OrderStatus.SUBMITTED,
                OrderTrigger.FILL,
                fill_qty=101,
                leaves_qty=100,
            )

    def test_non_positive_error_preserves_the_invalid_quantity(self) -> None:
        with pytest.raises(
            OrderStateError,
            match="FILL requires positive fill_qty, got 0",
        ):
            transition(
                OrderStatus.SUBMITTED,
                OrderTrigger.FILL,
                fill_qty=0,
                leaves_qty=1,
            )

    def test_zero_leaves_error_preserves_the_invalid_quantity(self) -> None:
        with pytest.raises(
            OrderStateError,
            match=r"FILL with no remaining leaves_qty \(0\)",
        ):
            transition(
                OrderStatus.SUBMITTED,
                OrderTrigger.FILL,
                fill_qty=1,
                leaves_qty=0,
            )
