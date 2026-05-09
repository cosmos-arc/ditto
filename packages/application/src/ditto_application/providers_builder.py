"""Builder 层 DI Provider — 策略运行时装配服务注册。"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_execution.audit import ExecutionAuditService
from ditto_features.services import DerivedQueryService
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunLifecycleStore,
)

from ditto_application.builders import (
    BacktestRuntimeBuilder,
    StrategyRuntimeBuilder,
    StrategyServiceFactory,
    StrategySliceBuilder,
)
from ditto_application.builders.data_provider import ServiceBackedDataProvider
from ditto_application.processes.execution.strategy_run_process import StrategyFacade


class AppBuilderFactory(Provider):
    """App Builder 层 DI Provider — 策略运行时装配服务注册。"""

    scope = Scope.APP

    @provide
    def strategy_runtime_builder(
        self,
        catalog_service: StrategyCatalogService,
    ) -> StrategyRuntimeBuilder:
        """策略运行时构建器."""
        return StrategyRuntimeBuilder(catalog_service=catalog_service)

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
    ) -> BacktestRuntimeBuilder:
        """回测运行时构建器."""
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
        """策略切片构建器."""
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
        """策略服务工厂."""
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
        """策略运行门面."""
        return StrategyFacade(factory=factory, slice_builder=slice_builder)
