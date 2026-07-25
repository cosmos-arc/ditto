"""Process 层 DI Provider — 编排/物化/质量服务注册。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_analysis.experiments import (
    ExperimentReaderProtocol,
    ExperimentWriterProtocol,
)
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_data.catalog import DataCatalogReader, DataCatalogWriter
from ditto_data.catalog.certification import (
    CertificationReader as DataProductCertificationReader,
)
from ditto_data.catalog.license import DatasetLicenseReader
from ditto_data.catalog.promotion import DatasetMaturityPromotionReader
from ditto_data.catalog.source_snapshot import ProviderSnapshotWriter
from ditto_data.config.data_source import DataSourceSettings
from ditto_data.config.data_store import DataStoreSettings
from ditto_data.ingestion.ingestion_log_store import IngestionLogStore
from ditto_data.ingestion.partition_state import (
    PartitionLifecycleReader,
    PartitionLifecycleWriter,
)
from ditto_data.lineage import DataLineageRecorder
from ditto_data.quality import QualityEngine
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_execution.contracts import FillDataPort, IntentDataPort, PositionDataPort
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
from ditto_strategy.governance.service import GovernanceService
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)

from ditto_application.builders.published_baseline_runtime_builder import (
    PublishedBaselineRuntimeBuilder,
)
from ditto_application.builders.research_executor_probe import (
    BuilderBackedResearchExecutorProbe as _BuilderBackedResearchExecutorProbe,
)
from ditto_application.builders.research_runtime_builder import (
    ResearchRuntimeBuilder,
)
from ditto_application.builders.research_validation_authority import (
    ProductionResearchValidationAuthorityProbe as _ValidationAuthorityProbe,
)
from ditto_application.catalog_freshness import PersistedIngestionEvidenceVerifier
from ditto_application.commands.experiments import ExperimentControlNotifier
from ditto_application.processes.execution.factor_bridge import FactorBridge
from ditto_application.processes.execution.manual_sizing import (
    AShareTradeDateResolver,
    ManualSizingContextBuilder,
    ManualSizingService,
)
from ditto_application.processes.execution.manual_tracker import ManualTracker
from ditto_application.processes.execution.position_reader import StoredPositionReader
from ditto_application.processes.execution.replay_process import (
    IndexedResearchReplayArtifactReader,
    ReplayProcess,
    VerifiedReplayArtifactReader,
)
from ditto_application.processes.execution.signal_package import SignalPackagePublisher
from ditto_application.processes.execution.signal_snapshot import SignalSnapshotProcess
from ditto_application.processes.execution.strategy_run_process import StrategyFacade
from ditto_application.processes.experiments._control_runtime import (
    CONTROL_COORDINATOR_LEASE_DURATION,
    CONTROL_COORDINATOR_OWNER_TOKEN,
    ControlOnlyFirstAttemptFactory,
    LoggingExperimentControlNotifier,
)
from ditto_application.processes.experiments.coordinator import (
    ExperimentExecutionCoordinator,
)
from ditto_application.processes.experiments.planning_process import (
    ExperimentPlanningProcess,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStore,
)
from ditto_application.processes.ingestion.bootstrap_planner import BootstrapPlanner
from ditto_application.processes.ingestion.evidence_commit import (
    EvidenceCommitPorts,
    IngestionEvidenceCommitter,
)
from ditto_application.processes.ingestion.r2_preflight import (
    R2AcceptanceRuntimeEvidence,
)
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
from ditto_application.processes.quality import (
    QualityBatchCoordinator,
    QualityCompletenessService,
    QualityPatrolService,
)
from ditto_application.processes.strategy.promotion import StrategyPromotionProcess
from ditto_application.providers_builder import get_trading_calendar_range
from ditto_application.queries.account import AccountBaselineQuery
from ditto_application.queries.data_readiness import (
    DataReadinessQueryFacade,
)
from ditto_application.queries.market import MarketQueryFacade
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_application.queries.research_certification import (
    DataReadinessCertificationProbe as _DataReadinessCertificationProbe,
)
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
    def bootstrap_planner(
        self,
        metadata_service: MetadataService,
        partition_lifecycle_reader: PartitionLifecycleReader,
    ) -> BootstrapPlanner:
        """Build resumable R2 chunks behind the application composition boundary."""
        return BootstrapPlanner(
            metadata_service=metadata_service,
            partition_lifecycle_reader=partition_lifecycle_reader,
        )

    @provide
    def ingestion_evidence_committer(
        self,
        partition_lifecycle_reader: PartitionLifecycleReader,
        partition_lifecycle_writer: PartitionLifecycleWriter,
        provider_snapshot_writer: ProviderSnapshotWriter,
        dataset_license_reader: DatasetLicenseReader,
        data_catalog_writer: DataCatalogWriter,
        lineage_recorder: DataLineageRecorder,
        ingestion_log_store: IngestionLogStore,
    ) -> IngestionEvidenceCommitter:
        """Assemble the fail-closed R2 evidence saga from application ports."""
        return IngestionEvidenceCommitter(
            ports=EvidenceCommitPorts(
                lifecycle_reader=partition_lifecycle_reader,
                lifecycle_writer=partition_lifecycle_writer,
                snapshot_writer=provider_snapshot_writer,
                license_reader=dataset_license_reader,
                catalog_writer=data_catalog_writer,
                lineage_recorder=lineage_recorder,
                ingestion_log_store=ingestion_log_store,
            )
        )

    @provide
    def r2_acceptance_runtime_evidence(
        self,
        settings: DataSourceSettings,
        license_reader: DatasetLicenseReader,
    ) -> R2AcceptanceRuntimeEvidence:
        """Resolve non-secret live acceptance inputs at the composition boundary."""
        credential_sources: set[str] = set()
        if settings.tushare_token.strip():
            credential_sources.add("tushare")
        if settings.fred_api_key.strip():
            credential_sources.update({"fred", "alfred"})
        if Path(settings.tdx_path).expanduser().is_dir():
            credential_sources.add("local_tdx")
        return R2AcceptanceRuntimeEvidence(
            credential_sources=frozenset(credential_sources),
            license_records=license_reader.list_licenses(),
        )

    @provide
    def data_readiness_query_facade(
        self,
        certification_reader: DataProductCertificationReader,
        maturity_promotion_reader: DatasetMaturityPromotionReader,
    ) -> DataReadinessQueryFacade:
        """R2 consumer readiness query with certification and maturity gates."""
        return DataReadinessQueryFacade(
            certification_reader=certification_reader,
            maturity_promotion_reader=maturity_promotion_reader,
        )

    @provide
    def research_certification_probe(
        self,
        facade: DataReadinessQueryFacade,
        research_catalog: ResearchCatalogService,
    ) -> _DataReadinessCertificationProbe:
        """Bind R3 preflight to the fixed R2 certification read model."""
        return _DataReadinessCertificationProbe(facade, research_catalog)

    @provide
    def research_executor_probe(
        self,
        builder: ResearchRuntimeBuilder,
        published_baseline_builder: PublishedBaselineRuntimeBuilder,
        strategy_catalog: StrategyCatalogService,
    ) -> _BuilderBackedResearchExecutorProbe:
        """Validate every candidate against the explicit-version runtime builder."""
        return _BuilderBackedResearchExecutorProbe(
            builder,
            published_baseline_builder=published_baseline_builder,
            strategy_reader=strategy_catalog,
        )

    @provide
    def research_validation_authority_probe(
        self,
    ) -> _ValidationAuthorityProbe:
        """Bind planning to the production fail-closed validation authority."""
        return _ValidationAuthorityProbe()

    @provide
    def experiment_planning_process(
        self,
        reader: ExperimentReaderProtocol,
        writer: ExperimentWriterProtocol,
        certification_probe: _DataReadinessCertificationProbe,
        executor_probe: _BuilderBackedResearchExecutorProbe,
        authority_probe: _ValidationAuthorityProbe,
    ) -> ExperimentPlanningProcess:
        """Assemble deterministic preflight and exact launch persistence ports."""
        return ExperimentPlanningProcess(
            reader=reader,
            writer=writer,
            certification_probe=certification_probe,
            executor_probe=executor_probe,
            authority_probe=authority_probe,
        )

    @provide
    def experiment_scheduler_store(
        self,
        reader: ExperimentReaderProtocol,
        writer: ExperimentWriterProtocol,
    ) -> ExperimentSchedulerStore:
        """Bind Task 9 scheduling to the approved durable experiment ports."""
        return ExperimentSchedulerStore(reader, writer)

    @provide
    def experiment_control_notifier(self) -> ExperimentControlNotifier:
        """R3 best-effort logging notifier for the single-machine durable-tick model."""
        return LoggingExperimentControlNotifier()

    @provide
    def experiment_execution_coordinator(
        self,
        store: ExperimentSchedulerStore,
    ) -> ExperimentExecutionCoordinator:
        """
        Wire the R3 control-only coordinator.

        Control routes (pause/cancel/resume/retry-fold) never dispatch attempts;
        the placeholder factory fails loudly if tick dispatch is ever connected
        through this instance. Replace the factory when the execution bundle
        resolver (Task 9/13) is assembled.
        """
        return ExperimentExecutionCoordinator(
            store=store,
            first_attempt_factory=ControlOnlyFirstAttemptFactory(),
            owner_token=CONTROL_COORDINATOR_OWNER_TOKEN,
            lease_duration=CONTROL_COORDINATOR_LEASE_DURATION,
        )

    @provide
    def persisted_ingestion_evidence_verifier(
        self,
        data_catalog_reader: DataCatalogReader,
        ingestion_log_store: IngestionLogStore,
    ) -> PersistedIngestionEvidenceVerifier:
        """Bind DQ outcomes to durable catalog and ingestion-log facts."""
        return PersistedIngestionEvidenceVerifier(
            reader=data_catalog_reader,
            ingestion_logs=ingestion_log_store,
        )

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
    def quality_batch_coordinator(
        self,
        quality_patrol_service: QualityPatrolService,
        metadata_facade: MetadataQueryFacade,
        evidence_verifier: PersistedIngestionEvidenceVerifier,
        alert_manager: AlertManager,
    ) -> QualityBatchCoordinator:
        """Quality batch application coordinator."""
        return QualityBatchCoordinator(
            patrol=quality_patrol_service,
            metadata=metadata_facade,
            evidence_verifier=evidence_verifier,
            alert_manager=alert_manager,
        )

    @provide
    def quality_completeness_service(
        self,
        market_facade: MarketQueryFacade,
    ) -> QualityCompletenessService:
        """Market instrument completeness process."""
        return QualityCompletenessService(market=market_facade)

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
    def stored_position_reader(
        self,
        position_port: PositionDataPort,
    ) -> StoredPositionReader:
        """Stored position adapter for signal package generation."""
        return StoredPositionReader(position_port=position_port)

    @provide
    def signal_snapshot_process(
        self,
        position_reader: StoredPositionReader,
        sizing_service: ManualSizingService,
    ) -> SignalSnapshotProcess:
        """Signal snapshot process using stored manual positions."""
        return SignalSnapshotProcess(
            position_reader=position_reader,
            sizing_service=sizing_service,
        )

    @provide
    def manual_sizing_service(self) -> ManualSizingService:
        """A 股人工交易建议数量服务。"""
        return ManualSizingService()

    @provide
    def manual_sizing_context_builder(
        self,
        account_query: AccountBaselineQuery,
        market_query: MarketQueryFacade,
    ) -> ManualSizingContextBuilder:
        """显式账户基线与 D 日收盘价的 sizing context builder。"""
        return ManualSizingContextBuilder(
            account_query=account_query,
            market_query=market_query,
        )

    @provide
    def a_share_trade_date_resolver(
        self,
        metadata_service: MetadataService,
        trading_settings: TradingSettings,
    ) -> AShareTradeDateResolver:
        """基于正式 A 股交易日历解析建议交易日。"""
        start_date, end_date = get_trading_calendar_range(trading_settings)
        return AShareTradeDateResolver(
            trading_days=tuple(metadata_service.list_trading_days(start_date, end_date))
        )

    @provide
    def signal_package_publisher(
        self,
        snapshot_process: SignalSnapshotProcess,
        intent_port: IntentDataPort,
        fill_port: FillDataPort,
        date_resolver: AShareTradeDateResolver,
        artifact_service: StrategyArtifactService,
    ) -> SignalPackagePublisher:
        """Signal package publisher backed by execution intent storage."""
        return SignalPackagePublisher(
            snapshot_process=snapshot_process,
            intent_port=intent_port,
            fill_port=fill_port,
            date_resolver=date_resolver,
            artifact_service=artifact_service,
        )

    @provide
    def verified_replay_artifact_reader(
        self,
        strategy_artifact_service: StrategyArtifactService,
        experiment_reader: ExperimentReaderProtocol,
        research_artifact_service: ResearchArtifactService,
    ) -> VerifiedReplayArtifactReader:
        """Bind R3 replay to Schema v1 metadata and verified artifact reads."""
        return IndexedResearchReplayArtifactReader(
            strategy_artifact_service=strategy_artifact_service,
            artifact_index_reader=experiment_reader,
            artifact_content_reader=research_artifact_service,
        )

    @provide
    def replay_process(
        self,
        strategy_facade: StrategyFacade,
        artifact_service: StrategyArtifactService,
        run_model: RunReadModel,
        verified_artifact_reader: VerifiedReplayArtifactReader,
    ) -> ReplayProcess:
        """回测重放流程."""
        return ReplayProcess(
            strategy_facade=strategy_facade,
            artifact_service=artifact_service,
            run_model=run_model,
            verified_artifact_reader=verified_artifact_reader,
        )

    @provide
    def strategy_promotion_process(
        self,
        governance_service: GovernanceService,
    ) -> StrategyPromotionProcess:
        """R3 策略 promotion 流程（evidence-gated publish + activate）."""
        return StrategyPromotionProcess(governance_service)

    @provide
    def factor_bridge(self) -> FactorBridge:
        """因子桥接服务."""
        return FactorBridge()
