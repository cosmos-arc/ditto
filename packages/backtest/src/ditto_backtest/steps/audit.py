"""
AuditStep -- 记录 account_view + fills + closed_trades.

对应 EngineLoop._record_step_audit():
  1. 获取最新 account_view
  2. 记录 account_view 到 audit_collector
  3. 记录每个 fill
  4. 通过 trade_builder 匹配成交 -> 记录已平仓交易
"""

from __future__ import annotations

from ditto_execution.brokerage import Brokerage
from ditto_execution.trade_builder import TradeBuilder

from ditto_backtest.audit.collector import ExecutionAuditCollector
from ditto_backtest.steps.types import StepContext, StepResult

__all__ = ["AuditStep"]


class AuditStep:
    """审计记录步骤 -- 记录 account_view + fills + closed_trades."""

    def __init__(
        self,
        audit_collector: ExecutionAuditCollector | None,
        brokerage: Brokerage,
        trade_builder: TradeBuilder,
        recorded_trade_ids: set[str],
    ) -> None:
        self._audit_collector = audit_collector
        self._brokerage = brokerage
        self._trade_builder = trade_builder
        self._recorded_trade_ids = recorded_trade_ids

    def execute(self, ctx: StepContext) -> StepResult:
        """记录审计数据。"""
        if self._audit_collector is None:
            return StepResult.skipped()

        # 获取最新账户快照
        account_view = self._brokerage.get_account()

        # 记录账户快照
        self._audit_collector.record_account_view(ctx.date, account_view)

        # 记录每个 fill + 传给 trade_builder
        for fill in ctx.step_fills:
            self._audit_collector.record_fill(fill)
            self._trade_builder.on_fill(fill, account_view)

        # 记录已平仓交易（去重）
        for trade in self._trade_builder.get_closed_trades():
            if trade.trade_id not in self._recorded_trade_ids:
                self._audit_collector.record_closed_trade(trade)
                self._recorded_trade_ids.add(trade.trade_id)

        return StepResult.ok()
