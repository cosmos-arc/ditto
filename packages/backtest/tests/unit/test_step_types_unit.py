"""
StepResult + StepContext + TradingStep Protocol 单元测试.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_backtest.errors import SimulationError
from ditto_backtest.steps import StepContext, StepResult, TradingStep
from packages.backtest.tests.unit._helpers import (
    _make_account_view,
    _make_ctx,
    _make_execution_plan,
    _make_slice,
)


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
        _ctx = _make_ctx(trade_date="2025-01-15", is_rebalance_day=True)
        result = step.execute(_ctx)
        assert result.success is True

    def test_step_returns_skipped(self) -> None:
        """Step 可以返回 skipped 结果。"""

        class SkipStep:
            def execute(self, ctx: StepContext) -> StepResult:
                return StepResult.skipped()

        step: TradingStep = SkipStep()  # type: ignore[assignment]
        _ctx = _make_ctx(trade_date="2025-01-15", is_rebalance_day=False)
        result = step.execute(_ctx)
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


class TestStepContextRequireGetters:
    """StepContext.require_*() 类型安全 getter 测试。"""

    # -- require_slice

    def test_require_slice_returns_value_when_set(self) -> None:
        """slice_ 已设置时 require_slice() 返回值。"""
        ctx = _make_ctx()
        slice_ = _make_slice()
        ctx.slice_ = slice_
        assert ctx.require_slice() is slice_

    def test_require_slice_raises_when_none(self) -> None:
        """slice_ 为 None 时 require_slice() 抛出 SimulationError。"""
        ctx = _make_ctx()
        with pytest.raises(SimulationError, match="slice_"):
            ctx.require_slice()

    # -- require_account_view

    def test_require_account_view_returns_value_when_set(self) -> None:
        """account_view 已设置时 require_account_view() 返回值。"""
        ctx = _make_ctx()
        account_view = _make_account_view()
        ctx.account_view = account_view
        assert ctx.require_account_view() is account_view

    def test_require_account_view_raises_when_none(self) -> None:
        """account_view 为 None 时 require_account_view() 抛出 SimulationError。"""
        ctx = _make_ctx()
        with pytest.raises(SimulationError, match="account_view"):
            ctx.require_account_view()

    # -- require_execution_plan

    def test_require_execution_plan_returns_value_when_set(self) -> None:
        """execution_plan 已设置时 require_execution_plan() 返回值。"""
        ctx = _make_ctx()
        plan = _make_execution_plan()
        ctx.execution_plan = plan
        assert ctx.require_execution_plan() is plan

    def test_require_execution_plan_raises_when_none(self) -> None:
        """execution_plan 为 None 时 require_execution_plan() 抛出 SimulationError。"""
        ctx = _make_ctx()
        with pytest.raises(SimulationError, match="execution_plan"):
            ctx.require_execution_plan()

    # -- require_target_portfolio

    def test_require_target_portfolio_returns_value_when_set(self) -> None:
        """target_portfolio 已设置时 require_target_portfolio() 返回值。"""
        ctx = _make_ctx()
        target = MagicMock()  # TargetPortfolioLike 是 Protocol，用 mock 模拟
        ctx.target_portfolio = target
        assert ctx.require_target_portfolio() is target

    def test_require_target_portfolio_raises_when_none(self) -> None:
        """target_portfolio 为 None 时抛出 SimulationError。"""
        ctx = _make_ctx()
        with pytest.raises(SimulationError, match="target_portfolio"):
            ctx.require_target_portfolio()

    # -- 错误信息质量

    def test_error_message_contains_field_name(self) -> None:
        """错误信息包含字段名和上下文描述。"""
        ctx = _make_ctx()
        with pytest.raises(SimulationError, match=r"slice_.*required"):
            ctx.require_slice()
