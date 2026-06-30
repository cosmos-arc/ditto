"""Strategy storage DI Provider — 策略存储读写与服务装配."""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_platform.foundation import SQLitePool

from ditto_strategy.contracts import StrategyCatalogReader
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunCheckpointStore,
    StrategyRunCheckpointWriterProtocol,
    StrategyRunLifecycleStore,
    StrategyRunWriterProtocol,
)
from ditto_strategy.storage.sqlite.strategy_artifact_store import (
    SQLiteStrategyArtifactReader,
    SQLiteStrategyArtifactWriter,
)
from ditto_strategy.storage.sqlite.strategy_run_store import (
    SQLiteStrategyRunCheckpointReader,
    SQLiteStrategyRunCheckpointWriter,
    SQLiteStrategyRunReader,
    SQLiteStrategyRunWriter,
)
from ditto_strategy.storage.sqlite.strategy_spec_store import (
    SQLiteStrategySpecReader,
    SQLiteStrategySpecWriter,
)

__all__ = ["StrategyStorageProvider"]


class StrategyStorageProvider(Provider):
    """策略存储 Provider — SQLite 读写器与域服务装配."""

    scope = Scope.APP

    @provide
    def strategy_spec_reader(
        self,
        sqlite_pool: SQLitePool,
    ) -> SQLiteStrategySpecReader:
        """提供策略规格读取器."""
        return SQLiteStrategySpecReader(sqlite_pool)

    @provide
    def strategy_spec_writer(
        self,
        sqlite_pool: SQLitePool,
    ) -> SQLiteStrategySpecWriter:
        """提供策略规格写入器."""
        return SQLiteStrategySpecWriter(sqlite_pool)

    @provide
    def strategy_artifact_reader(
        self,
        sqlite_pool: SQLitePool,
    ) -> SQLiteStrategyArtifactReader:
        """提供策略工件读取器."""
        return SQLiteStrategyArtifactReader(sqlite_pool)

    @provide
    def strategy_artifact_writer(
        self,
        sqlite_pool: SQLitePool,
    ) -> SQLiteStrategyArtifactWriter:
        """提供策略工件写入器."""
        return SQLiteStrategyArtifactWriter(sqlite_pool)

    @provide
    def strategy_run_reader(
        self,
        sqlite_pool: SQLitePool,
    ) -> SQLiteStrategyRunReader:
        """提供策略运行读取器."""
        SQLiteStrategyRunWriter(sqlite_pool).init_schema()
        return SQLiteStrategyRunReader(sqlite_pool)

    @provide
    def strategy_run_checkpoint_reader(
        self,
        sqlite_pool: SQLitePool,
    ) -> SQLiteStrategyRunCheckpointReader:
        """提供策略运行 checkpoint 读取器."""
        SQLiteStrategyRunCheckpointWriter(sqlite_pool).init_schema()
        return SQLiteStrategyRunCheckpointReader(sqlite_pool)

    @provide
    def strategy_run_writer(
        self,
        sqlite_pool: SQLitePool,
    ) -> StrategyRunWriterProtocol:
        """提供策略运行写入器."""
        writer = SQLiteStrategyRunWriter(sqlite_pool)
        writer.init_schema()
        return writer

    @provide
    def strategy_run_checkpoint_writer(
        self,
        sqlite_pool: SQLitePool,
    ) -> StrategyRunCheckpointWriterProtocol:
        """提供策略运行 checkpoint 写入器."""
        writer = SQLiteStrategyRunCheckpointWriter(sqlite_pool)
        writer.init_schema()
        return writer

    @provide
    def strategy_catalog_service(
        self,
        strategy_spec_reader: SQLiteStrategySpecReader,
        strategy_spec_writer: SQLiteStrategySpecWriter,
    ) -> StrategyCatalogService:
        """提供策略目录服务."""
        return StrategyCatalogService(
            reader=strategy_spec_reader,
            writer=strategy_spec_writer,
        )

    @provide
    def strategy_catalog_reader(
        self,
        catalog_service: StrategyCatalogService,
    ) -> StrategyCatalogReader:
        """将 StrategyCatalogService 注册为 StrategyCatalogReader Protocol."""
        return catalog_service

    @provide
    def strategy_artifact_service(
        self,
        strategy_artifact_reader: SQLiteStrategyArtifactReader,
        strategy_artifact_writer: SQLiteStrategyArtifactWriter,
    ) -> StrategyArtifactService:
        """提供策略工件服务."""
        return StrategyArtifactService(
            reader=strategy_artifact_reader,
            writer=strategy_artifact_writer,
        )

    @provide
    def strategy_run_service(
        self,
        strategy_run_reader: SQLiteStrategyRunReader,
        strategy_run_writer: StrategyRunWriterProtocol,
    ) -> StrategyRunLifecycleStore:
        """提供策略运行服务."""
        return StrategyRunLifecycleStore(
            reader=strategy_run_reader,
            writer=strategy_run_writer,
        )

    @provide
    def strategy_run_checkpoint_store(
        self,
        strategy_run_checkpoint_reader: SQLiteStrategyRunCheckpointReader,
        strategy_run_checkpoint_writer: StrategyRunCheckpointWriterProtocol,
    ) -> StrategyRunCheckpointStore:
        """提供策略运行 checkpoint 服务."""
        return StrategyRunCheckpointStore(
            reader=strategy_run_checkpoint_reader,
            writer=strategy_run_checkpoint_writer,
        )
