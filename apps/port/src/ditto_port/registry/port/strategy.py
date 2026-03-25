"""Port 层 Strategy Provider。"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_datahub.services.audit import ExecutionAuditService
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_datahub.services.strategy.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_datahub.services.strategy.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_datahub.services.strategy.strategy_run_service import (
    StrategyRunService as StrategyRunLifecycleService,
)

from ditto_port.services.strategy.backtest_runtime_builder import (
    BacktestRuntimeBuilder,
)
from ditto_port.services.strategy.facade import StrategyFacade
from ditto_port.services.strategy.factory import StrategyServiceFactory
from ditto_port.services.strategy.runtime_builder import StrategyRuntimeBuilder
from ditto_port.services.strategy.slice_builder import StrategySliceBuilder

__all__ = ["StrategyProvider"]


class StrategyProvider(Provider):
    """Strategy 相关 Port service 工厂 Provider。"""

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
