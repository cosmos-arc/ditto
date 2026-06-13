"""Data 层 - Runtime Layer Provider。"""

from __future__ import annotations

from collections.abc import Iterator
from importlib.resources import files
from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_platform.foundation import (
    FileLockManager,
    SQLiteClient,
    SQLitePool,
)

from ditto_data.catalog.contracts import DataCatalogReader, DataCatalogWriter
from ditto_data.catalog.fallback_policy import (
    CatalogSourceFallbackPolicyReader,
    CatalogSourceFallbackPolicyWriter,
)
from ditto_data.catalog.fallback_policy_store import (
    SQLiteCatalogSourceFallbackPolicyStore,
)
from ditto_data.catalog.promotion import (
    DatasetMaturityPromotionHistoryReader,
    DatasetMaturityPromotionReader,
    DatasetMaturityPromotionRevoker,
    DatasetMaturityPromotionWriter,
    DatasetPromotionEvidenceReader,
    DatasetPromotionEvidenceWriter,
)
from ditto_data.catalog.promotion_store import (
    SQLiteDatasetMaturityPromotionStore,
    SQLiteDatasetPromotionEvidenceStore,
)
from ditto_data.catalog.remediation import (
    CatalogRemediationApprovalReader,
    CatalogRemediationApprovalWriter,
)
from ditto_data.catalog.remediation_store import SQLiteCatalogRemediationApprovalStore
from ditto_data.catalog.sqlite_store import SQLiteDataCatalog
from ditto_data.config.data_store import DataStoreSettings
from ditto_data.ingestion.freeze_store import (
    FreezeStore,
)
from ditto_data.ingestion.ingestion_cursor_store import (
    IngestionCursorStore,
)
from ditto_data.ingestion.ingestion_log_store import (
    IngestionLogStore,
)
from ditto_data.ingestion.quality_record_store import (
    QualityRecordStore,
)
from ditto_data.lineage import DataLineageReader, DataLineageRecorder
from ditto_data.lineage.sqlite_store import SQLiteDataLineage
from ditto_data.runtime.freeze_manager import FreezeManager
from ditto_data.runtime.instrument_id_allocator import InstrumentIdAllocator
from ditto_data.runtime.sql_engine import SqlEngine
from ditto_data.services.source_accessor import SourceAccessor
from ditto_data.sources.source import DataSources
from ditto_data.storage.runtime.ingestion import (
    IngestionCursorReader,
    IngestionCursorWriter,
    IngestionLogReader,
    IngestionLogWriter,
)
from ditto_data.storage.runtime.quality import (
    ComparisonReader,
    ComparisonWriter,
    QuarantineReader,
    QuarantineWriter,
)

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
    def data_catalog_store(self, sqlite_client: SQLiteClient) -> SQLiteDataCatalog:
        """SQLite 数据目录存储（应用级共享实例）."""
        return SQLiteDataCatalog(sqlite_client)

    @provide
    def data_catalog_writer(
        self,
        data_catalog_store: SQLiteDataCatalog,
    ) -> DataCatalogWriter:
        """DataCatalog 写入端口."""
        return data_catalog_store

    @provide
    def data_catalog_reader(
        self,
        data_catalog_store: SQLiteDataCatalog,
    ) -> DataCatalogReader:
        """DataCatalog 读取端口."""
        return data_catalog_store

    @provide
    def dataset_promotion_evidence_store(
        self,
        sqlite_client: SQLiteClient,
    ) -> SQLiteDatasetPromotionEvidenceStore:
        """SQLite dataset promotion evidence store."""
        return SQLiteDatasetPromotionEvidenceStore(sqlite_client)

    @provide
    def dataset_promotion_evidence_writer(
        self,
        dataset_promotion_evidence_store: SQLiteDatasetPromotionEvidenceStore,
    ) -> DatasetPromotionEvidenceWriter:
        """Dataset promotion evidence write port."""
        return dataset_promotion_evidence_store

    @provide
    def dataset_promotion_evidence_reader(
        self,
        dataset_promotion_evidence_store: SQLiteDatasetPromotionEvidenceStore,
    ) -> DatasetPromotionEvidenceReader:
        """Dataset promotion evidence read port."""
        return dataset_promotion_evidence_store

    @provide
    def dataset_maturity_promotion_store(
        self,
        sqlite_client: SQLiteClient,
    ) -> SQLiteDatasetMaturityPromotionStore:
        """SQLite dataset maturity promotion override store."""
        return SQLiteDatasetMaturityPromotionStore(sqlite_client)

    @provide
    def dataset_maturity_promotion_writer(
        self,
        dataset_maturity_promotion_store: SQLiteDatasetMaturityPromotionStore,
    ) -> DatasetMaturityPromotionWriter:
        """Dataset maturity promotion write port."""
        return dataset_maturity_promotion_store

    @provide
    def dataset_maturity_promotion_reader(
        self,
        dataset_maturity_promotion_store: SQLiteDatasetMaturityPromotionStore,
    ) -> DatasetMaturityPromotionReader:
        """Dataset maturity promotion read port."""
        return dataset_maturity_promotion_store

    @provide
    def dataset_maturity_promotion_history_reader(
        self,
        dataset_maturity_promotion_store: SQLiteDatasetMaturityPromotionStore,
    ) -> DatasetMaturityPromotionHistoryReader:
        """Dataset maturity promotion history read port."""
        return dataset_maturity_promotion_store

    @provide
    def dataset_maturity_promotion_revoker(
        self,
        dataset_maturity_promotion_store: SQLiteDatasetMaturityPromotionStore,
    ) -> DatasetMaturityPromotionRevoker:
        """Dataset maturity promotion revoke port."""
        return dataset_maturity_promotion_store

    @provide
    def catalog_remediation_approval_store(
        self,
        sqlite_client: SQLiteClient,
    ) -> SQLiteCatalogRemediationApprovalStore:
        """SQLite catalog remediation approval state store."""
        return SQLiteCatalogRemediationApprovalStore(sqlite_client)

    @provide
    def catalog_remediation_approval_writer(
        self,
        catalog_remediation_approval_store: SQLiteCatalogRemediationApprovalStore,
    ) -> CatalogRemediationApprovalWriter:
        """Catalog remediation approval write port."""
        return catalog_remediation_approval_store

    @provide
    def catalog_remediation_approval_reader(
        self,
        catalog_remediation_approval_store: SQLiteCatalogRemediationApprovalStore,
    ) -> CatalogRemediationApprovalReader:
        """Catalog remediation approval read port."""
        return catalog_remediation_approval_store

    @provide
    def catalog_source_fallback_policy_store(
        self,
        sqlite_client: SQLiteClient,
    ) -> SQLiteCatalogSourceFallbackPolicyStore:
        """SQLite catalog source fallback policy state store."""
        return SQLiteCatalogSourceFallbackPolicyStore(sqlite_client)

    @provide
    def catalog_source_fallback_policy_writer(
        self,
        catalog_source_fallback_policy_store: SQLiteCatalogSourceFallbackPolicyStore,
    ) -> CatalogSourceFallbackPolicyWriter:
        """Catalog source fallback policy write port."""
        return catalog_source_fallback_policy_store

    @provide
    def catalog_source_fallback_policy_reader(
        self,
        catalog_source_fallback_policy_store: SQLiteCatalogSourceFallbackPolicyStore,
    ) -> CatalogSourceFallbackPolicyReader:
        """Catalog source fallback policy read port."""
        return catalog_source_fallback_policy_store

    @provide
    def data_lineage_store(self, sqlite_client: SQLiteClient) -> SQLiteDataLineage:
        """SQLite 血缘存储（应用级共享实例）."""
        return SQLiteDataLineage(sqlite_client)

    @provide
    def data_lineage_recorder(
        self,
        data_lineage_store: SQLiteDataLineage,
    ) -> DataLineageRecorder:
        """血缘写入端口."""
        return data_lineage_store

    @provide
    def data_lineage_reader(
        self,
        data_lineage_store: SQLiteDataLineage,
    ) -> DataLineageReader:
        """血缘读取端口."""
        return data_lineage_store

    @provide
    def instrument_id_allocator(self, sqlite_pool: SQLitePool) -> InstrumentIdAllocator:
        """Instrument ID 分配器."""
        return InstrumentIdAllocator(sqlite_pool)

    @provide
    def freeze_manager(self, settings: DataStoreSettings) -> FreezeManager:
        """数据版本管理."""
        return FreezeManager(data_root=str(settings.data_root))

    @provide
    def freeze_store(self, freeze_manager: FreezeManager) -> FreezeStore:
        """数据版本管理服务."""
        return FreezeStore(freeze_manager=freeze_manager)

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

    # ========================================================================
    # Runtime Services
    # ========================================================================

    @provide
    def ingestion_log_store(
        self,
        ingestion_log_reader: IngestionLogReader,
        ingestion_log_writer: IngestionLogWriter,
    ) -> IngestionLogStore:
        """数据摄入日志服务."""
        return IngestionLogStore(ingestion_log_reader, ingestion_log_writer)

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
    def ingestion_cursor_store(
        self,
        ingestion_cursor_reader: IngestionCursorReader,
        ingestion_cursor_writer: IngestionCursorWriter,
    ) -> IngestionCursorStore:
        """数据摄入游标服务."""
        return IngestionCursorStore(ingestion_cursor_reader, ingestion_cursor_writer)

    @provide
    def quality_record_store(
        self,
        comparison_reader: ComparisonReader,
        comparison_writer: ComparisonWriter,
        quarantine_reader: QuarantineReader,
        quarantine_writer: QuarantineWriter,
    ) -> QualityRecordStore:
        """质量记录服务."""
        return QualityRecordStore(
            comparison_reader,
            comparison_writer,
            quarantine_reader,
            quarantine_writer,
        )

    @provide
    def source_accessor(self, sources: DataSources) -> SourceAccessor:
        """外部数据源访问服务."""
        return SourceAccessor(sources)

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
