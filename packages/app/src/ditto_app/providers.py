"""
App 层 DI Provider — 应用编排服务注册。

四个 Provider 按职责分离，对应 R8 互斥规则：
- AppCommandProvider: Command Handler 注册（command 模块）
- AppQueryProvider: 只读查询服务（query 模块）
- AppProcessProvider: 编排/物化/质量服务（process 模块）
- AppBuilderFactory: 策略运行时装配服务（builders 模块）
"""

from __future__ import annotations

from pathlib import Path

from dishka import Provider, Scope, provide

# ---------------------------------------------------------------------------
# Data 层依赖（由更底层的 Provider 注册，此处仅声明类型）
# ---------------------------------------------------------------------------
from ditto_analytics.compile_cache import SQLiteCompileCache
from ditto_data import SQLiteClient
from ditto_data.config.data_store import DataStoreSettings
from ditto_data.providers.provider import ServiceBackedDataProvider
from ditto_data.quality import QualityEngine
from ditto_data.services import (
    DerivedArtifactReader,
    DerivedCatalogService,
    DerivedQueryService,
    DerivedShadowSlotService,
    PublicationSafetyRecordService,
    QualityRecordService,
    ResearchCatalogService,
)
from ditto_data.services.audit import ExecutionAuditService
from ditto_data.services.capital_service import CapitalService
from ditto_data.services.derived.artifact_persistence_service import (
    ArtifactPersistenceService,
)
from ditto_data.services.fundamental_service import FundamentalService
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.services.research_artifact_service import ResearchArtifactService
from ditto_data.services.source_service import SourceService
from ditto_data.services.strategy.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_data.services.strategy.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_data.services.strategy.strategy_run_service import (
    StrategyRunService as StrategyRunLifecycleService,
)
from ditto_data.services.trade_service import TradeService

# ---------------------------------------------------------------------------
# App Builder 层
# ---------------------------------------------------------------------------
from ditto_app.builders import (
    BacktestRuntimeBuilder,
    StrategyRuntimeBuilder,
    StrategyServiceFactory,
    StrategySliceBuilder,
)

# ---------------------------------------------------------------------------
# App Command 层
# ---------------------------------------------------------------------------
from ditto_app.command.backtest import (
    BacktestRunHandler,
    CancelRunHandler,
    RetryRunHandler,
)
from ditto_app.command.quality_check import CheckDataQualityHandler
from ditto_app.command.strategy import (
    CreateStrategyHandler,
    PublishStrategyHandler,
    UpdateStrategyHandler,
)
from ditto_app.command.trade import (
    RecordFillHandler,
    UpdateIntentStatusHandler,
)
from ditto_app.command.universe import (
    CreateCustomUniverseHandler,
    DeleteCustomUniverseHandler,
    UpdateCustomUniverseHandler,
)
from ditto_app.process.execution.factor_bridge import FactorBridge
from ditto_app.process.execution.manual_tracker import ManualTracker
from ditto_app.process.execution.replay_process import ReplayProcess  # noqa: RUF100
from ditto_app.process.execution.strategy_run_process import StrategyFacade
from ditto_app.process.execution.strategy_types import RunLifecycleService

# ---------------------------------------------------------------------------
# App Process 层
# ---------------------------------------------------------------------------
from ditto_app.process.materialization.cascade_orchestrator import (
    InvalidationCascadeOrchestrator,
)
from ditto_app.process.materialization.orchestrator import (
    DerivedMaterializationOrchestrator,
    RuntimeDerivedInputProvider,
)
from ditto_app.process.materialization.publication_facade import (
    DerivedPublicationFacade,
)
from ditto_app.process.quality import QualityPatrolService

# ---------------------------------------------------------------------------
# App Query 层
# ---------------------------------------------------------------------------
from ditto_app.query.backtest import BacktestQueryFacade
from ditto_app.query.backtest_trade import BacktestTradeQueryFacade
from ditto_app.query.capital import CapitalQueryFacade
from ditto_app.query.commodity import CommodityQueryFacade
from ditto_app.query.comparison import ComparisonQueryFacade
from ditto_app.query.derived import DerivedQueryFacade
from ditto_app.query.forward_return_service import ForwardReturnService
from ditto_app.query.fundamental import FundamentalQueryFacade
from ditto_app.query.fx import FXQueryFacade
from ditto_app.query.lineage import LineageQueryFacade  # noqa: RUF100
from ditto_app.query.macro import MacroQueryFacade
from ditto_app.query.market import MarketQueryFacade
from ditto_app.query.metadata import MetadataQueryFacade
from ditto_app.query.portfolio_actual import PortfolioActualQueryFacade
from ditto_app.query.research import ResearchDatasetFacade
from ditto_app.query.run import RunReadModel
from ditto_app.query.signal import SignalQueryFacade
from ditto_app.query.source import SourceQueryFacade
from ditto_app.query.strategy import StrategyQueryFacade
from ditto_app.query.trade import TradeQueryFacade
from ditto_app.query.universe import UniverseQueryFacade

__all__ = [
    "AppBuilderFactory",
    "AppCommandProvider",
    "AppProcessProvider",
    "AppQueryProvider",
    "get_app_providers",
]


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
        run_service: StrategyRunLifecycleService,
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
        run_service: StrategyRunLifecycleService,
    ) -> CancelRunHandler:
        """取消运行 Command Handler."""
        return CancelRunHandler(run_service=run_service)

    @provide
    def retry_run_handler(
        self,
        run_service: StrategyRunLifecycleService,
    ) -> RetryRunHandler:
        """重试运行 Command Handler."""
        return RetryRunHandler(run_service=run_service)

    @provide
    def run_lifecycle_service(
        self,
        run_service: StrategyRunLifecycleService,
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
# AppQueryProvider — 只读查询服务
# ---------------------------------------------------------------------------


class AppQueryProvider(Provider):
    """App Query 层 DI Provider — 只读查询服务注册。"""

    scope = Scope.APP

    @provide
    def forward_return_service(
        self,
        market_service: MarketService,
    ) -> ForwardReturnService:
        """前向收益率计算服务."""
        return ForwardReturnService(market_service=market_service)

    @provide
    def derived_query_facade(
        self,
        derived_query_service: DerivedQueryService,
    ) -> DerivedQueryFacade:
        """衍生数据查询用例 facade."""
        return DerivedQueryFacade(
            service=derived_query_service,
        )

    @provide
    def market_query_facade(
        self,
        market_service: MarketService,
    ) -> MarketQueryFacade:
        """行情数据查询 facade — 隐藏内部查询类型."""
        return MarketQueryFacade(market_service=market_service)

    @provide
    def source_query_facade(
        self,
        source_service: SourceService,
        metadata_service: MetadataService,
    ) -> SourceQueryFacade:
        """数据源查询 facade — 隐藏 Dataset 枚举和服务接线."""
        return SourceQueryFacade(
            source_service=source_service,
            metadata_service=metadata_service,
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
        """研究数据集快照构建 facade."""
        return ResearchDatasetFacade(
            metadata_service=metadata_service,
            research_catalog_service=research_catalog_service,
            artifact_reader=DerivedArtifactReader(
                catalog_service=derived_catalog_service,
                artifact_root=Path(settings.data_root),
            ),
            research_artifact_service=research_artifact_service,
        )

    @provide
    def metadata_query_facade(
        self,
        metadata_service: MetadataService,
    ) -> MetadataQueryFacade:
        """元数据查询 facade — 隐藏 SecurityQuery 和内部类型."""
        return MetadataQueryFacade(metadata_service=metadata_service)

    @provide
    def capital_query_facade(
        self,
        capital_service: CapitalService,
    ) -> CapitalQueryFacade:
        """资金查询 facade — 隐藏 CQRS 端口类型."""
        return CapitalQueryFacade(capital_service=capital_service)

    @provide
    def fundamental_query_facade(
        self,
        fundamental_service: FundamentalService,
    ) -> FundamentalQueryFacade:
        """基本面查询 facade — 隐藏 CQRS 端口类型."""
        return FundamentalQueryFacade(fundamental_service=fundamental_service)

    @provide
    def macro_query_facade(
        self,
        macro_service: MacroService,
    ) -> MacroQueryFacade:
        """宏观查询 facade — 隐藏 MacroQuery 和枚举类型."""
        return MacroQueryFacade(macro_service=macro_service)

    @provide
    def fx_query_facade(
        self,
        market_service: MarketService,
    ) -> FXQueryFacade:
        """外汇查询 facade — 隐藏 FX 代码映射和资产类别."""
        return FXQueryFacade(market_service=market_service)

    @provide
    def commodity_query_facade(
        self,
        market_service: MarketService,
    ) -> CommodityQueryFacade:
        """商品查询 facade — 隐藏 Commodity/VIX 映射和资产类别."""
        return CommodityQueryFacade(market_service=market_service)

    @provide
    def backtest_trade_query_facade(
        self,
        artifact_service: StrategyArtifactService,
    ) -> BacktestTradeQueryFacade:
        """回测成交查询 facade."""
        return BacktestTradeQueryFacade(artifact_service=artifact_service)

    @provide
    def run_read_model(
        self,
        run_service: StrategyRunLifecycleService,
    ) -> RunReadModel:
        """回测运行读模型."""
        return RunReadModel(run_service=run_service)

    @provide
    def strategy_query_facade(
        self,
        catalog_service: StrategyCatalogService,
    ) -> StrategyQueryFacade:
        """策略只读查询 facade — 封装 StrategyCatalogService."""
        return StrategyQueryFacade(catalog_service=catalog_service)

    @provide
    def backtest_query_facade(
        self,
        trade_facade: BacktestTradeQueryFacade,
        run_model: RunReadModel,
        audit_service: ExecutionAuditService,
        artifact_service: StrategyArtifactService,
    ) -> BacktestQueryFacade:
        """回测统一查询门面."""
        return BacktestQueryFacade(
            trade_facade=trade_facade,
            run_model=run_model,
            audit_service=audit_service,
            artifact_service=artifact_service,
        )

    @provide
    def trade_query_facade(
        self,
        trade_service: TradeService,
    ) -> TradeQueryFacade:
        """交易意图查询 facade — 封装 TradeService."""
        return TradeQueryFacade(trade_service=trade_service)

    @provide
    def portfolio_actual_query_facade(
        self,
        trade_service: TradeService,
    ) -> PortfolioActualQueryFacade:
        """实际组合查询 facade — 封装 TradeService 的持仓/成交/P&L 查询."""
        return PortfolioActualQueryFacade(trade_service=trade_service)

    @provide
    def lineage_query_facade(
        self,
        run_service: StrategyRunLifecycleService,
    ) -> LineageQueryFacade:
        """运行血统查询 facade — 提供 lineage chain 查询."""
        return LineageQueryFacade(run_service=run_service)

    @provide
    def signal_query_facade(
        self,
        trade_service: TradeService,
    ) -> SignalQueryFacade:
        """信号查询 facade — 封装 TradeService 的意图查询."""
        return SignalQueryFacade(trade_service=trade_service)

    @provide
    def comparison_query_facade(
        self,
        backtest_facade: BacktestQueryFacade,
        actual_facade: PortfolioActualQueryFacade,
    ) -> ComparisonQueryFacade:
        """回测 vs 实际对比查询 facade."""
        return ComparisonQueryFacade(
            backtest_facade=backtest_facade,
            actual_facade=actual_facade,
        )

    @provide
    def universe_query_facade(
        self,
        metadata_service: MetadataService,
    ) -> UniverseQueryFacade:
        """Universe 只读查询 facade — 封装 MetadataService universe 方法."""
        return UniverseQueryFacade(metadata_service=metadata_service)


# ---------------------------------------------------------------------------
# AppProcessProvider — 编排/物化/质量服务
# ---------------------------------------------------------------------------


class AppProcessProvider(Provider):
    """App Process 层 DI Provider — 编排/物化/质量服务注册。"""

    scope = Scope.APP

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
    ) -> QualityPatrolService:
        """质量巡检服务（原 L3 批量统计检查）."""
        return QualityPatrolService(
            engine=dq_engine,
            market_facade=market_facade,
            metadata_facade=metadata_facade,
        )

    @provide
    def manual_tracker(
        self,
        metadata_service: MetadataService,
    ) -> ManualTracker:
        """人工持仓聚合追踪器 — 注入交易日历以支持 T+1 冻结逻辑."""
        trading_days = metadata_service.list_trading_days("2020-01-01", "2030-12-31")
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
        AppCommandProvider(),
        AppQueryProvider(),
        AppProcessProvider(),
        AppBuilderFactory(),
    ]
