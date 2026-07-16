"""Execution storage DI Provider — 审计服务与交易闭环装配."""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_platform.foundation import SQLiteClient, SQLitePool

from ditto_execution.audit import ExecutionAuditService
from ditto_execution.contracts import (
    AccountDataPort,
    BrokerEventDataPort,
    FillDataPort,
    IntentDataPort,
    PositionDataPort,
)
from ditto_execution.storage.deps import ExecutionReaders, ExecutionWriters
from ditto_execution.storage.sqlite.reconciliation import (
    REPAIR_WORKFLOW_DDL,
    SQLiteRepairWorkflowStore,
)
from ditto_execution.storage.sqlite.trade import (
    ACCOUNT_SNAPSHOTS_DDL,
    BROKER_EVENTS_DDL,
    FILL_ADJUSTMENTS_DDL,
    FILLS_DDL,
    INTENTS_DDL,
    POSITIONS_DDL,
    AccountSnapshotReader,
    AccountSnapshotWriter,
    BrokerEventReader,
    BrokerEventWriter,
    FillAdjustmentReader,
    FillAdjustmentWriter,
    FillReader,
    FillWriter,
    IntentReader,
    IntentWriter,
    PositionReader,
    PositionWriter,
    ensure_position_schema,
)
from ditto_execution.storage.sqlite.trade.service import TradeService

__all__ = ["ExecutionStorageProvider"]


class ExecutionStorageProvider(Provider):
    """执行存储 Provider — 审计服务初始化 + 交易闭环 CRUD 服务."""

    scope = Scope.APP

    # ── 审计服务 ──

    @provide
    def execution_audit_service(self, sqlite_pool: SQLitePool) -> ExecutionAuditService:
        """创建 ExecutionAuditService 并初始化 schema."""
        service = ExecutionAuditService(sqlite_pool)
        service.init_schema()
        return service

    # ── 交易闭环 ──

    @provide
    def execution_sqlite_client(self, sqlite_pool: SQLitePool) -> SQLiteClient:
        """Execution 域 SQLiteClient（独立于 data 域实例）。"""
        return SQLiteClient(sqlite_pool)

    @provide
    def execution_readers(self, sqlite_client: SQLiteClient) -> ExecutionReaders:
        """Execution 域读取依赖聚合."""
        return ExecutionReaders(
            intent=IntentReader(sqlite_client),
            fill=FillReader(sqlite_client),
            position=PositionReader(sqlite_client),
            account=AccountSnapshotReader(sqlite_client),
            broker_event=BrokerEventReader(sqlite_client),
            fill_adjustment=FillAdjustmentReader(sqlite_client),
        )

    @provide
    def execution_writers(self, sqlite_client: SQLiteClient) -> ExecutionWriters:
        """Execution 域写入依赖聚合."""
        return ExecutionWriters(
            intent=IntentWriter(sqlite_client),
            fill=FillWriter(sqlite_client),
            position=PositionWriter(sqlite_client),
            account=AccountSnapshotWriter(sqlite_client),
            broker_event=BrokerEventWriter(sqlite_client),
            fill_adjustment=FillAdjustmentWriter(sqlite_client),
        )

    @provide
    def init_schema(self, sqlite_client: SQLiteClient) -> None:
        """执行 execution 域 DDL（应用级单次初始化）。"""
        sqlite_client.executescript(
            INTENTS_DDL
            + FILLS_DDL
            + FILL_ADJUSTMENTS_DDL
            + POSITIONS_DDL
            + ACCOUNT_SNAPSHOTS_DDL
            + BROKER_EVENTS_DDL
            + REPAIR_WORKFLOW_DDL
        )
        ensure_position_schema(sqlite_client)
        sqlite_client.commit()

    @provide
    def repair_workflow_store(
        self,
        sqlite_client: SQLiteClient,
        _schema_initialized: None,
    ) -> SQLiteRepairWorkflowStore:
        """对账修复审批/执行状态存储."""
        return SQLiteRepairWorkflowStore(sqlite_client)

    @provide
    def trade_service(
        self,
        readers: ExecutionReaders,
        writers: ExecutionWriters,
        sqlite_client: SQLiteClient,
        audit_service: ExecutionAuditService,
        _schema_initialized: None,
    ) -> TradeService:
        """交易信号/成交/持仓 CRUD 服务（内部实例）。"""
        return TradeService(
            readers=readers,
            writers=writers,
            sqlite_client=sqlite_client,
            audit_service=audit_service,
        )

    # ── ISP 窄 Port 暴露 ──

    @provide
    def intent_data_port(self, trade_service: TradeService) -> IntentDataPort:
        """交易意图窄 Port."""
        return trade_service

    @provide
    def fill_data_port(self, trade_service: TradeService) -> FillDataPort:
        """成交窄 Port."""
        return trade_service

    @provide
    def position_data_port(self, trade_service: TradeService) -> PositionDataPort:
        """持仓窄 Port."""
        return trade_service

    @provide
    def account_data_port(self, trade_service: TradeService) -> AccountDataPort:
        """账户基线聚合窄 Port."""
        return trade_service

    @provide
    def broker_event_data_port(
        self,
        trade_service: TradeService,
    ) -> BrokerEventDataPort:
        """券商事件窄 Port."""
        return trade_service
