"""Execution storage DI Provider — 审计服务与交易闭环装配."""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_platform.foundation import SQLiteClient, SQLitePool

from ditto_execution.audit import ExecutionAuditService
from ditto_execution.contracts import (
    FillDataPort,
    IntentDataPort,
    PositionDataPort,
)
from ditto_execution.storage.deps import ExecutionReaders, ExecutionWriters
from ditto_execution.storage.sqlite.trade import (
    FILLS_DDL,
    INTENTS_DDL,
    POSITIONS_DDL,
    FillReader,
    FillWriter,
    IntentReader,
    IntentWriter,
    PositionReader,
    PositionWriter,
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
        )

    @provide
    def execution_writers(self, sqlite_client: SQLiteClient) -> ExecutionWriters:
        """Execution 域写入依赖聚合."""
        return ExecutionWriters(
            intent=IntentWriter(sqlite_client),
            fill=FillWriter(sqlite_client),
            position=PositionWriter(sqlite_client),
        )

    @provide
    def init_schema(self, sqlite_client: SQLiteClient) -> None:
        """执行 execution 域 DDL（应用级单次初始化）。"""
        sqlite_client.executescript(INTENTS_DDL + FILLS_DDL + POSITIONS_DDL)
        sqlite_client.commit()

    @provide
    def trade_service(
        self,
        readers: ExecutionReaders,
        writers: ExecutionWriters,
        _schema_initialized: None,
    ) -> TradeService:
        """交易信号/成交/持仓 CRUD 服务（内部实例）。"""
        return TradeService(readers=readers, writers=writers)

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
