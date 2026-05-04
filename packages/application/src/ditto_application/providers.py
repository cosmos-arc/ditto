"""
App 层 DI Provider — 应用编排服务注册。

六个 Provider 按职责分离，对应 R8 互斥规则：
- AppCommandProvider: Command Handler 注册（command 模块）
- AppMarketQueryProvider: 市场数据查询服务（query 模块）
- AppStrategyQueryProvider: 策略/回测查询服务（query 模块）
- AppPortfolioQueryProvider: 组合/交易查询服务（query 模块）
- AppProcessProvider: 编排/物化/质量服务（process 模块）
- AppBuilderFactory: 策略运行时装配服务（builders 模块）
"""

from __future__ import annotations

from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_data.config.data_store import DataStoreSettings
from ditto_data.ingestion.publication_safety_record_service import (
    PublicationSafetyRecordService,
    PublicationSafetyRuntimeStores,
)
from ditto_data.ingestion.quality_record_service import QualityRecordService
from ditto_data.quality import QualityEngine
from ditto_data.quality.golden import GoldenDatasetSpec
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.sources.tdx.source import TdxSource
from ditto_data.storage.metadata.instrument import InstrumentReader
from ditto_data.storage.runtime.publication_shadow_sqlite import (
    SQLiteDerivedShadowSlotReader,
    SQLiteDerivedShadowSlotWriter,
)
from ditto_data.storage.runtime.quality import ComparisonWriter
from ditto_execution.audit import ExecutionAuditService
from ditto_execution.storage.sqlite.trade import TradeService

# ---------------------------------------------------------------------------
# Data 层依赖（由更底层的 Provider 注册，此处仅声明类型）
# ---------------------------------------------------------------------------
from ditto_features.compile_cache import SQLiteCompileCache
from ditto_features.services.derived import DerivedArtifactReader
from ditto_features.services.derived.artifact_persistence_service import (
    ArtifactPersistenceService,
)
from ditto_features.services.derived.query_service import DerivedQueryService
from ditto_features.services.derived_catalog_service import DerivedCatalogService
from ditto_features.services.derived_shadow_slot_service import (
    DerivedShadowSlotService,
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
from ditto_platform.foundation.storage.sqlite_client import SQLiteClient
from ditto_platform.services.notification import AlertManager
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunLifecycleStore,
)

# ---------------------------------------------------------------------------
# App Builder 层
# ---------------------------------------------------------------------------
from ditto_application.builders import (
    BacktestRuntimeBuilder,
    StrategyRuntimeBuilder,
    StrategyServiceFactory,
    StrategySliceBuilder,
)
from ditto_application.builders.data_provider import ServiceBackedDataProvider

# ---------------------------------------------------------------------------
# App Command 层
# ---------------------------------------------------------------------------
from ditto_application.commands.backtest import (
    BacktestRunHandler,
    CancelRunHandler,
    RetryRunHandler,
)
from ditto_application.commands.quality_check import CheckDataQualityHandler
from ditto_application.commands.quality_reconciliation import ReconcileSourcesHandler
from ditto_application.commands.strategy import (
    CreateStrategyHandler,
    PublishStrategyHandler,
    UpdateStrategyHandler,
)
from ditto_application.commands.trade import (
    RecordFillHandler,
    UpdateIntentStatusHandler,
)
from ditto_application.commands.universe import (
    CreateCustomUniverseHandler,
    DeleteCustomUniverseHandler,
    UpdateCustomUniverseHandler,
)
from ditto_application.processes.execution.factor_bridge import FactorBridge
from ditto_application.processes.execution.manual_tracker import ManualTracker
from ditto_application.processes.execution.replay_process import ReplayProcess
from ditto_application.processes.execution.strategy_run_process import StrategyFacade
from ditto_application.processes.execution.strategy_types import RunLifecycleService

# ---------------------------------------------------------------------------
# App Process 层
# ---------------------------------------------------------------------------
from ditto_application.processes.materialization.cascade_orchestrator import (
    InvalidationCascadeOrchestrator,
)
from ditto_application.processes.materialization.orchestrator import (
    DerivedMaterializationOrchestrator,
    RuntimeDerivedInputProvider,
)
from ditto_application.processes.materialization.publication_facade import (
    DerivedPublicationFacade,
)
from ditto_application.processes.quality import QualityPatrolService
from ditto_application.providers_market import AppMarketQueryProvider
from ditto_application.providers_portfolio import AppPortfolioQueryProvider
from ditto_application.providers_strategy import AppStrategyQueryProvider
from ditto_application.queries.market import MarketQueryFacade
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_application.settings import TradingSettings

__all__ = [
    "AppBuilderFactory",
    "AppCommandProvider",
    "AppMarketQueryProvider",
    "AppPortfolioQueryProvider",
    "AppProcessProvider",
    "AppStrategyQueryProvider",
    "get_app_providers",
]


# ---------------------------------------------------------------------------
# 日期范围配置（环境变量外部化，避免硬编码失效）
# ---------------------------------------------------------------------------


def get_trading_calendar_range(
    trading_settings: TradingSettings,
) -> tuple[str, str]:
    """
    获取交易日历查询的日期范围。

    通过 TradingSettings 类型化配置获取，支持环境变量别名覆盖。

    Returns:
        (start_date, end_date) 字符串元组，格式 YYYY-MM-DD。

    """
    return (
        trading_settings.trading_calendar_start,
        trading_settings.trading_calendar_end,
    )


# ---------------------------------------------------------------------------
# AppCommandProvider — Command Handler 注册
# ---------------------------------------------------------------------------


class AppCommandProvider(Provider):
    """App Command 层 DI Provider — Command Handler 注册。"""

    scope = Scope.APP

    @provide
    def check_data_quality_handler(
        self,
        dq_engine: QualityEngine,
        quality_record_service: QualityRecordService,
    ) -> CheckDataQualityHandler:
        """数据质量检查 Command Handler."""
        return CheckDataQualityHandler(
            engine=dq_engine,
            quarantine_writer=quality_record_service,
        )

    @provide
    def reconcile_sources_handler(
        self,
        dq_engine: QualityEngine,
        tdx_source: TdxSource,
        comparison_store: ComparisonWriter,
        instrument_store: InstrumentReader,
        golden_dataset: GoldenDatasetSpec | None = None,
    ) -> ReconcileSourcesHandler:
        """数据源对账 Command Handler."""
        return ReconcileSourcesHandler(
            engine=dq_engine,
            tdx_source=tdx_source,
            comparison_store=comparison_store,
            instrument_store=instrument_store,
            golden_dataset=golden_dataset,
        )

    @provide
    def create_strategy_handler(
        self,
        catalog_service: StrategyCatalogService,
    ) -> CreateStrategyHandler:
        """创建策略 Command Handler."""
        return CreateStrategyHandler(catalog_service=catalog_service)

    @provide
    def update_strategy_handler(
        self,
        catalog_service: StrategyCatalogService,
    ) -> UpdateStrategyHandler:
        """更新策略 Command Handler."""
        return UpdateStrategyHandler(catalog_service=catalog_service)

    @provide
    def publish_strategy_handler(
        self,
        catalog_service: StrategyCatalogService,
    ) -> PublishStrategyHandler:
        """发布策略 Command Handler."""
        return PublishStrategyHandler(catalog_service=catalog_service)

    @provide
    def record_fill_handler(
        self,
        trade_service: TradeService,
        manual_tracker: ManualTracker,
    ) -> RecordFillHandler:
        """录入人工成交 Command Handler."""
        return RecordFillHandler(
            trade_service=trade_service,
            manual_tracker=manual_tracker,
        )

    @provide
    def update_intent_status_handler(
        self,
        trade_service: TradeService,
    ) -> UpdateIntentStatusHandler:
        """更新交易意图状态 Command Handler."""
        return UpdateIntentStatusHandler(trade_service=trade_service)

    @provide
    def backtest_run_handler(
        self,
        catalog_service: StrategyCatalogService,
        run_service: StrategyRunLifecycleStore,
        factor_bridge: FactorBridge,
    ) -> BacktestRunHandler:
        """回测触发 Command Handler."""
        return BacktestRunHandler(
            catalog_service=catalog_service,
            run_service=run_service,
            factor_bridge=factor_bridge,
        )

    @provide
    def cancel_run_handler(
        self,
        run_service: StrategyRunLifecycleStore,
    ) -> CancelRunHandler:
        """取消运行 Command Handler."""
        return CancelRunHandler(run_service=run_service)

    @provide
    def retry_run_handler(
        self,
        run_service: StrategyRunLifecycleStore,
    ) -> RetryRunHandler:
        """重试运行 Command Handler."""
        return RetryRunHandler(run_service=run_service)

    @provide
    def run_lifecycle_service(
        self,
        run_service: StrategyRunLifecycleStore,
    ) -> RunLifecycleService:
        """RunLifecycleService Protocol 绑定 — 路由层通过此协议解耦 data 层."""
        return run_service

    @provide
    def create_custom_universe_handler(
        self,
        metadata_service: MetadataService,
    ) -> CreateCustomUniverseHandler:
        """创建自定义 Universe Command Handler."""
        return CreateCustomUniverseHandler(metadata_service=metadata_service)

    @provide
    def update_custom_universe_handler(
        self,
        metadata_service: MetadataService,
    ) -> UpdateCustomUniverseHandler:
        """更新自定义 Universe Command Handler."""
        return UpdateCustomUniverseHandler(metadata_service=metadata_service)

    @provide
    def delete_custom_universe_handler(
        self,
        metadata_service: MetadataService,
    ) -> DeleteCustomUniverseHandler:
        """删除自定义 Universe Command Handler."""
        return DeleteCustomUniverseHandler(metadata_service=metadata_service)


# ---------------------------------------------------------------------------
# AppProcessProvider — 编排/物化/质量服务
# ---------------------------------------------------------------------------


class AppProcessProvider(Provider):
    """App Process 层 DI Provider — 编排/物化/质量服务注册。"""

    scope = Scope.APP

    @provide
    def derived_shadow_slot_service(
        self,
        sqlite_client: SQLiteClient,
    ) -> DerivedShadowSlotService:
        """Shadow slot 控制面服务 — 组装 data 层 reader/writer 与 features 层服务."""
        return DerivedShadowSlotService(
            slot_reader=SQLiteDerivedShadowSlotReader(sqlite_client),
            slot_writer=SQLiteDerivedShadowSlotWriter(sqlite_client),
        )

    @provide
    def compile_cache_service(
        self,
        sqlite_client: SQLiteClient,
    ) -> SQLiteCompileCache:
        """基于 SQLite 的编译缓存服务."""
        return SQLiteCompileCache(sqlite_client)

    @provide
    def derived_input_provider(
        self,
        derived_catalog_service: DerivedCatalogService,
        market_service: MarketService,
        settings: DataStoreSettings,
    ) -> RuntimeDerivedInputProvider:
        """基于 truth-layer parquet 和制品的运行时输入提供器."""
        return RuntimeDerivedInputProvider(
            catalog_service=derived_catalog_service,
            market_service=market_service,
            artifact_root=Path(settings.data_root),
        )

    @provide
    def publication_safety_record_service(
        self,
        settings: DataStoreSettings,
    ) -> PublicationSafetyRecordService:
        """Feature-owned publication safety stores wired for app orchestration."""
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
    def derived_materialization_orchestrator(
        self,
        derived_catalog_service: DerivedCatalogService,
        compile_cache_service: SQLiteCompileCache,
        derived_input_provider: RuntimeDerivedInputProvider,
        publication_record_service: PublicationSafetyRecordService,
        metadata_service: MetadataService,
        settings: DataStoreSettings,
    ) -> DerivedMaterializationOrchestrator:
        """统一物化编排器."""
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
        """基于 BFS 的失效级联，带环检测和状态机."""
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
        """发布编排 facade."""
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
        """质量巡检服务（原 L3 批量统计检查）."""
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
        """人工持仓聚合追踪器 — 注入交易日历以支持 T+1 冻结逻辑."""
        start_date, end_date = get_trading_calendar_range(trading_settings)
        trading_days = metadata_service.list_trading_days(start_date, end_date)
        return ManualTracker(trading_calendar=tuple(trading_days))

    @provide
    def replay_process(
        self,
        strategy_facade: StrategyFacade,
        artifact_service: StrategyArtifactService,
    ) -> ReplayProcess:
        """回测重放编排 — 从原始运行恢复配置并重新执行."""
        return ReplayProcess(
            strategy_facade=strategy_facade,
            artifact_service=artifact_service,
        )

    @provide
    def factor_bridge(self) -> FactorBridge:
        """因子桥接 — 字符串表达式 → 编译 → 信号计算."""
        return FactorBridge()


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
    def data_provider(
        self,
        market_service: MarketService,
        metadata_service: MetadataService,
        derived_query_service: DerivedQueryService,
    ) -> ServiceBackedDataProvider:
        """提供 DataProvider 实现。"""
        return ServiceBackedDataProvider(
            market_service=market_service,
            metadata_service=metadata_service,
            derived_service=derived_query_service,
        )

    @provide
    def backtest_runtime_builder(
        self,
        runtime_builder: StrategyRuntimeBuilder,
        metadata_service: MetadataService,
        data_provider: ServiceBackedDataProvider,
    ) -> BacktestRuntimeBuilder:
        """提供 published strategy backtest runtime builder。"""
        return BacktestRuntimeBuilder(
            strategy_runtime_builder=runtime_builder,
            metadata_service=metadata_service,
            data_provider=data_provider,
        )

    @provide
    def strategy_slice_builder(
        self,
        runtime_builder: StrategyRuntimeBuilder,
        metadata_service: MetadataService,
        data_provider: ServiceBackedDataProvider,
    ) -> StrategySliceBuilder:
        """提供 published strategy 单日 Slice builder。"""
        return StrategySliceBuilder(
            strategy_runtime_builder=runtime_builder,
            metadata_service=metadata_service,
            data_provider=data_provider,
        )

    @provide
    def strategy_service_factory(
        self,
        audit_service: ExecutionAuditService,
        artifact_service: StrategyArtifactService,
        run_service: StrategyRunLifecycleStore,
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
        AppCommandProvider(),
        AppMarketQueryProvider(),
        AppStrategyQueryProvider(),
        AppPortfolioQueryProvider(),
        AppProcessProvider(),
        AppBuilderFactory(),
    ]
