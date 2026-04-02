"""
App 层 DI Provider — 应用编排服务注册。

三个 Provider 按职责分离，对应 R8 互斥规则：
- AppQueryProvider: 只读查询服务（query 模块）
- AppProcessProvider: 编排/物化/质量服务（process 模块）
- AppBuilderFactory: 策略运行时装配服务（builders 模块）
"""

from __future__ import annotations

from pathlib import Path

from dishka import Provider, Scope, provide

# ---------------------------------------------------------------------------
# DataHub 层依赖（由更底层的 Provider 注册，此处仅声明类型）
# ---------------------------------------------------------------------------
from ditto_analytics.compile_cache import SQLiteCompileCache
from ditto_data.config.data_store import DataStoreSettings
from ditto_data.quality import QualityEngine
from ditto_data.services import (
    DerivedArtifactReader,
    DerivedCatalogService,
    DerivedQueryService,
    DerivedShadowSlotService,
    PublicationSafetyRecordService,
    ResearchCatalogService,
)
from ditto_data.services.audit import ExecutionAuditService
from ditto_data.services.derived.artifact_persistence_service import (
    ArtifactPersistenceService,
)
from ditto_data.services.hot_layer import UnavailableHotLayerReader
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.services.research_artifact_service import ResearchArtifactService
from ditto_data.services.strategy.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_data.services.strategy.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_data.services.strategy.strategy_run_service import (
    StrategyRunService as StrategyRunLifecycleService,
)

# ---------------------------------------------------------------------------
# App Builder 层
# ---------------------------------------------------------------------------
from ditto_app.builders.strategy import (
    BacktestRuntimeBuilder,
    StrategyRuntimeBuilder,
    StrategyServiceFactory,
    StrategySliceBuilder,
)

# ---------------------------------------------------------------------------
# App Process 层
# ---------------------------------------------------------------------------
from ditto_app.process.materialization import (
    DerivedMaterializationOrchestrator,
    DerivedPublicationFacade,
    InvalidationCascadeOrchestrator,
    RuntimeDerivedInputProvider,
)
from ditto_app.process.quality import QualityService
from ditto_app.process.strategy import StrategyFacade

# ---------------------------------------------------------------------------
# App Query 层
# ---------------------------------------------------------------------------
from ditto_app.query.derived import (
    DerivedQueryFacade,
    StaticRuntimeModeResolver,
)
from ditto_app.query.research import ResearchDatasetFacade

__all__ = [
    "AppBuilderFactory",
    "AppProcessProvider",
    "AppQueryProvider",
    "get_app_providers",
]


# ---------------------------------------------------------------------------
# AppQueryProvider — 只读查询服务
# ---------------------------------------------------------------------------


class AppQueryProvider(Provider):
    """App Query 层 DI Provider — 只读查询服务注册。"""

    scope = Scope.APP

    @provide
    def runtime_mode_resolver(self) -> StaticRuntimeModeResolver:
        """Static runtime mode resolver for Phase 2 contract wiring."""
        return StaticRuntimeModeResolver()

    @provide
    def derived_query_facade(
        self,
        derived_query_service: DerivedQueryService,
        runtime_mode_resolver: StaticRuntimeModeResolver,
    ) -> DerivedQueryFacade:
        """Derived query use-case facade."""
        return DerivedQueryFacade(
            service=derived_query_service,
            mode_resolver=runtime_mode_resolver,
            hot_layer=UnavailableHotLayerReader(),
        )

    @provide
    def research_dataset_facade(
        self,
        metadata_service: MetadataService,
        research_catalog_service: ResearchCatalogService,
        derived_catalog_service: DerivedCatalogService,
        research_artifact_service: ResearchArtifactService,
        settings: DataStoreSettings,
    ) -> ResearchDatasetFacade:
        """Research dataset snapshot builder facade."""
        return ResearchDatasetFacade(
            metadata_service=metadata_service,
            research_catalog_service=research_catalog_service,
            artifact_reader=DerivedArtifactReader(
                catalog_service=derived_catalog_service,
                artifact_root=Path(settings.data_root),
            ),
            research_artifact_service=research_artifact_service,
        )


# ---------------------------------------------------------------------------
# AppProcessProvider — 编排/物化/质量服务
# ---------------------------------------------------------------------------


class AppProcessProvider(Provider):
    """App Process 层 DI Provider — 编排/物化/质量服务注册。"""

    scope = Scope.APP

    @provide
    def derived_input_provider(
        self,
        derived_catalog_service: DerivedCatalogService,
        market_service: MarketService,
        settings: DataStoreSettings,
    ) -> RuntimeDerivedInputProvider:
        """Runtime input provider backed by truth-layer parquet and artifacts."""
        return RuntimeDerivedInputProvider(
            catalog_service=derived_catalog_service,
            market_service=market_service,
            artifact_root=Path(settings.data_root),
            data_root=Path(settings.data_root),
        )

    @provide
    def derived_materialization_orchestrator(
        self,
        derived_catalog_service: DerivedCatalogService,
        compile_cache_service: SQLiteCompileCache,
        derived_input_provider: RuntimeDerivedInputProvider,
        publication_record_service: PublicationSafetyRecordService,
        metadata_service: MetadataService,
        settings: DataStoreSettings,
    ) -> DerivedMaterializationOrchestrator:
        """Unified materialization orchestrator."""
        return DerivedMaterializationOrchestrator(
            catalog_service=derived_catalog_service,
            compile_cache_service=compile_cache_service,
            artifact_writer=ArtifactPersistenceService(
                artifact_root=Path(settings.data_root),
            ),
            input_provider=derived_input_provider,
            universe_provider=metadata_service,
            publication_record_service=publication_record_service,
        )

    @provide
    def derived_invalidation_orchestrator(
        self,
        derived_catalog_service: DerivedCatalogService,
        derived_materialization_orchestrator: DerivedMaterializationOrchestrator,
    ) -> InvalidationCascadeOrchestrator:
        """BFS-based invalidation cascade with cycle guard and state machine."""
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
        """Publication orchestration facade."""
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
    def quality_service(self, dq_engine: QualityEngine) -> QualityService:
        """写入时 DQ 质量服务."""
        return QualityService(engine=dq_engine)


# ---------------------------------------------------------------------------
# AppBuilderFactory — 策略运行时装配
# ---------------------------------------------------------------------------


class AppBuilderFactory(Provider):
    """App Builder 层 DI Provider — 策略运行时装配服务注册。"""

    scope = Scope.APP

    @provide
    def strategy_runtime_builder(
        self,
        catalog_service: StrategyCatalogService,
    ) -> StrategyRuntimeBuilder:
        """提供 published strategy runtime builder。"""
        return StrategyRuntimeBuilder(catalog_service=catalog_service)

    @provide
    def backtest_runtime_builder(
        self,
        runtime_builder: StrategyRuntimeBuilder,
        metadata_service: MetadataService,
        market_service: MarketService,
    ) -> BacktestRuntimeBuilder:
        """提供 published strategy backtest runtime builder。"""
        return BacktestRuntimeBuilder(
            strategy_runtime_builder=runtime_builder,
            metadata_service=metadata_service,
            market_service=market_service,
        )

    @provide
    def strategy_slice_builder(
        self,
        runtime_builder: StrategyRuntimeBuilder,
        metadata_service: MetadataService,
        market_service: MarketService,
    ) -> StrategySliceBuilder:
        """提供 published strategy 单日 Slice builder。"""
        return StrategySliceBuilder(
            strategy_runtime_builder=runtime_builder,
            metadata_service=metadata_service,
            market_service=market_service,
        )

    @provide
    def strategy_service_factory(
        self,
        audit_service: ExecutionAuditService,
        artifact_service: StrategyArtifactService,
        run_service: StrategyRunLifecycleService,
        runtime_builder: StrategyRuntimeBuilder,
        backtest_runtime_builder: BacktestRuntimeBuilder,
    ) -> StrategyServiceFactory:
        """提供预接控制面依赖的 StrategyServiceFactory。"""
        return StrategyServiceFactory(
            audit_service=audit_service,
            artifact_service=artifact_service,
            run_service=run_service,
            runtime_builder=runtime_builder,
            backtest_runtime_builder=backtest_runtime_builder,
        )

    @provide
    def strategy_facade(
        self,
        factory: StrategyServiceFactory,
        slice_builder: StrategySliceBuilder,
    ) -> StrategyFacade:
        """提供统一的 catalog-backed 策略执行 facade。"""
        return StrategyFacade(factory=factory, slice_builder=slice_builder)


# ---------------------------------------------------------------------------
# 聚合入口
# ---------------------------------------------------------------------------


def get_app_providers() -> list[Provider]:
    """返回 App 层所有 Provider。"""
    return [
        AppQueryProvider(),
        AppProcessProvider(),
        AppBuilderFactory(),
    ]
