"""
ExecutionAuditCollector — 回测审计数据收集器.

仅负责 recording API + getter API。
计算逻辑在 statistics.py 的模块级函数中。
"""

from __future__ import annotations

from ditto_execution.trade_builder import TradeRecord
from ditto_portfolio.accounting import AccountView, FillEvent

from ditto_backtest.audit.records import (
    PreTradeDecisionRecord,
    RiskScanRecord,
)
from ditto_backtest.audit.state import ExecutionAuditStateSnapshot

__all__ = [
    "ExecutionAuditCollector",
]


class ExecutionAuditCollector:
    """
    回测审计数据收集器.

    在回测运行期间收集 fills、每日账户快照和平仓交易，
    提供 getter 方法供 statistics 模块计算统计指标。

    """

    def __init__(self) -> None:
        self._fills: list[FillEvent] = []
        self._snapshots: list[tuple[str, AccountView]] = []
        self._closed_trades: list[TradeRecord] = []
        self._risk_log: list[RiskScanRecord] = []
        self._pre_trade_log: list[PreTradeDecisionRecord] = []

    # -- recording API -------------------------------------------------------

    def record_fill(self, fill: FillEvent) -> None:
        """记录成交事件。"""
        self._fills.append(fill)

    def record_account_view(self, date: str, account_view: AccountView) -> None:
        """记录每日账户快照。"""
        self._snapshots.append((date, account_view))

    def record_closed_trade(self, trade: TradeRecord) -> None:
        """记录平仓交易。"""
        self._closed_trades.append(trade)

    def record_risk_scan(
        self,
        date: str,
        results: tuple[RiskScanRecord, ...],
    ) -> None:
        """记录 PostTrade 风控扫描结果。"""
        self._risk_log.extend(results)

    def record_pre_trade_decisions(
        self,
        date: str,
        decisions: tuple[PreTradeDecisionRecord, ...],
    ) -> None:
        """记录 PreTrade 订单校验决策。"""
        self._pre_trade_log.extend(decisions)

    # -- checkpoint state API -----------------------------------------------

    def snapshot_state(self) -> ExecutionAuditStateSnapshot:
        """Capture append-only report inputs without mutating the collector."""
        return ExecutionAuditStateSnapshot.capture(
            fills=tuple(self._fills),
            daily_snapshots=tuple(self._snapshots),
            closed_trades=tuple(self._closed_trades),
            risk_log=tuple(self._risk_log),
            pre_trade_log=tuple(self._pre_trade_log),
        )

    def restore_state(self, snapshot: ExecutionAuditStateSnapshot) -> None:
        """Restore history into a pristine collector before execution starts."""
        if any(
            (
                self._fills,
                self._snapshots,
                self._closed_trades,
                self._risk_log,
                self._pre_trade_log,
            )
        ):
            raise ValueError("execution audit collector must be pristine on restore")
        self._fills.extend(snapshot.fills)
        self._snapshots.extend(snapshot.to_daily_snapshots())
        self._closed_trades.extend(snapshot.closed_trades)
        self._risk_log.extend(snapshot.risk_log)
        self._pre_trade_log.extend(snapshot.pre_trade_log)

    # -- getter API ----------------------------------------------------------

    def get_fills(self) -> tuple[FillEvent, ...]:
        """返回所有已记录的成交事件。"""
        return tuple(self._fills)

    def get_daily_snapshots(self) -> tuple[tuple[str, AccountView], ...]:
        """返回所有已记录的每日账户快照。"""
        return tuple(self._snapshots)

    def get_closed_trades(self) -> tuple[TradeRecord, ...]:
        """返回所有已记录的平仓交易。"""
        return tuple(self._closed_trades)

    def get_risk_log(self) -> tuple[RiskScanRecord, ...]:
        """返回所有已记录的风控扫描记录。"""
        return tuple(self._risk_log)

    def get_pre_trade_log(self) -> tuple[PreTradeDecisionRecord, ...]:
        """返回所有已记录的 PreTrade 决策记录。"""
        return tuple(self._pre_trade_log)
