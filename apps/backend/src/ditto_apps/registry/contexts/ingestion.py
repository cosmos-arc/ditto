"""摄入上下文工厂。"""

from collections.abc import Generator
from contextlib import contextmanager
from typing import cast

from ditto_application.catalog_freshness import PersistedIngestionEvidenceVerifier
from ditto_application.commands.quality_check import CheckDataQualityHandler
from ditto_application.processes.ingestion.backfill_manager import BackfillManager
from ditto_application.processes.ingestion.bootstrap_planner import BootstrapPlanner
from ditto_application.processes.ingestion.coordinator_factory import (
    CoordinatorRuntimeContext,
    CoordinatorServices,
    create_coordinator,
)
from ditto_application.processes.ingestion.evidence_commit import (
    IngestionEvidenceCommitter,
)
from ditto_application.processes.ingestion.retry_manager import RetryManager
from ditto_application.processes.ingestion.sparse_recovery import (
    SparsePITReattestationProcess,
)
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_data.catalog import (
    DataCatalogReader,
    DataCatalogWriter,
)
from ditto_data.catalog.provider_payload import ProviderPayloadWriter
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.ingestion.ingestion_cursor_store import IngestionCursorStore
from ditto_data.ingestion.ingestion_log_store import IngestionLogStore
from ditto_data.ingestion.partition_state import PartitionLifecycleReader
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.fundamental_store import FundamentalStore
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_service import MarketService
from ditto_data.services.market_write_service import MarketWriteService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.services.source_accessor import SourceAccessor
from ditto_data.sources.exchange_transformers import ExchangeTransformers
from ditto_data.sources.fuyao.source import FuyaoDailyKDumpFetcher
from ditto_data.sources.protocols import MarketFetcher
from ditto_data.sources.registry import SourceRegistry

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.bundle import IngestionBundle


class _MarketFetcherOverrideRegistry:
    """
    组合根单源 MarketFetcher 覆盖（#439 手动回填专用）.

    只覆盖 ``(source, MarketFetcher)`` 一个绑定，其余查询透传底座；
    不参与 source=auto 选源，仅由显式 ``market_fetcher_override`` 注入。
    """

    def __init__(
        self,
        base: SourceRegistry,
        source_name: str,
        fetcher: MarketFetcher | FuyaoDailyKDumpFetcher,
    ) -> None:
        self._base = base
        self._source_name = source_name
        self._fetcher = fetcher

    def get[FetcherT](self, name: str, protocol: type[FetcherT]) -> FetcherT:
        if name == self._source_name and protocol is MarketFetcher:
            # 协议子集实现（与 FuyaoSource 注册同口径），不支持的方法
            # 由数据集白名单前置挡住或以取数错误暴露
            return cast("FetcherT", self._fetcher)
        return self._base.get(name, protocol)


@contextmanager
def create_ingestion_bundle(
    source: str = "tushare",
    *,
    market_fetcher_override: MarketFetcher | FuyaoDailyKDumpFetcher | None = None,
) -> Generator[IngestionBundle]:
    """
    创建摄入上下文组合包（单容器）.

    解决 ARCH-004：替代嵌套的 create_ingestion_context + create_ingestion_log_context，
    确保单个 flow 只创建一个容器实例。

    #394 之后跳过/覆盖/PIT 证据全部消费 completed provider snapshots,
    摄取必须产出快照事实,因此证据 saga 恒开启。

    Args:
        source: 数据源名称。
        market_fetcher_override: 显式覆盖 (source, MarketFetcher) 绑定
            （#439 fuyao dump 手动回填；None = 使用容器注册的真实源）.

    Yields:
        IngestionBundle: 包含协调器、管理器和查询 facade

    Example:
        >>> with create_ingestion_bundle() as bundle:
        ...     result = bundle.coordinator.ingest(...)
        ...     bundle.metadata_facade.is_trading_day(...)

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
        source_registry: SourceRegistry | _MarketFetcherOverrideRegistry = (
            container.get(SourceRegistry)
        )
        if market_fetcher_override is not None:
            source_registry = _MarketFetcherOverrideRegistry(
                source_registry, source, market_fetcher_override
            )
        ingestion_log_store = container.get(IngestionLogStore)
        ingestion_cursor_store = container.get(IngestionCursorStore)
        exchange_transformers = container.get(ExchangeTransformers)
        quality_checker = container.get(CheckDataQualityHandler)
        catalog_reader = container.get(DataCatalogReader)
        catalog_writer = container.get(DataCatalogWriter)
        provider_payload_writer = container.get(ProviderPayloadWriter)
        snapshot_reader = container.get(ProviderSnapshotReader)
        lifecycle_reader = container.get(PartitionLifecycleReader)
        evidence_committer = container.get(IngestionEvidenceCommitter)
        evidence_verifier = PersistedIngestionEvidenceVerifier(
            snapshots=snapshot_reader,
            lifecycle=lifecycle_reader,
            ingestion_logs=ingestion_log_store,
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
                etf_reference_config=source_accessor.etf_reference_config,
            ),
            source_name=source,
            runtime=CoordinatorRuntimeContext(
                ingestion_cursor_store=ingestion_cursor_store,
                quality_checker=quality_checker,
                catalog_reader=catalog_reader,
                catalog_writer=catalog_writer,
                evidence_committer=evidence_committer,
                provider_payload_writer=provider_payload_writer,
                snapshot_reader=snapshot_reader,
                lifecycle_reader=lifecycle_reader,
            ),
        ) as coordinator:
            # 创建管理器
            backfill_manager = BackfillManager(
                coordinator=coordinator,
                metadata_service=metadata_service,
                bootstrap_planner=container.get(BootstrapPlanner),
                snapshot_reader=snapshot_reader,
                lifecycle_reader=lifecycle_reader,
            )
            retry_manager = RetryManager(
                coordinator=coordinator,
                ingestion_log_store=ingestion_log_store,
                source=source,
            )
            sparse_pit_reattestation = SparsePITReattestationProcess(
                ingestion=coordinator,
                snapshots=snapshot_reader,
                lifecycle=lifecycle_reader,
                verifier=evidence_verifier,
            )
            # 创建查询 facade
            metadata_facade = MetadataQueryFacade(metadata_service=metadata_service)

            yield IngestionBundle(
                coordinator=coordinator,
                backfill_manager=backfill_manager,
                retry_manager=retry_manager,
                sparse_pit_reattestation=sparse_pit_reattestation,
                metadata_facade=metadata_facade,
                exchange_transformers=exchange_transformers,
            )
    finally:
        container.close()
