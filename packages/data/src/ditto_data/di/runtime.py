"""Data 层 - Runtime Layer Provider。"""

from __future__ import annotations

from collections.abc import Iterator
from importlib.resources import files
from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_infra.foundation import SQLitePool
from ditto_infra.foundation.concurrency import FileLockManager

from ditto_data.config.data_store import DataStoreSettings
from ditto_data.ingestion.publication_safety_record_service import (
    PublicationSafetyRuntimeStores,
)
from ditto_data.runtime.freeze_manager import FreezeManager
from ditto_data.runtime.instrument_id_allocator import InstrumentIdAllocator
from ditto_data.runtime.sql_engine import SqlEngine
from ditto_data.services import (
    DerivedCatalogService,
    DerivedShadowSlotService,
    FreezeService,
    IngestionCursorService,
    IngestionLogService,
    PublicationSafetyRecordService,
    QualityRecordService,
    ResearchCatalogService,
)
from ditto_data.services.audit import ExecutionAuditService
from ditto_data.services.source_service import SourceService
from ditto_data.services.strategy.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_data.services.strategy.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_data.services.strategy.strategy_run_service import (
    StrategyRunService,
    StrategyRunWriterProtocol,
)
from ditto_data.sources.source import DataSources
from ditto_data.storage.metadata import (
    SQLiteStrategyArtifactReader,
    SQLiteStrategyArtifactWriter,
    SQLiteStrategyRunReader,
    SQLiteStrategyRunWriter,
    SQLiteStrategySpecReader,
    SQLiteStrategySpecWriter,
)
from ditto_data.storage.runtime.derived_sqlite import (
    SQLiteDerivedCatalogReader,
    SQLiteDerivedCatalogWriter,
)
from ditto_data.storage.runtime.ingestion import (
    IngestionCursorReader,
    IngestionCursorWriter,
    IngestionLogReader,
    IngestionLogWriter,
)
from ditto_data.storage.runtime.publication_safety import (
    CertificationReader,
    CertificationWriter,
    ManifestReader,
    ManifestWriter,
    MinimalDQReader,
    MinimalDQWriter,
    ShadowReportReader,
    ShadowReportWriter,
)
from ditto_data.storage.runtime.publication_shadow_sqlite import (
    SQLiteDerivedShadowSlotReader,
    SQLiteDerivedShadowSlotWriter,
)
from ditto_data.storage.runtime.quality import (
    ComparisonReader,
    ComparisonWriter,
    QuarantineReader,
    QuarantineWriter,
)
from ditto_data.storage.runtime.research_sqlite import (
    SQLiteResearchCatalogReader,
    SQLiteResearchCatalogWriter,
)
from ditto_data.storage.sqlite_client import SQLiteClient

__all__ = ["RuntimeProvider"]


class RuntimeProvider(Provider):
    """Runtime Layer Provider - 基础设施和运行时服务."""

    scope = Scope.APP

    # ========================================================================
    # SQLite 基础设施
    # ========================================================================

    @provide
    def sqlite_pool(
        self,
        settings: DataStoreSettings,
    ) -> Iterator[SQLitePool]:
        """SQLite 连接池（应用级单例）."""
        db_path = settings.resolved_sqlite_path
        db_path.parent.mkdir(parents=True, exist_ok=True)

        schema_traversable = files("ditto_data.scripts") / "schema.sql"
        schema_path = Path(str(schema_traversable))
        pool = SQLitePool(str(db_path), schema_path=schema_path)
        pool.init_schema()
        yield pool
        pool.close()

    @provide
    def sqlite_client(self, sqlite_pool: SQLitePool) -> SQLiteClient:
        """SQLite 客户端（基于全局连接池）."""
        return SQLiteClient(sqlite_pool)

    @provide
    def instrument_id_allocator(self, sqlite_pool: SQLitePool) -> InstrumentIdAllocator:
        """Instrument ID 分配器."""
        return InstrumentIdAllocator(sqlite_pool)

    @provide
    def freeze_manager(self, settings: DataStoreSettings) -> FreezeManager:
        """数据版本管理."""
        return FreezeManager(data_root=str(settings.data_root))

    @provide
    def freeze_service(self, freeze_manager: FreezeManager) -> FreezeService:
        """数据版本管理服务."""
        return FreezeService(freeze_manager=freeze_manager)

    @provide
    def execution_audit_service(self, sqlite_pool: SQLitePool) -> ExecutionAuditService:
        """执行审计日志服务（自动初始化 schema）。"""
        service = ExecutionAuditService(sqlite_pool)
        service.init_schema()
        return service

    @provide
    def file_lock(self, settings: DataStoreSettings) -> FileLockManager:
        """文件锁管理器."""
        lock_dir = settings.data_root / "locks"
        return FileLockManager(lock_dir)

    # ========================================================================
    # Runtime Domain CQRS Readers and Writers
    # ========================================================================

    @provide
    def ingestion_log_reader(self, sqlite_client: SQLiteClient) -> IngestionLogReader:
        """摄取日志读取器."""
        return IngestionLogReader(sqlite_client)

    @provide
    def ingestion_log_writer(self, sqlite_client: SQLiteClient) -> IngestionLogWriter:
        """摄取日志写入器."""
        return IngestionLogWriter(sqlite_client)

    @provide
    def derived_catalog_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> SQLiteDerivedCatalogReader:
        """统一派生 catalog 读取器."""
        return SQLiteDerivedCatalogReader(sqlite_client)

    @provide
    def derived_catalog_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> SQLiteDerivedCatalogWriter:
        """统一派生 catalog 写入器."""
        return SQLiteDerivedCatalogWriter(sqlite_client)

    @provide
    def research_catalog_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> SQLiteResearchCatalogReader:
        """Research 控制面读取器."""
        return SQLiteResearchCatalogReader(sqlite_client)

    @provide
    def research_catalog_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> SQLiteResearchCatalogWriter:
        """Research 控制面写入器."""
        return SQLiteResearchCatalogWriter(sqlite_client)

    @provide
    def strategy_spec_reader(self, sqlite_pool: SQLitePool) -> SQLiteStrategySpecReader:
        """策略目录控制面读取器."""
        return SQLiteStrategySpecReader(sqlite_pool)

    @provide
    def strategy_spec_writer(self, sqlite_pool: SQLitePool) -> SQLiteStrategySpecWriter:
        """策略目录控制面写入器."""
        return SQLiteStrategySpecWriter(sqlite_pool)

    @provide
    def strategy_artifact_reader(
        self,
        sqlite_pool: SQLitePool,
    ) -> SQLiteStrategyArtifactReader:
        """策略产物控制面读取器."""
        return SQLiteStrategyArtifactReader(sqlite_pool)

    @provide
    def strategy_artifact_writer(
        self,
        sqlite_pool: SQLitePool,
    ) -> SQLiteStrategyArtifactWriter:
        """策略产物控制面写入器."""
        return SQLiteStrategyArtifactWriter(sqlite_pool)

    @provide
    def strategy_run_reader(self, sqlite_pool: SQLitePool) -> SQLiteStrategyRunReader:
        """策略运行控制面读取器."""
        return SQLiteStrategyRunReader(sqlite_pool)

    @provide
    def strategy_run_writer(
        self,
        sqlite_pool: SQLitePool,
    ) -> StrategyRunWriterProtocol:
        """策略运行控制面写入器."""
        return SQLiteStrategyRunWriter(sqlite_pool)

    @provide
    def comparison_reader(self, settings: DataStoreSettings) -> ComparisonReader:
        """质量对比数据读取器."""
        return ComparisonReader(base_path=settings.data_root)

    @provide
    def comparison_writer(self, settings: DataStoreSettings) -> ComparisonWriter:
        """质量对比数据写入器."""
        return ComparisonWriter(base_path=settings.data_root)

    @provide
    def quarantine_reader(self, sqlite_client: SQLiteClient) -> QuarantineReader:
        """隔离区数据读取器."""
        return QuarantineReader(sqlite_client)

    @provide
    def quarantine_writer(self, sqlite_client: SQLiteClient) -> QuarantineWriter:
        """隔离区数据写入器."""
        return QuarantineWriter(sqlite_client)

    @provide
    def manifest_reader(self, settings: DataStoreSettings) -> ManifestReader:
        """发布兼容 manifest 读取器."""
        return ManifestReader(base_path=settings.data_root)

    @provide
    def manifest_writer(self, settings: DataStoreSettings) -> ManifestWriter:
        """发布兼容 manifest 写入器."""
        return ManifestWriter(base_path=settings.data_root)

    @provide
    def minimal_dq_reader(self, settings: DataStoreSettings) -> MinimalDQReader:
        """Minimal DQ 摘要读取器."""
        return MinimalDQReader(base_path=settings.data_root)

    @provide
    def minimal_dq_writer(self, settings: DataStoreSettings) -> MinimalDQWriter:
        """Minimal DQ 摘要写入器."""
        return MinimalDQWriter(base_path=settings.data_root)

    @provide
    def shadow_report_reader(self, settings: DataStoreSettings) -> ShadowReportReader:
        """Shadow diff / trace 读取器."""
        return ShadowReportReader(base_path=settings.data_root)

    @provide
    def shadow_report_writer(self, settings: DataStoreSettings) -> ShadowReportWriter:
        """Shadow diff / trace 写入器."""
        return ShadowReportWriter(base_path=settings.data_root)

    @provide
    def certification_reader(self, settings: DataStoreSettings) -> CertificationReader:
        """认证报告读取器."""
        return CertificationReader(base_path=settings.data_root)

    @provide
    def certification_writer(self, settings: DataStoreSettings) -> CertificationWriter:
        """认证报告写入器."""
        return CertificationWriter(base_path=settings.data_root)

    @provide
    def derived_shadow_slot_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> SQLiteDerivedShadowSlotReader:
        """Shadow slot 控制面读取器."""
        return SQLiteDerivedShadowSlotReader(sqlite_client)

    @provide
    def derived_shadow_slot_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> SQLiteDerivedShadowSlotWriter:
        """Shadow slot 控制面写入器."""
        return SQLiteDerivedShadowSlotWriter(sqlite_client)

    # ========================================================================
    # Runtime Services
    # ========================================================================

    @provide
    def ingestion_log_service(
        self,
        ingestion_log_reader: IngestionLogReader,
        ingestion_log_writer: IngestionLogWriter,
    ) -> IngestionLogService:
        """数据摄入日志服务."""
        return IngestionLogService(ingestion_log_reader, ingestion_log_writer)

    @provide
    def ingestion_cursor_reader(
        self, sqlite_client: SQLiteClient
    ) -> IngestionCursorReader:
        """摄取游标读取器."""
        return IngestionCursorReader(sqlite_client)

    @provide
    def ingestion_cursor_writer(
        self, sqlite_client: SQLiteClient
    ) -> IngestionCursorWriter:
        """摄取游标写入器."""
        return IngestionCursorWriter(sqlite_client)

    @provide
    def ingestion_cursor_service(
        self,
        ingestion_cursor_reader: IngestionCursorReader,
        ingestion_cursor_writer: IngestionCursorWriter,
    ) -> IngestionCursorService:
        """数据摄入游标服务."""
        return IngestionCursorService(ingestion_cursor_reader, ingestion_cursor_writer)

    @provide
    def derived_catalog_service(
        self,
        derived_catalog_reader: SQLiteDerivedCatalogReader,
        derived_catalog_writer: SQLiteDerivedCatalogWriter,
    ) -> DerivedCatalogService:
        """统一派生 catalog 记录服务."""
        return DerivedCatalogService(
            catalog_reader=derived_catalog_reader,
            catalog_writer=derived_catalog_writer,
        )

    @provide
    def research_catalog_service(
        self,
        research_catalog_reader: SQLiteResearchCatalogReader,
        research_catalog_writer: SQLiteResearchCatalogWriter,
    ) -> ResearchCatalogService:
        """Research 控制面元数据服务."""
        return ResearchCatalogService(
            catalog_reader=research_catalog_reader,
            catalog_writer=research_catalog_writer,
        )

    @provide
    def strategy_catalog_service(
        self,
        strategy_spec_reader: SQLiteStrategySpecReader,
        strategy_spec_writer: SQLiteStrategySpecWriter,
    ) -> StrategyCatalogService:
        """策略目录服务."""
        return StrategyCatalogService(
            reader=strategy_spec_reader,
            writer=strategy_spec_writer,
        )

    @provide
    def strategy_artifact_service(
        self,
        strategy_artifact_reader: SQLiteStrategyArtifactReader,
        strategy_artifact_writer: SQLiteStrategyArtifactWriter,
    ) -> StrategyArtifactService:
        """策略产物服务."""
        return StrategyArtifactService(
            reader=strategy_artifact_reader,
            writer=strategy_artifact_writer,
        )

    @provide
    def strategy_run_service(
        self,
        strategy_run_reader: SQLiteStrategyRunReader,
        strategy_run_writer: StrategyRunWriterProtocol,
    ) -> StrategyRunService:
        """策略运行生命周期服务."""
        return StrategyRunService(
            reader=strategy_run_reader,
            writer=strategy_run_writer,
        )

    @provide
    def quality_record_service(
        self,
        comparison_reader: ComparisonReader,
        comparison_writer: ComparisonWriter,
        quarantine_reader: QuarantineReader,
        quarantine_writer: QuarantineWriter,
    ) -> QualityRecordService:
        """质量记录服务."""
        return QualityRecordService(
            comparison_reader,
            comparison_writer,
            quarantine_reader,
            quarantine_writer,
        )

    @provide
    def publication_safety_record_service(
        self,
        publication_safety_runtime_stores: PublicationSafetyRuntimeStores,
    ) -> PublicationSafetyRecordService:
        """发布安全记录服务."""
        return PublicationSafetyRecordService(publication_safety_runtime_stores)

    @provide
    def publication_safety_runtime_stores(
        self,
        settings: DataStoreSettings,
    ) -> PublicationSafetyRuntimeStores:
        """发布安全运行时 stores 组合包."""
        data_root = settings.data_root
        return PublicationSafetyRuntimeStores(
            manifest_reader=ManifestReader(base_path=data_root),
            manifest_writer=ManifestWriter(base_path=data_root),
            minimal_dq_reader=MinimalDQReader(base_path=data_root),
            minimal_dq_writer=MinimalDQWriter(base_path=data_root),
            shadow_report_reader=ShadowReportReader(base_path=data_root),
            shadow_report_writer=ShadowReportWriter(base_path=data_root),
            certification_reader=CertificationReader(base_path=data_root),
            certification_writer=CertificationWriter(base_path=data_root),
        )

    @provide
    def derived_shadow_slot_service(
        self,
        derived_shadow_slot_reader: SQLiteDerivedShadowSlotReader,
        derived_shadow_slot_writer: SQLiteDerivedShadowSlotWriter,
    ) -> DerivedShadowSlotService:
        """Shadow slot 控制面服务."""
        return DerivedShadowSlotService(
            slot_reader=derived_shadow_slot_reader,
            slot_writer=derived_shadow_slot_writer,
        )

    @provide
    def source_service(self, sources: DataSources) -> SourceService:
        """外部数据源访问服务."""
        return SourceService(sources)

    # ========================================================================
    # SQL Engine
    # ========================================================================

    @provide
    def sql_engine(
        self,
        settings: DataStoreSettings,
    ) -> SqlEngine:
        """DuckDB SQL 引擎."""
        return SqlEngine(settings=settings)
