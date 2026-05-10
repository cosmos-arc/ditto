"""
StepResult + StepContext + TradingStep Protocol 单元测试.
"""

from __future__ import annotations

import pytest
from ditto_backtest.steps import StepContext, StepResult, TradingStep
from packages.backtest.tests.unit._helpers import _make_ctx


class TestStepResult:
    """StepResult 数据类测试。"""

    def test_ok_factory(self) -> None:
        result = StepResult.ok()
        assert result.success is True
        assert result.errors == ()
        assert result.audit_data == {}

    def test_skipped_factory(self) -> None:
        result = StepResult.skipped()
        assert result.success is True
        assert result.errors == ()
        assert result.audit_data == {}

    def test_fail_factory(self) -> None:
        result = StepResult.fail("err1", "err2")
        assert result.success is False
        assert result.errors == ("err1", "err2")
        assert result.audit_data == {}

    def test_with_audit_data(self) -> None:
        result = StepResult(success=True, audit_data={"key": "value"})
        assert result.audit_data == {"key": "value"}

    def test_frozen(self) -> None:
        result = StepResult.ok()
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]


class TestStepContext:
    """StepContext 可变共享状态测试。"""

    def test_basic_fields(self) -> None:
        ctx = _make_ctx(trade_date="2025-01-15", is_rebalance_day=True)
        assert ctx.time_context.trade_date == "2025-01-15"
        assert ctx.is_rebalance_day is True

    def test_default_none_fields(self) -> None:
        ctx = _make_ctx(trade_date="2025-01-15", is_rebalance_day=True)
        assert ctx.slice_ is None
        assert ctx.account_view is None
        assert ctx.target_portfolio is None
        assert ctx.execution_plan is None
        assert ctx.rules is None

    def test_default_list_fields_empty(self) -> None:
        ctx = _make_ctx(trade_date="2025-01-15", is_rebalance_day=True)
        assert ctx.step_orders == []
        assert ctx.step_fills == []
        assert ctx.pre_trade_decisions == []

    def test_mutable_step_outputs(self) -> None:
        """StepContext 是可变的 -- Steps 会写入结果字段。"""
        ctx = _make_ctx(trade_date="2025-01-15", is_rebalance_day=True)
        ctx.slice_ = "fake_slice"  # type: ignore[assignment]
        assert ctx.slice_ == "fake_slice"

    def test_mutable_step_orders(self) -> None:
        """step_orders 可以被 Steps 追加。"""
        ctx = _make_ctx(trade_date="2025-01-15", is_rebalance_day=True)
        ctx.step_orders.append("order1")  # type: ignore[arg-type]
        assert len(ctx.step_orders) == 1


class TestTradingStepProtocol:
    """验证 TradingStep 可以被正确实现。"""

    def test_concrete_step_satisfies_protocol(self) -> None:
        """自定义 Step 实现 TradingStep Protocol。"""

        class FakeStep:
            def execute(self, ctx: StepContext) -> StepResult:
                return StepResult.ok()

        step: TradingStep = FakeStep()  # type: ignore[assignment]
        ctx = _make_ctx(trade_date="2025-01-15", is_rebalance_day=True)
        result = step.execute(ctx)
        assert result.success is True

    def test_step_returns_skipped(self) -> None:
        """Step 可以返回 skipped 结果。"""

        class SkipStep:
            def execute(self, ctx: StepContext) -> StepResult:
                return StepResult.skipped()

        step: TradingStep = SkipStep()  # type: ignore[assignment]
        ctx = _make_ctx(trade_date="2025-01-15", is_rebalance_day=False)
        result = step.execute(ctx)
        assert result.success is True

    def test_step_returns_failure(self) -> None:
        """Step 可以返回失败结果。"""

        class FailStep:
            def execute(self, ctx: StepContext) -> StepResult:
                return StepResult.fail("something went wrong")

        step: TradingStep = FailStep()  # type: ignore[assignment]
        ctx = _make_ctx(trade_date="2025-01-15", is_rebalance_day=True)
        result = step.execute(ctx)
        assert result.success is False
        assert "something went wrong" in result.errors
