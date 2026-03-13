"""DataHub 层 - Runtime Layer Provider。"""

from __future__ import annotations

from collections.abc import Iterator
from importlib.resources import files
from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_datahub.config.data_store import DataStoreSettings
from ditto_datahub.runtime.freeze_manager import FreezeManager
from ditto_datahub.runtime.instrument_id_allocator import InstrumentIdAllocator
from ditto_datahub.runtime.sql_engine import SqlEngine
from ditto_datahub.services import (
    IngestionLogService,
    PublicationSafetyRecordService,
    QualityRecordService,
)
from ditto_datahub.services.source_service import SourceService
from ditto_datahub.sources.source import DataSources
from ditto_datahub.stores.runtime.ingestion import (
    IngestionLogReader,
    IngestionLogWriter,
)
from ditto_datahub.stores.runtime.publication_safety import (
    CertificationReader,
    CertificationWriter,
    ManifestReader,
    ManifestWriter,
    ShadowReportReader,
    ShadowReportWriter,
)
from ditto_datahub.stores.runtime.quality import (
    ComparisonReader,
    ComparisonWriter,
    QuarantineReader,
    QuarantineWriter,
)
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_infra.foundation import SQLitePool
from ditto_infra.foundation.concurrency import FileLockManager

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

        schema_traversable = files("ditto_datahub.scripts") / "schema.sql"
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
        manifest_reader: ManifestReader,
        manifest_writer: ManifestWriter,
        shadow_report_reader: ShadowReportReader,
        shadow_report_writer: ShadowReportWriter,
        certification_reader: CertificationReader,
        certification_writer: CertificationWriter,
    ) -> PublicationSafetyRecordService:
        """发布安全记录服务."""
        return PublicationSafetyRecordService(
            manifest_reader=manifest_reader,
            manifest_writer=manifest_writer,
            shadow_report_reader=shadow_report_reader,
            shadow_report_writer=shadow_report_writer,
            certification_reader=certification_reader,
            certification_writer=certification_writer,
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
