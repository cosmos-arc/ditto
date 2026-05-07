"""
StrategyStep 单元测试.
"""

from __future__ import annotations

from unittest.mock import Mock

from ditto_backtest.steps import StepContext, StrategyStep, TradingStep
from ditto_strategy.alpha.context import StrategyContext
from packages.backtest.tests.unit._helpers import (
    IID_1,
    _make_account_view,
    _make_slice,
    _make_snapshot,
)


class TestStrategyStep:
    """StrategyStep: 运行策略 Pipeline -> TargetPortfolio。"""

    def _make_ctx_with_data(self) -> StepContext:
        """构建包含 slice_ 和 account_view 的 StepContext。"""
        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        ctx.slice_ = _make_slice()
        ctx.account_view = _make_account_view()
        return ctx

    def test_skips_when_not_rebalance_day(self) -> None:
        """非调仓日跳过策略运行。"""
        step = StrategyStep(
            pipeline=Mock(),
            strategy_context=StrategyContext(),
            strategy_id="test-strategy",
            strategy_run_id="run-1",
        )

        ctx = StepContext(date="2026-03-01", is_rebalance_day=False)
        ctx.slice_ = _make_slice()
        result = step.execute(ctx)

        assert result.success is True

    def test_runs_pipeline_on_rebalance_day(self) -> None:
        """调仓日运行 pipeline 并设置 ctx.target_portfolio。"""
        target = Mock(name="target_portfolio")
        pipeline = Mock(run=Mock(return_value=target))

        step = StrategyStep(
            pipeline=pipeline,
            strategy_context=StrategyContext(),
            strategy_id="test-strategy",
            strategy_run_id="run-1",
        )

        ctx = self._make_ctx_with_data()
        result = step.execute(ctx)

        assert result.success is True
        assert ctx.target_portfolio is target
        pipeline.run.assert_called_once()

    def test_builds_input_bundle_from_slice(self) -> None:
        """从 slice_.bars 构建 StrategyInputBundle 传给 pipeline。"""
        target = Mock(name="target_portfolio")
        pipeline = Mock(run=Mock(return_value=target))

        step = StrategyStep(
            pipeline=pipeline,
            strategy_context=StrategyContext(),
            strategy_id="test-strategy",
            strategy_run_id="run-1",
        )

        bars = {IID_1: _make_snapshot(IID_1, close=10.0)}
        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        ctx.slice_ = _make_slice(bars=bars)
        ctx.account_view = _make_account_view()

        step.execute(ctx)

        # 验证 pipeline.run 收到的 input_bundle 含正确的 trade_date
        call_args = pipeline.run.call_args
        input_bundle = call_args[0][1]  # 第二个位置参数
        assert input_bundle.trade_date == "2026-03-01"
        assert input_bundle.strategy_id == "test-strategy"
        assert input_bundle.run_id == "run-1"

    def test_satisfies_trading_step_protocol(self) -> None:
        """StrategyStep 满足 TradingStep Protocol。"""
        step: TradingStep = StrategyStep(  # type: ignore[assignment]
            pipeline=Mock(run=Mock(return_value=Mock())),
            strategy_context=StrategyContext(),
            strategy_id="test",
            strategy_run_id="run-1",
        )
        ctx = self._make_ctx_with_data()
        result = step.execute(ctx)
        assert result.success is True
