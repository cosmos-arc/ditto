"""
ExecutionStep 单元测试.
"""

from __future__ import annotations

from unittest.mock import Mock

from ditto_backtest.steps import ExecutionStep, StepContext, TradingStep
from packages.backtest.tests.unit._helpers import (
    _make_clock,
    _make_fill,
    _make_slice,
)


class TestExecutionStep:
    """ExecutionStep: 处理成交 (process_pending)。"""

    def _make_ctx_with_data(self) -> StepContext:
        """构建包含 slice_ 的 StepContext。"""
        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        ctx.slice_ = _make_slice()
        return ctx

    def test_processes_pending_fills(self) -> None:
        """执行后 fills 被追加到 ctx.step_fills。"""
        fill = _make_fill()
        brokerage = Mock(
            process_pending=Mock(return_value=(fill,)),
        )

        step = ExecutionStep(
            brokerage=brokerage,
            event_bus=None,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        result = step.execute(ctx)

        assert result.success is True
        assert fill in ctx.step_fills

    def test_builds_process_input_from_slice(self) -> None:
        """从 slice_ 构建 ProcessInput 传给 brokerage。"""
        brokerage = Mock(process_pending=Mock(return_value=()))

        step = ExecutionStep(
            brokerage=brokerage,
            event_bus=None,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        step.execute(ctx)

        brokerage.process_pending.assert_called_once()
        process_input = brokerage.process_pending.call_args[0][0]
        assert process_input.trade_date == "2026-03-01"

    def test_publishes_order_filled_events(self) -> None:
        """有 event_bus 时为每个 fill 发布 OrderFilled 事件。"""
        fill_1 = _make_fill(order_id="ord-1")
        fill_2 = _make_fill(order_id="ord-2")
        event_bus = Mock()
        brokerage = Mock(
            process_pending=Mock(return_value=(fill_1, fill_2)),
        )

        step = ExecutionStep(
            brokerage=brokerage,
            event_bus=event_bus,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        step.execute(ctx)

        # 每个 fill 发布一个事件
        assert event_bus.publish.call_count == 2

    def test_no_fills_no_events(self) -> None:
        """无成交时不发布事件。"""
        event_bus = Mock()
        brokerage = Mock(process_pending=Mock(return_value=()))

        step = ExecutionStep(
            brokerage=brokerage,
            event_bus=event_bus,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        step.execute(ctx)

        event_bus.publish.assert_not_called()
        assert len(ctx.step_fills) == 0

    def test_satisfies_trading_step_protocol(self) -> None:
        """ExecutionStep 满足 TradingStep Protocol。"""
        step: TradingStep = ExecutionStep(  # type: ignore[assignment]
            brokerage=Mock(process_pending=Mock(return_value=())),
            event_bus=None,
            clock=_make_clock(),
        )
        ctx = self._make_ctx_with_data()
        result = step.execute(ctx)
        assert result.success is True
