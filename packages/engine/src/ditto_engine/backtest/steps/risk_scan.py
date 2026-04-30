"""
RiskScanStep -- PostTrade 风控扫描 + 锁管理.

对应 EngineLoop._step() 中 PostTrade 风控部分:
  1. post_trade_guard.scan(account_view, slice_) -> RiskAction[]
  2. 记录风控审计 (audit_collector)
  3. 对 REDUCE_POSITION/LIQUIDATE + INSTRUMENT scope 锁定标的
  4. 发布 RiskGuardTriggered 事件 (event_bus)
"""

from __future__ import annotations

from ditto_kernel.clock import Clock
from ditto_kernel.events import EventBus
from ditto_risk.post_trade import (
    PostTradeRiskGuard,
    RiskActionType,
    RiskScope,
)
from ditto_strategy.alpha.context import StrategyContext

from ditto_engine.backtest.audit.collector import ExecutionAuditCollector
from ditto_engine.backtest.audit.records import RiskScanRecord
from ditto_engine.backtest.steps.types import StepContext, StepResult
from ditto_engine.events import RiskGuardTriggered

__all__ = ["RiskScanStep"]


class RiskScanStep:
    """PostTrade 风控扫描步骤 -- 扫描风险 + 锁定标的 + 发布事件."""

    def __init__(
        self,
        post_trade_guard: PostTradeRiskGuard | None,
        audit_collector: ExecutionAuditCollector | None,
        event_bus: EventBus | None,
        strategy_context: StrategyContext,
        clock: Clock,
    ) -> None:
        self._post_trade_guard = post_trade_guard
        self._audit_collector = audit_collector
        self._event_bus = event_bus
        self._strategy_context = strategy_context
        self._clock = clock

    def execute(self, ctx: StepContext) -> StepResult:
        """执行风控扫描。"""
        if self._post_trade_guard is None:
            return StepResult.skipped()

        if ctx.slice_ is None or ctx.account_view is None:
            return StepResult.fail("slice_ and account_view required")

        risk_actions = self._post_trade_guard.scan(ctx.account_view, ctx.slice_)

        # 审计日志: 记录风控扫描结果
        if risk_actions and self._audit_collector is not None:
            self._audit_collector.record_risk_scan(
                ctx.date,
                tuple(
                    RiskScanRecord(
                        trade_date=ctx.date,
                        rule_id=action.rule_id,
                        instrument_id=action.instrument_id,
                        scope=action.scope,
                        severity=action.severity,
                        action_taken=action.action_type,
                        detail=action.detail,
                        current_value=action.current_value,
                        threshold=action.threshold,
                    )
                    for action in risk_actions
                ),
            )

        # 锁定标的 + 发布事件
        for action in risk_actions:
            if (
                action.action_type
                in (RiskActionType.REDUCE_POSITION, RiskActionType.LIQUIDATE)
                and action.scope == RiskScope.INSTRUMENT
                and action.instrument_id is not None
            ):
                self._strategy_context.lock_instrument(
                    action.instrument_id,
                    action.detail,
                    cooldown_until=action.cooldown_until_date,
                )

            # 发布 RiskGuardTriggered 事件
            if self._event_bus is not None:
                self._event_bus.publish(
                    RiskGuardTriggered(
                        rule_name=action.rule_id,
                        severity=action.severity.value,
                        details={"instrument_id": action.instrument_id},
                        timestamp=self._clock.now(),
                    ),
                )

        return StepResult.ok()
