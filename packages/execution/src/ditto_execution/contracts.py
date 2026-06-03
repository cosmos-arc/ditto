"""Execution domain contracts — Protocol definitions for execution consumers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ditto_execution.audit.models import (
    PreTradeDecisionPayload,
    RepairExecutionPayload,
    RiskDecisionPayload,
    RiskScanPayload,
    TradeFillPayload,
)
from ditto_execution.models import (
    BrokerEventRecord,
    FillRecord,
    PositionRecord,
    SignalRecord,
)

__all__ = [
    "BrokerEventDataPort",
    "FillDataPort",
    "IntentDataPort",
    "OrderRouter",
    "PositionDataPort",
    "TradeAuditor",
]


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

    def save_risk_decision(
        self,
        run_id: str,
        records: tuple[RiskDecisionPayload, ...],
    ) -> int:
        """保存风控决策审计记录（accept/reject/modify）."""
        ...

    def save_repair_execution_log(
        self,
        run_id: str,
        records: tuple[RepairExecutionPayload, ...],
    ) -> int:
        """保存对账修复执行审计记录."""
        ...


# ---------------------------------------------------------------------------
# ISP 窄 Port — 按聚合边界拆分交易数据访问
# ---------------------------------------------------------------------------


class IntentDataPort(Protocol):
    """交易意图窄 Port — 信号 CRUD + 状态变更."""

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
        """更新交易信号状态."""
        ...


class FillDataPort(Protocol):
    """成交窄 Port — 成交 CRUD."""

    def save_fill(self, record: FillRecord) -> None:
        """保存成交记录."""
        ...

    def find_fill(self, intent_id: str, trade_date: str) -> FillRecord | None:
        """按 intent_id + trade_date 查找成交记录."""
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


class PositionDataPort(Protocol):
    """持仓窄 Port — 持仓快照读写."""

    def save_position(self, record: PositionRecord) -> None:
        """保存持仓快照."""
        ...

    def list_positions(
        self,
        strategy_id: str,
        snapshot_date: str | None = None,
        run_id: str | None = None,
    ) -> list[PositionRecord]:
        """按条件查询持仓快照列表."""
        ...


class BrokerEventDataPort(Protocol):
    """券商事件窄 Port — 标准化 broker gateway event CRUD."""

    def save_broker_event(self, record: BrokerEventRecord) -> None:
        """保存标准化券商事件."""
        ...

    def list_broker_events(
        self,
        run_id: str,
        *,
        event_type: str | None = None,
        order_id: str | None = None,
        broker_order_id: str | None = None,
        fill_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[BrokerEventRecord]:
        """按运行、事件类型、关联键和日期查询标准化券商事件."""
        ...
