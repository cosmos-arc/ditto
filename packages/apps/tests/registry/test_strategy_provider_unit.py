"""Tests for App Builder Provider wiring (原 StrategyProvider 测试)."""

from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock

from dishka import Container, Provider, Scope, make_container, provide
from ditto_application.builders import (
    BacktestRuntimeBuilder,
    StrategyServiceFactory,
    StrategySliceBuilder,
)
from ditto_application.processes.execution.backtest_process import (
    BacktestService,
    BacktestServiceConfig,
)
from ditto_application.processes.execution.strategy_input import StrategyInputAssembler
from ditto_application.processes.execution.strategy_run_process import (
    StrategyFacade,
    StrategyRunMode,
    StrategyRunService,
    StrategyRunServiceConfig,
)
from ditto_apps.registry import ConfigProvider
from ditto_backtest.data_feed import DataFeed, ProviderBackedDataFeed
from ditto_data.di import RuntimeProvider
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.sources.source import DataSources
from ditto_execution.audit import ExecutionAuditService
from ditto_execution.brokerage import Brokerage
from ditto_execution.planner import ExecutionPlanner
from ditto_features.services import DerivedQueryService
from ditto_risk.pre_trade import CompositePreTradeCheck
from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.specs import StrategySpec
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunLifecycleStore as DataStrategyRunLifecycleStore,
)


def _sources_provider() -> Provider:
    class SourcesProvider(Provider):
        scope = Scope.APP

        @provide
        def data_sources(self) -> DataSources:
            return DataSources(tushare=MagicMock(), fred=None)

    return SourcesProvider()


def _strategy_runtime_deps_provider() -> Provider:
    class StrategyRuntimeDepsProvider(Provider):
        scope = Scope.APP

        @provide
        def market_service(self) -> MarketService:
            return MagicMock(spec=MarketService)

        @provide
        def metadata_service(self) -> MetadataService:
            return MagicMock(spec=MetadataService)

        @provide
        def derived_query_service(self) -> DerivedQueryService:
            return MagicMock(spec=DerivedQueryService)

    return StrategyRuntimeDepsProvider()


def _make_test_container() -> Container:
    from ditto_application.providers import AppBuilderFactory
    from ditto_data.di import QualityProvider
    from ditto_execution.di import ExecutionStorageProvider
    from ditto_strategy.di import StrategyStorageProvider

    return make_container(
        ConfigProvider(),
        _sources_provider(),
        RuntimeProvider(),
        _strategy_runtime_deps_provider(),
        QualityProvider(),
        AppBuilderFactory(),
        StrategyStorageProvider(),
        ExecutionStorageProvider(),
    )


class TestAppBuilderFactory:
    """Tests for App Builder Factory wiring (原 StrategyProvider)."""

    @staticmethod
    def _make_strategy_spec() -> StrategySpec:
        """构造测试用已发布策略定义。"""
        return StrategySpec(
            strategy_id="momentum-etf",
            name="Momentum ETF",
            template="etf_rotation",
            universe="cn_etf",
            asset_class="etf",
            params={
                "top_k": 3,
                "allocation_method": "equal_weight",
                "cash_target": 0.1,
                "signal_column": "momentum_20d",
                "max_weight": 0.4,
                "max_positions": 3,
                "scoring_method": "rank",
                "scoring_ascending": True,
            },
            tags=("momentum", "etf"),
        )

    def test_provider_builds_catalog_backed_strategy_run_service(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """AppBuilderFactory 应支持从 published catalog 直接构造 StrategyRunService。"""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        container = _make_test_container()
        spec = self._make_strategy_spec()
        catalog_service = container.get(StrategyCatalogService)
        catalog_service.save_spec(
            StrategySpecRecord(
                strategy_id=spec.strategy_id,
                name=spec.name,
                spec_json=asdict(spec),
                version=2,
                tags=spec.tags,
            )
        )
        catalog_service.publish_spec("momentum-etf", 2)

        factory = container.get(StrategyServiceFactory)
        service = factory.build_strategy_run_service_from_catalog(
            config=StrategyRunServiceConfig(
                strategy_id="momentum-etf",
                mode=StrategyRunMode.RESEARCH,
            ),
            version=2,
        )

        assert isinstance(service, StrategyRunService)
        assert isinstance(service._pipeline, StrategyPipeline)
        assert service._config.spec is not None
        assert service._config.strategy_version == "2"
        assert service._assembler.parameters["top_k"] == 3
        container.close()

    def test_provider_builds_strategy_service_factory(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """AppBuilderFactory 应返回预接好控制面服务的 StrategyServiceFactory。"""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        container = _make_test_container()

        factory = container.get(StrategyServiceFactory)
        backtest_runtime_builder = container.get(BacktestRuntimeBuilder)
        run_service = factory.build_strategy_run_service(
            config=StrategyRunServiceConfig(
                strategy_id="momentum-etf",
                mode=StrategyRunMode.RECOMMENDATION,
            ),
            pipeline=MagicMock(spec=StrategyPipeline),
        )
        backtest_service = factory.build_backtest_service(
            config=BacktestServiceConfig(
                strategy_id="momentum-etf",
                start_date="2026-01-01",
                end_date="2026-03-01",
            ),
            pipeline=MagicMock(spec=StrategyPipeline),
            planner=MagicMock(spec=ExecutionPlanner),
            brokerage=MagicMock(spec=Brokerage),
            pre_trade_check=MagicMock(spec=CompositePreTradeCheck),
            data_feed=MagicMock(spec=DataFeed),
        )

        assert isinstance(factory, StrategyServiceFactory)
        assert isinstance(backtest_runtime_builder, BacktestRuntimeBuilder)
        assert isinstance(run_service, StrategyRunService)
        assert isinstance(run_service._artifact_service, StrategyArtifactService)
        assert isinstance(run_service._run_service, DataStrategyRunLifecycleStore)
        assert isinstance(run_service._assembler, StrategyInputAssembler)
        assert run_service._assembler.strategy_id == "momentum-etf"

        assert isinstance(backtest_service, BacktestService)
        assert isinstance(
            backtest_service._options.audit_service,
            ExecutionAuditService,
        )
        assert isinstance(
            backtest_service._options.artifact_service,
            StrategyArtifactService,
        )
        assert isinstance(
            backtest_service._options.run_service,
            DataStrategyRunLifecycleStore,
        )
        container.close()

    def test_provider_builds_strategy_facade(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """AppBuilderFactory 应暴露统一的 StrategyFacade。"""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        container = _make_test_container()

        facade = container.get(StrategyFacade)

        assert isinstance(facade, StrategyFacade)
        container.close()

    def test_provider_builds_strategy_slice_builder(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """AppBuilderFactory 应暴露 StrategySliceBuilder。"""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        container = _make_test_container()

        slice_builder = container.get(StrategySliceBuilder)

        assert isinstance(slice_builder, StrategySliceBuilder)
        container.close()

    def test_provider_builds_catalog_backed_backtest_service(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """AppBuilderFactory 应支持从 published catalog 直接构造 BacktestService。"""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        container = _make_test_container()
        spec = self._make_strategy_spec()
        catalog_service = container.get(StrategyCatalogService)
        catalog_service.save_spec(
            StrategySpecRecord(
                strategy_id=spec.strategy_id,
                name=spec.name,
                spec_json=asdict(spec),
                version=2,
                tags=spec.tags,
            )
        )
        catalog_service.publish_spec("momentum-etf", 2)

        factory = container.get(StrategyServiceFactory)
        service = factory.build_backtest_service_from_catalog(
            config=BacktestServiceConfig(
                strategy_id="momentum-etf",
                start_date="2026-01-01",
                end_date="2026-03-01",
                initial_cash=1_500_000.0,
            ),
            version=2,
        )

        assert isinstance(service, BacktestService)
        assert service._config.strategy_version == "2"
        # data_feed 是 ProviderBackedDataFeed 实例（满足 DataFeed Protocol）
        assert isinstance(service._data_feed, ProviderBackedDataFeed)
        container.close()
