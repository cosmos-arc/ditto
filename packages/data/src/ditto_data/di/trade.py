"""Trade DI Provider — 交易闭环 CRUD 服务注册."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from ditto_data.services.deps import ExecutionReaders, ExecutionWriters
from ditto_data.services.trade import TradeService
from ditto_data.storage.execution import (
    FILLS_DDL,
    INTENTS_DDL,
    POSITIONS_DDL,
    FillReader,
    FillWriter,
    PositionReader,
    PositionWriter,
    SignalReader,
    SignalWriter,
)
from ditto_data.storage.sqlite_client import SQLiteClient

__all__ = ["TradeProvider"]


class TradeProvider(Provider):
    """交易闭环服务的 Data 层 DI 注册."""

    scope = Scope.APP

    @provide
    def execution_readers(self, sqlite_client: SQLiteClient) -> ExecutionReaders:
        """Execution 域读取依赖聚合."""
        return ExecutionReaders(
            signal=SignalReader(sqlite_client),
            fill=FillReader(sqlite_client),
            position=PositionReader(sqlite_client),
        )

    @provide
    def execution_writers(self, sqlite_client: SQLiteClient) -> ExecutionWriters:
        """Execution 域写入依赖聚合."""
        return ExecutionWriters(
            signal=SignalWriter(sqlite_client),
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
        """交易信号/成交/持仓 CRUD 服务."""
        return TradeService(readers=readers, writers=writers)
