"""Execution domain contracts — Protocol definitions for execution consumers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ditto_execution.audit.models import (
    PreTradeDecisionPayload,
    RiskScanPayload,
    TradeFillPayload,
)
from ditto_execution.models import FillRecord, PositionRecord, SignalRecord

__all__ = ["OrderRouter", "TradeAuditor", "TradeDataPort"]


@runtime_checkable
class OrderRouter(Protocol):
    """订单路由接口 — 将交易意图持久化为信号记录."""

    def save_intent(self, record: SignalRecord) -> None:
        """持久化交易意图信号."""
        ...


@runtime_checkable
class TradeAuditor(Protocol):
    """交易审计接口 — 记录执行审计日志."""

    def save_risk_log(self, run_id: str, records: tuple[RiskScanPayload, ...]) -> int:
        """保存风控扫描审计日志."""
        ...

    def save_pre_trade_log(
        self,
        run_id: str,
        records: tuple[PreTradeDecisionPayload, ...],
    ) -> int:
        """保存盘前决策审计日志."""
        ...

    def save_trade_fill_log(
        self,
        run_id: str,
        records: tuple[TradeFillPayload, ...],
    ) -> int:
        """保存成交审计日志."""
        ...


class TradeDataPort(Protocol):
    """
    交易数据端口 — Application 层与 Execution 存储的解耦契约.

    覆盖 Application 层（queries/commands/providers）所需的全部公开方法，
    消除 application 对 execution.storage.sqlite 的直接依赖。
    TradeService 是本 Protocol 的唯一实现。
    """

    # -- Intent CRUD --

    def save_intent(self, record: SignalRecord) -> None:
        """保存交易信号记录."""
        ...

    def get_intent(self, intent_id: str) -> SignalRecord | None:
        """按 intent_id 查询单条交易信号."""
        ...

    def list_intents(
        self,
        strategy_id: str,
        signal_date: str | None = None,
        status: str | None = None,
    ) -> list[SignalRecord]:
        """按条件查询交易信号列表."""
        ...

    def update_intent_status(
        self,
        intent_id: str,
        status: str,
        *,
        expected_current: tuple[str, ...],
    ) -> bool:
        """更新交易信号状态（expected_current 用于 TOCTOU 防护）。"""
        ...

    # -- Fill CRUD --

    def save_fill(self, record: FillRecord) -> None:
        """保存成交记录."""
        ...

    def find_fill(self, intent_id: str, trade_date: str) -> FillRecord | None:
        """按 intent_id + trade_date 查找成交记录（幂等去重用）。"""
        ...

    def list_fills(
        self,
        strategy_id: str,
        trade_date: str | None = None,
        intent_id: str | None = None,
        end_date: str | None = None,
    ) -> list[FillRecord]:
        """按条件查询成交记录列表."""
        ...

    # -- Position CRUD --

    def save_position(self, record: PositionRecord) -> None:
        """保存持仓快照."""
        ...

    def list_positions(
        self,
        strategy_id: str,
        snapshot_date: str | None = None,
    ) -> list[PositionRecord]:
        """按条件查询持仓快照列表."""
        ...
