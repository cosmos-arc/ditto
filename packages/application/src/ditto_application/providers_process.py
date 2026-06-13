"""Process 层 DI Provider — 编排/物化/质量服务注册。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_data.catalog import DataCatalogReader
from ditto_data.config.data_store import DataStoreSettings
from ditto_data.lineage import DataLineageRecorder
from ditto_data.quality import QualityEngine
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_features.compile_cache import SQLiteCompileCache, SQLiteCompileCacheBackend
from ditto_features.services import (
    ArtifactPersistenceService,
    DerivedArtifactReader,
    DerivedCatalogService,
    DerivedShadowSlotService,
    PublicationSafetyRecordService,
    PublicationSafetyRuntimeStores,
)
from ditto_features.storage.runtime.publication_safety import (
    CertificationReader,
    CertificationWriter,
    ManifestReader,
    ManifestWriter,
    MinimalDQReader,
    MinimalDQWriter,
    ShadowReportReader,
    ShadowReportWriter,
)
from ditto_platform.services import AlertManager
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)

from ditto_application.processes.execution.factor_bridge import FactorBridge
from ditto_application.processes.execution.manual_tracker import ManualTracker
from ditto_application.processes.execution.replay_process import ReplayProcess
from ditto_application.processes.execution.strategy_run_process import StrategyFacade
from ditto_application.processes.materialization.cascade_orchestrator import (
    InvalidationCascadeOrchestrator,
)
from ditto_application.processes.materialization.orchestrator import (
    DerivedMaterializationOrchestrator,
    MaterializationRuntimePorts,
    RuntimeDerivedInputProvider,
)
from ditto_application.processes.materialization.publication_facade import (
    DerivedPublicationFacade,
)
from ditto_application.processes.materialization.source_snapshot_resolver import (
    CatalogSourceSnapshotResolver,
    UniverseSourceTickersRequest,
)
from ditto_application.processes.quality import QualityPatrolService
from ditto_application.providers_builder import get_trading_calendar_range
from ditto_application.queries.market import MarketQueryFacade
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_application.queries.run import RunReadModel
from ditto_application.settings import TradingSettings


def _source_tickers_for_universe(
    metadata_service: MetadataService,
    request: UniverseSourceTickersRequest,
) -> tuple[str, ...]:
    return tuple(
        metadata_service.resolve_source_ticker(
            instrument_id=instrument_id,
            source=request.source,
            asof=request.asof,
        )
        for instrument_id in metadata_service.get_universe(
            request.universe_id,
            request.asof,
        )
    )


@dataclass(frozen=True)
class _MaterializationGovernancePorts:
    """Optional governance collaborators for materialization runtime wiring."""

    source_snapshot_resolver: CatalogSourceSnapshotResolver
    universe_provider: MetadataService
    publication_record_service: PublicationSafetyRecordService
    lineage_recorder: DataLineageRecorder


class AppProcessProvider(Provider):
    """App Process 层 DI Provider — 编排/物化/质量服务注册。"""

    scope = Scope.APP

    @provide
    def compile_cache_service(
        self,
        sqlite_client: SQLiteCompileCacheBackend,
    ) -> SQLiteCompileCache:
        """编译缓存服务."""
        return SQLiteCompileCache(sqlite_client)

    @provide
    def derived_input_provider(
        self,
        derived_catalog_service: DerivedCatalogService,
        market_service: MarketService,
        settings: DataStoreSettings,
        data_catalog_reader: DataCatalogReader,
        metadata_service: MetadataService,
    ) -> RuntimeDerivedInputProvider:
        """衍生因子运行时输入提供器."""
        return RuntimeDerivedInputProvider(
            catalog_service=derived_catalog_service,
            market_service=market_service,
            artifact_root=Path(settings.data_root),
            data_catalog_reader=data_catalog_reader,
            catalog_coverage_dates_provider=metadata_service.list_trading_days,
        )

    @provide
    def publication_safety_record_service(
        self,
        settings: DataStoreSettings,
    ) -> PublicationSafetyRecordService:
        """发布安全记录服务."""
        data_root = settings.data_root
        stores = PublicationSafetyRuntimeStores(
            manifest_reader=ManifestReader(base_path=data_root),
            manifest_writer=ManifestWriter(base_path=data_root),
            minimal_dq_reader=MinimalDQReader(base_path=data_root),
            minimal_dq_writer=MinimalDQWriter(base_path=data_root),
            shadow_report_reader=ShadowReportReader(base_path=data_root),
            shadow_report_writer=ShadowReportWriter(base_path=data_root),
            certification_reader=CertificationReader(base_path=data_root),
            certification_writer=CertificationWriter(base_path=data_root),
        )
        return PublicationSafetyRecordService(stores)

    @provide
    def derived_artifact_writer(
        self,
        settings: DataStoreSettings,
    ) -> ArtifactPersistenceService:
        """衍生数据 artifact 持久化服务."""
        return ArtifactPersistenceService(artifact_root=Path(settings.data_root))

    @provide
    def catalog_source_snapshot_resolver(
        self,
        data_catalog_reader: DataCatalogReader,
        metadata_service: MetadataService,
    ) -> CatalogSourceSnapshotResolver:
        """从 DataCatalog 解析物化输入快照."""
        return CatalogSourceSnapshotResolver(
            data_catalog_reader=data_catalog_reader,
            catalog_coverage_dates_provider=metadata_service.list_trading_days,
            universe_source_tickers_provider=lambda request: (
                _source_tickers_for_universe(metadata_service, request)
            ),
        )

    @provide
    def materialization_governance_ports(
        self,
        source_snapshot_resolver: CatalogSourceSnapshotResolver,
        metadata_service: MetadataService,
        publication_record_service: PublicationSafetyRecordService,
        lineage_recorder: DataLineageRecorder,
    ) -> _MaterializationGovernancePorts:
        """衍生物化治理侧运行时 collaborators."""
        return _MaterializationGovernancePorts(
            source_snapshot_resolver=source_snapshot_resolver,
            universe_provider=metadata_service,
            publication_record_service=publication_record_service,
            lineage_recorder=lineage_recorder,
        )

    @provide
    def materialization_runtime_ports(
        self,
        derived_catalog_service: DerivedCatalogService,
        compile_cache_service: SQLiteCompileCache,
        artifact_writer: ArtifactPersistenceService,
        derived_input_provider: RuntimeDerivedInputProvider,
        governance_ports: _MaterializationGovernancePorts,
    ) -> MaterializationRuntimePorts:
        """组装衍生物化编排器运行时 ports."""
        return MaterializationRuntimePorts(
            catalog_service=derived_catalog_service,
            compile_cache_service=compile_cache_service,
            artifact_writer=artifact_writer,
            input_provider=derived_input_provider,
            source_snapshot_resolver=governance_ports.source_snapshot_resolver,
            universe_provider=governance_ports.universe_provider,
            publication_record_service=governance_ports.publication_record_service,
            lineage_recorder=governance_ports.lineage_recorder,
        )

    @provide
    def derived_materialization_orchestrator(
        self,
        ports: MaterializationRuntimePorts,
    ) -> DerivedMaterializationOrchestrator:
        """衍生因子物化编排器."""
        return DerivedMaterializationOrchestrator(ports)

    @provide
    def derived_invalidation_orchestrator(
        self,
        derived_catalog_service: DerivedCatalogService,
        derived_materialization_orchestrator: DerivedMaterializationOrchestrator,
    ) -> InvalidationCascadeOrchestrator:
        """衍生因子失效级联编排器."""
        return InvalidationCascadeOrchestrator(
            catalog_service=derived_catalog_service,
            materialization_service=derived_materialization_orchestrator,
        )

    @provide
    def derived_publication_facade(
        self,
        derived_catalog_service: DerivedCatalogService,
        publication_record_service: PublicationSafetyRecordService,
        shadow_slot_service: DerivedShadowSlotService,
        settings: DataStoreSettings,
    ) -> DerivedPublicationFacade:
        """衍生因子发布门面."""
        return DerivedPublicationFacade(
            catalog_service=derived_catalog_service,
            artifact_reader=DerivedArtifactReader(
                catalog_service=derived_catalog_service,
                artifact_root=Path(settings.data_root),
            ),
            publication_record_service=publication_record_service,
            shadow_slot_service=shadow_slot_service,
        )

    @provide
    def quality_patrol_service(
        self,
        dq_engine: QualityEngine,
        market_facade: MarketQueryFacade,
        metadata_facade: MetadataQueryFacade,
        alert_manager: AlertManager,
    ) -> QualityPatrolService:
        """质量巡检服务."""
        return QualityPatrolService(
            engine=dq_engine,
            market_facade=market_facade,
            metadata_facade=metadata_facade,
            alert_manager=alert_manager,
        )

    @provide
    def manual_tracker(
        self,
        metadata_service: MetadataService,
        trading_settings: TradingSettings,
    ) -> ManualTracker:
        """人工持仓追踪器."""
        start_date, end_date = get_trading_calendar_range(trading_settings)
        trading_days = metadata_service.list_trading_days(start_date, end_date)
        return ManualTracker(trading_calendar=tuple(trading_days))

    @provide
    def replay_process(
        self,
        strategy_facade: StrategyFacade,
        artifact_service: StrategyArtifactService,
        run_model: RunReadModel,
    ) -> ReplayProcess:
        """回测重放流程."""
        return ReplayProcess(
            strategy_facade=strategy_facade,
            artifact_service=artifact_service,
            run_model=run_model,
        )

    @provide
    def factor_bridge(self) -> FactorBridge:
        """因子桥接服务."""
        return FactorBridge()
