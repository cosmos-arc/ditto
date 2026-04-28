"""
PlanningStep 单元测试.
"""

from __future__ import annotations

from unittest.mock import Mock

from conftest import (
    IID_1,
    _make_account_view,
    _make_execution_plan,
    _make_slice,
)
from ditto_engine.alpha.context import StrategyContext
from ditto_engine.backtest.steps import PlanningStep, StepContext, TradingStep


class TestPlanningStep:
    """PlanningStep: 获取规则 + 调用 planner.plan()。"""

    def _make_ctx_with_target(self) -> StepContext:
        """构建包含 slice_, account_view, target_portfolio 的 StepContext。"""
        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        ctx.slice_ = _make_slice()
        ctx.account_view = _make_account_view()
        ctx.target_portfolio = Mock(name="target_portfolio")
        return ctx

    def test_skips_when_not_rebalance_day(self) -> None:
        """非调仓日跳过计划生成。"""
        step = PlanningStep(
            planner=Mock(),
            rule_provider=None,
            rule_ref_collector=None,
            strategy_context=StrategyContext(),
        )

        ctx = StepContext(date="2026-03-01", is_rebalance_day=False)
        result = step.execute(ctx)

        assert result.success is True

    def test_plans_on_rebalance_day(self) -> None:
        """调仓日调用 planner.plan 并设置 ctx.execution_plan。"""
        plan = _make_execution_plan()
        planner = Mock(plan=Mock(return_value=plan))

        step = PlanningStep(
            planner=planner,
            rule_provider=None,
            rule_ref_collector=None,
            strategy_context=StrategyContext(),
        )

        ctx = self._make_ctx_with_target()
        result = step.execute(ctx)

        assert result.success is True
        assert ctx.execution_plan is plan

    def test_fetches_rules_from_provider(self) -> None:
        """有 rule_provider 时获取规则并传给 planner。"""
        rules = {IID_1: Mock(name="rules")}
        plan = _make_execution_plan()
        planner = Mock(plan=Mock(return_value=plan))
        rule_provider = Mock(get_rules=Mock(return_value=rules))

        step = PlanningStep(
            planner=planner,
            rule_provider=rule_provider,
            rule_ref_collector=None,
            strategy_context=StrategyContext(),
        )

        ctx = self._make_ctx_with_target()
        step.execute(ctx)

        # 验证 rule_provider.get_rules 被调用
        rule_provider.get_rules.assert_called_once()
        # 验证 planner.plan 收到 rules
        planner.plan.assert_called_once()
        call_kwargs = planner.plan.call_args
        assert call_kwargs[1]["rules"] is rules or call_kwargs[0][3] is rules

    def test_observes_rules_in_collector(self) -> None:
        """有 rule_ref_collector 时观察规则引用。"""
        rules = {IID_1: Mock(name="rules")}
        plan = _make_execution_plan()
        planner = Mock(plan=Mock(return_value=plan))
        rule_provider = Mock(get_rules=Mock(return_value=rules))
        collector = Mock()

        step = PlanningStep(
            planner=planner,
            rule_provider=rule_provider,
            rule_ref_collector=collector,
            strategy_context=StrategyContext(),
        )

        ctx = self._make_ctx_with_target()
        step.execute(ctx)

        collector.observe.assert_called_once()

    def test_passes_locked_instruments_to_planner(self) -> None:
        """strategy_context 中被锁定的标的传给 planner。"""
        plan = _make_execution_plan()
        planner = Mock(plan=Mock(return_value=plan))
        strategy_context = StrategyContext()
        strategy_context.lock_instrument(IID_1, "risk", cooldown_until="2026-03-05")

        step = PlanningStep(
            planner=planner,
            rule_provider=None,
            rule_ref_collector=None,
            strategy_context=strategy_context,
        )

        ctx = self._make_ctx_with_target()
        step.execute(ctx)

        planner.plan.assert_called_once()
        call_kwargs = planner.plan.call_args
        locked = (
            call_kwargs[1].get("locked_instruments")
            if call_kwargs[1]
            else call_kwargs[0][4]
            if len(call_kwargs[0]) > 4
            else None
        )
        assert locked is not None
        assert IID_1 in locked

    def test_satisfies_trading_step_protocol(self) -> None:
        """PlanningStep 满足 TradingStep Protocol。"""
        step: TradingStep = PlanningStep(  # type: ignore[assignment]
            planner=Mock(plan=Mock(return_value=_make_execution_plan())),
            rule_provider=None,
            rule_ref_collector=None,
            strategy_context=StrategyContext(),
        )
        ctx = self._make_ctx_with_target()
        result = step.execute(ctx)
        assert result.success is True
