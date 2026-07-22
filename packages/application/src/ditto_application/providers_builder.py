"""Builder 层 DI Provider — 策略运行时装配服务注册。"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_data.catalog.promotion import DatasetMaturityPromotionReader
from ditto_data.lineage import DataLineageRecorder
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_execution.audit import ExecutionAuditService
from ditto_features.services import DerivedQueryService
from ditto_strategy.alpha.node_registry import (
    NodeRegistry,
    default_node_registry,
)
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunCheckpointWriterProtocol,
    StrategyRunLifecycleStore,
)

from ditto_application.builders import (
    BacktestRuntimeBuilder,
    PublishedBaselineRuntimeBuilder,
    ResearchRuntimeBuilder,
    StrategyRuntimeBuilder,
    StrategyServiceFactory,
    StrategySliceBuilder,
)
from ditto_application.builders.data_provider import ServiceBackedDataProvider
from ditto_application.builders.node_pipeline_builder import NodePipelineBuilder
from ditto_application.processes.execution.strategy_run_process import StrategyFacade
from ditto_application.queries.fundamental import FundamentalQueryFacade
from ditto_application.settings import TradingSettings


def get_trading_calendar_range(
    trading_settings: TradingSettings,
) -> tuple[str, str]:
    """获取交易日历查询的日期范围。"""
    return (
        trading_settings.trading_calendar_start,
        trading_settings.trading_calendar_end,
    )


class AppBuilderFactory(Provider):
    """App Builder 层 DI Provider — 策略运行时装配服务注册。"""

    scope = Scope.APP

    @provide
    def node_registry(self) -> NodeRegistry:
        """提供固定 builtin descriptor manifest。"""
        return default_node_registry()

    @provide
    def node_pipeline_builder(
        self,
        node_registry: NodeRegistry,
    ) -> NodePipelineBuilder:
        """提供受约束 compiler 到现有 StrategyPipeline 的装配器。"""
        return NodePipelineBuilder(registry=node_registry)

    @provide
    def strategy_runtime_builder(
        self,
        catalog_service: StrategyCatalogService,
        node_registry: NodeRegistry,
        node_pipeline_builder: NodePipelineBuilder,
    ) -> StrategyRuntimeBuilder:
        """策略运行时构建器."""
        return StrategyRuntimeBuilder(
            catalog_service=catalog_service,
            node_registry=node_registry,
            node_pipeline_builder=node_pipeline_builder,
        )

    @provide
    def research_runtime_builder(
        self,
        node_registry: NodeRegistry,
        node_pipeline_builder: NodePipelineBuilder,
    ) -> ResearchRuntimeBuilder:
        """Explicit-version research runtime with no catalog writer dependency."""
        return ResearchRuntimeBuilder(
            node_registry=node_registry,
            node_pipeline_builder=node_pipeline_builder,
        )

    @provide
    def published_baseline_runtime_builder(
        self,
        node_registry: NodeRegistry,
        node_pipeline_builder: NodePipelineBuilder,
    ) -> PublishedBaselineRuntimeBuilder:
        """Build exact published ETF baselines through the constrained compiler."""
        return PublishedBaselineRuntimeBuilder(
            node_registry=node_registry,
            node_pipeline_builder=node_pipeline_builder,
        )

    @provide
    def data_provider(
        self,
        market_service: MarketService,
        metadata_service: MetadataService,
        derived_query_service: DerivedQueryService,
    ) -> ServiceBackedDataProvider:
        """服务层数据提供器."""
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
        maturity_promotion_reader: DatasetMaturityPromotionReader,
        fundamental_query_facade: FundamentalQueryFacade,
    ) -> BacktestRuntimeBuilder:
        """回测运行时构建器."""
        return BacktestRuntimeBuilder(
            strategy_runtime_builder=runtime_builder,
            metadata_service=metadata_service,
            data_provider=data_provider,
            maturity_promotion_reader=maturity_promotion_reader,
            fundamental_read_facade=fundamental_query_facade,
            # InstrumentService 满足 ClassificationReadFacade Protocol(其
            # get_stock_industry 委托 IndustryMappingReader 做 PIT 行业查询)。
            classification_read_facade=metadata_service.instrument,
        )

    @provide
    def strategy_slice_builder(
        self,
        runtime_builder: StrategyRuntimeBuilder,
        metadata_service: MetadataService,
        data_provider: ServiceBackedDataProvider,
        maturity_promotion_reader: DatasetMaturityPromotionReader,
    ) -> StrategySliceBuilder:
        """策略切片构建器."""
        return StrategySliceBuilder(
            strategy_runtime_builder=runtime_builder,
            metadata_service=metadata_service,
            data_provider=data_provider,
            maturity_promotion_reader=maturity_promotion_reader,
        )

    @provide
    def strategy_service_factory(
        self,
        audit_service: ExecutionAuditService,
        artifact_service: StrategyArtifactService,
        run_service: StrategyRunLifecycleStore,
        checkpoint_writer: StrategyRunCheckpointWriterProtocol,
        runtime_builder: StrategyRuntimeBuilder,
        backtest_runtime_builder: BacktestRuntimeBuilder,
        lineage_recorder: DataLineageRecorder,
    ) -> StrategyServiceFactory:
        """策略服务工厂."""
        return StrategyServiceFactory(
            audit_service=audit_service,
            artifact_service=artifact_service,
            run_service=run_service,
            checkpoint_writer=checkpoint_writer,
            runtime_builder=runtime_builder,
            backtest_runtime_builder=backtest_runtime_builder,
            lineage_recorder=lineage_recorder,
        )

    @provide
    def strategy_facade(
        self,
        factory: StrategyServiceFactory,
        slice_builder: StrategySliceBuilder,
    ) -> StrategyFacade:
        """策略运行门面."""
        return StrategyFacade(factory=factory, slice_builder=slice_builder)
