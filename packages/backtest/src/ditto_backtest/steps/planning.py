"""
PlanningStep -- 获取规则 + 调用 planner.plan().

对应 EngineLoop._step() 中计划部分:
  1. 通过 rule_provider 获取三层规则
  2. rule_ref_collector.observe() 收集规则引用
  3. planner.plan(target, account_view, ...) -> ExecutionPlan
  4. 仅在调仓日执行
"""

from __future__ import annotations

from ditto_execution.planner import ExecutionPlanner
from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import InstrumentRuleProvider, InstrumentRules
from ditto_strategy.alpha.context import StrategyContext

from ditto_backtest.manifest import RuleRefCollector
from ditto_backtest.steps.types import StepContext, StepResult

__all__ = ["PlanningStep"]


class PlanningStep:
    """执行计划步骤 -- 获取规则 + 调用 planner.plan()."""

    def __init__(
        self,
        planner: ExecutionPlanner,
        rule_provider: InstrumentRuleProvider | None,
        rule_ref_collector: RuleRefCollector | None,
        strategy_context: StrategyContext,
    ) -> None:
        self._planner = planner
        self._rule_provider = rule_provider
        self._rule_ref_collector = rule_ref_collector
        self._strategy_context = strategy_context

    def execute(self, ctx: StepContext) -> StepResult:
        """生成执行计划。"""
        if not ctx.is_rebalance_day:
            return StepResult.skipped()

        account_view = ctx.require_account_view()
        target = ctx.require_target_portfolio()

        # 获取三层规则
        rules = self._fetch_rules(ctx)

        # 写入 context 供 PreTradeStep 使用
        ctx.rules = rules

        # 收集规则引用
        if self._rule_ref_collector is not None:
            self._rule_ref_collector.observe(ctx.time_context.trade_date, rules)

        # 生成执行计划
        plan = self._planner.plan(
            target=target,
            account_view=account_view,
            trade_date=ctx.time_context.trade_date,
            market_snapshots=ctx.bars,
            rules=rules,
            locked_instruments=self._strategy_context.get_locked_instruments(),
            order_book=ctx.order_book,
        )

        ctx.execution_plan = plan

        return StepResult.ok()

    def _fetch_rules(
        self,
        ctx: StepContext,
    ) -> dict[InstrumentId, InstrumentRules] | None:
        """通过 RuleProvider 获取三层规则，无 provider 返回 None。"""
        if self._rule_provider is None:
            return None
        ctx.require_slice()
        instrument_ids = list(ctx.bars.keys())
        return self._rule_provider.get_rules(
            ctx.time_context.trade_date,
            instrument_ids,
        )
