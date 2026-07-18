"""摄入上下文工厂。"""

from collections.abc import Generator
from contextlib import contextmanager

from ditto_application.catalog_freshness import PersistedIngestionEvidenceVerifier
from ditto_application.commands.data_product_certification import (
    DataProductCertificationCommands,
)
from ditto_application.commands.quality_check import CheckDataQualityHandler
from ditto_application.processes.ingestion.backfill_manager import BackfillManager
from ditto_application.processes.ingestion.bootstrap_planner import BootstrapPlanner
from ditto_application.processes.ingestion.coordinator_factory import (
    CoordinatorRuntimeContext,
    CoordinatorServices,
    create_coordinator,
)
from ditto_application.processes.ingestion.evidence_commit import (
    EvidenceCommitPorts,
    IngestionEvidenceCommitter,
)
from ditto_application.processes.ingestion.retry_manager import RetryManager
from ditto_application.processes.ingestion.sparse_recovery import (
    SparsePITReattestationProcess,
)
from ditto_application.queries.data_products import DataProductsQueryFacade
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_data.catalog import (
    DataCatalogReader,
    DataCatalogWriter,
    DatasetLicenseReader,
    ProviderSnapshotWriter,
)
from ditto_data.catalog.fallback_policy import CatalogSourceFallbackPolicyReader
from ditto_data.ingestion.freeze_store import FreezeStore
from ditto_data.ingestion.ingestion_cursor_store import IngestionCursorStore
from ditto_data.ingestion.ingestion_log_store import IngestionLogStore
from ditto_data.ingestion.partition_state import (
    PartitionLifecycleReader,
    PartitionLifecycleWriter,
)
from ditto_data.lineage import DataLineageRecorder
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.fundamental_store import FundamentalStore
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_service import MarketService
from ditto_data.services.market_write_service import MarketWriteService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.services.source_accessor import SourceAccessor
from ditto_data.sources.exchange_transformers import ExchangeTransformers
from ditto_data.sources.registry import SourceRegistry

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.bundle import IngestionBundle


@contextmanager
def create_ingestion_bundle(
    source: str = "tushare",
    *,
    license_record_id: str | None = None,
) -> Generator[IngestionBundle]:
    """
    创建摄入上下文组合包（单容器）.

    解决 ARCH-004：替代嵌套的 create_ingestion_context + create_ingestion_log_context，
    确保单个 flow 只创建一个容器实例。

    Args:
        source: 数据源名称
        license_record_id: 启用 R2 fail-closed 证据模式的已审核许可记录 ID。

    Yields:
        IngestionBundle: 包含协调器、管理器和查询 facade

    Example:
        with create_ingestion_bundle() as bundle:
            result = bundle.coordinator.ingest(...)
            bundle.metadata_facade.is_trading_day(...)

    """
    container = make_app_container()
    try:
        # 获取所有服务
        metadata_service = container.get(MetadataService)
        market_service = container.get(MarketService)
        market_write_service = container.get(MarketWriteService)
        fundamental_store = container.get(FundamentalStore)
        capital_store = container.get(CapitalStore)
        macro_service = container.get(MacroService)
        source_accessor = container.get(SourceAccessor)
        source_registry = container.get(SourceRegistry)
        ingestion_log_store = container.get(IngestionLogStore)
        ingestion_cursor_store = container.get(IngestionCursorStore)
        exchange_transformers = container.get(ExchangeTransformers)
        quality_checker = container.get(CheckDataQualityHandler)
        freeze_store = container.get(FreezeStore)
        lineage_recorder = container.get(DataLineageRecorder)
        catalog_reader = container.get(DataCatalogReader)
        catalog_writer = container.get(DataCatalogWriter)
        source_fallback_policy_reader = container.get(CatalogSourceFallbackPolicyReader)
        partition_lifecycle_reader = container.get(PartitionLifecycleReader)
        evidence_committer: IngestionEvidenceCommitter | None = None
        if license_record_id is not None:
            evidence_committer = IngestionEvidenceCommitter(
                ports=EvidenceCommitPorts(
                    lifecycle_reader=partition_lifecycle_reader,
                    lifecycle_writer=container.get(PartitionLifecycleWriter),
                    snapshot_writer=container.get(ProviderSnapshotWriter),
                    license_reader=container.get(DatasetLicenseReader),
                    catalog_writer=catalog_writer,
                    lineage_recorder=lineage_recorder,
                    ingestion_log_store=ingestion_log_store,
                )
            )

        # 创建协调器
        with create_coordinator(
            CoordinatorServices(
                metadata_service=metadata_service,
                market_service=market_service,
                market_write_service=market_write_service,
                fundamental_store=fundamental_store,
                capital_store=capital_store,
                macro_service=macro_service,
                source_accessor=source_accessor,
                ingestion_log_store=ingestion_log_store,
                source_registry=source_registry,
            ),
            source_name=source,
            runtime=CoordinatorRuntimeContext(
                ingestion_cursor_store=ingestion_cursor_store,
                quality_checker=quality_checker,
                freeze_store=freeze_store,
                lineage_recorder=lineage_recorder,
                catalog_reader=catalog_reader,
                catalog_writer=catalog_writer,
                source_fallback_policy_reader=source_fallback_policy_reader,
                evidence_committer=evidence_committer,
                license_record_id=license_record_id,
            ),
        ) as coordinator:
            # 创建管理器
            backfill_manager = BackfillManager(
                coordinator=coordinator,
                metadata_service=metadata_service,
                ingestion_log_store=ingestion_log_store,
                bootstrap_planner=BootstrapPlanner(
                    metadata_service=metadata_service,
                    partition_lifecycle_reader=partition_lifecycle_reader,
                ),
                evidence_verifier=PersistedIngestionEvidenceVerifier(
                    reader=catalog_reader,
                    ingestion_logs=ingestion_log_store,
                ),
            )
            retry_manager = RetryManager(
                coordinator=coordinator,
                ingestion_log_store=ingestion_log_store,
                source=source,
                data_catalog_reader=catalog_reader,
            )
            sparse_pit_reattestation = SparsePITReattestationProcess(
                ingestion=coordinator,
                catalog=catalog_reader,
                verifier=PersistedIngestionEvidenceVerifier(
                    reader=catalog_reader,
                    ingestion_logs=ingestion_log_store,
                ),
            )
            # 创建查询 facade
            metadata_facade = MetadataQueryFacade(metadata_service=metadata_service)
            data_products_query = container.get(DataProductsQueryFacade)
            certification_commands = container.get(DataProductCertificationCommands)

            yield IngestionBundle(
                coordinator=coordinator,
                backfill_manager=backfill_manager,
                retry_manager=retry_manager,
                sparse_pit_reattestation=sparse_pit_reattestation,
                metadata_facade=metadata_facade,
                exchange_transformers=exchange_transformers,
                data_products_query=data_products_query,
                certification_commands=certification_commands,
            )
    finally:
        container.close()
