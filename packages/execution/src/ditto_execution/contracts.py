"""Execution domain contracts — Protocol definitions for execution consumers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ditto_execution.audit.models import (
    PreTradeDecisionPayload,
    RiskScanPayload,
    TradeFillPayload,
)
from ditto_execution.models import FillRecord, SignalRecord

__all__ = ["FillReceiver", "OrderRouter", "TradeAuditor"]


@runtime_checkable
class OrderRouter(Protocol):
    """订单路由接口 — 将交易意图持久化为信号记录."""

    def save_intent(self, record: SignalRecord) -> None:
        """持久化交易意图信号."""
        ...


@runtime_checkable
class FillReceiver(Protocol):
    """成交通知接口 — 接收并持久化成交记录."""

    def save_fill(self, record: FillRecord) -> None:
        """持久化成交通知记录."""
        ...


@runtime_checkable
class TradeAuditor(Protocol):
    """交易审计接口 — 记录执行审计日志."""

    def save_risk_log(self, run_id: str, records: Sequence[RiskScanPayload]) -> int:
        """保存风控扫描审计日志."""
        ...

    def save_pre_trade_log(
        self,
        run_id: str,
        records: Sequence[PreTradeDecisionPayload],
    ) -> int:
        """保存盘前决策审计日志."""
        ...

    def save_trade_fill_log(
        self,
        run_id: str,
        records: Sequence[TradeFillPayload],
    ) -> int:
        """保存成交审计日志."""
        ...
