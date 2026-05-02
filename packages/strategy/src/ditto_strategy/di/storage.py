"""Strategy storage DI Provider — 策略存储读写与服务装配."""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_platform.foundation import SQLitePool

from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunLifecycleStore,
    StrategyRunWriterProtocol,
)
from ditto_strategy.storage.sqlite.strategy_artifact_store import (
    SQLiteStrategyArtifactReader,
    SQLiteStrategyArtifactWriter,
)
from ditto_strategy.storage.sqlite.strategy_run_store import (
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
    def strategy_spec_reader(  # noqa: D102
        self,
        sqlite_pool: SQLitePool,
    ) -> SQLiteStrategySpecReader:
        return SQLiteStrategySpecReader(sqlite_pool)

    @provide
    def strategy_spec_writer(  # noqa: D102
        self,
        sqlite_pool: SQLitePool,
    ) -> SQLiteStrategySpecWriter:
        return SQLiteStrategySpecWriter(sqlite_pool)

    @provide
    def strategy_artifact_reader(  # noqa: D102
        self,
        sqlite_pool: SQLitePool,
    ) -> SQLiteStrategyArtifactReader:
        return SQLiteStrategyArtifactReader(sqlite_pool)

    @provide
    def strategy_artifact_writer(  # noqa: D102
        self,
        sqlite_pool: SQLitePool,
    ) -> SQLiteStrategyArtifactWriter:
        return SQLiteStrategyArtifactWriter(sqlite_pool)

    @provide
    def strategy_run_reader(  # noqa: D102
        self,
        sqlite_pool: SQLitePool,
    ) -> SQLiteStrategyRunReader:
        return SQLiteStrategyRunReader(sqlite_pool)

    @provide
    def strategy_run_writer(  # noqa: D102
        self,
        sqlite_pool: SQLitePool,
    ) -> StrategyRunWriterProtocol:
        return SQLiteStrategyRunWriter(sqlite_pool)

    @provide
    def strategy_catalog_service(  # noqa: D102
        self,
        strategy_spec_reader: SQLiteStrategySpecReader,
        strategy_spec_writer: SQLiteStrategySpecWriter,
    ) -> StrategyCatalogService:
        return StrategyCatalogService(
            reader=strategy_spec_reader,
            writer=strategy_spec_writer,
        )

    @provide
    def strategy_artifact_service(  # noqa: D102
        self,
        strategy_artifact_reader: SQLiteStrategyArtifactReader,
        strategy_artifact_writer: SQLiteStrategyArtifactWriter,
    ) -> StrategyArtifactService:
        return StrategyArtifactService(
            reader=strategy_artifact_reader,
            writer=strategy_artifact_writer,
        )

    @provide
    def strategy_run_service(  # noqa: D102
        self,
        strategy_run_reader: SQLiteStrategyRunReader,
        strategy_run_writer: StrategyRunWriterProtocol,
    ) -> StrategyRunLifecycleStore:
        return StrategyRunLifecycleStore(
            reader=strategy_run_reader,
            writer=strategy_run_writer,
        )
