"""
StrategyStep -- 运行 Pipeline -> TargetPortfolio.

对应 EngineLoop._step() 中策略部分:
  1. 从 slice_.bars 构建 StrategyInputBundle
  2. pipeline.run(strategy_context, input_bundle) -> TargetPortfolio
  3. 仅在调仓日执行，非调仓日跳过
"""

from __future__ import annotations

from collections.abc import Callable

from ditto_engine.alpha.context import StrategyContext
from ditto_engine.alpha.pipeline import StrategyInputBundle, StrategyPipeline
from ditto_engine.backtest.steps._input_bundle import build_input_bundle
from ditto_engine.backtest.steps.types import StepContext, StepResult

__all__ = ["StrategyStep"]


class StrategyStep:
    """策略运行步骤 -- 运行 Pipeline -> TargetPortfolio."""

    def __init__(
        self,
        pipeline: StrategyPipeline,
        strategy_context: StrategyContext,
        strategy_id: str,
        strategy_run_id: str,
        input_bundle_builder: (
            Callable[[StepContext], StrategyInputBundle] | None
        ) = None,
    ) -> None:
        self._pipeline = pipeline
        self._strategy_context = strategy_context
        self._strategy_id = strategy_id
        self._strategy_run_id = strategy_run_id
        self._input_bundle_builder = input_bundle_builder

    def execute(self, ctx: StepContext) -> StepResult:
        """运行策略 Pipeline。"""
        if not ctx.is_rebalance_day:
            return StepResult.skipped()

        if ctx.slice_ is None:
            return StepResult.fail("slice_ required")

        # 从 slice_.bars 构建 StrategyInputBundle
        if self._input_bundle_builder is not None:
            input_bundle = self._input_bundle_builder(ctx)
        else:
            input_bundle = self._build_input_bundle(ctx)

        # 运行 Pipeline
        target = self._pipeline.run(self._strategy_context, input_bundle)

        # 设置到 context 供后续步骤使用
        ctx.target_portfolio = target

        return StepResult.ok()

    def _build_input_bundle(self, ctx: StepContext) -> StrategyInputBundle:
        """从 Slice 构建 StrategyInputBundle（默认实现）。"""
        slice_ = ctx.slice_
        if slice_ is None:  # guarded by execute() -- unreachable in practice
            msg = "slice_ required"
            raise ValueError(msg)

        return build_input_bundle(
            trade_date=ctx.date,
            strategy_id=self._strategy_id,
            run_id=self._strategy_run_id,
            bars=slice_.bars,
            benchmark_close=slice_.benchmark_close,
        )
