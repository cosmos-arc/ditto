"""Tests for StrategyProvider wiring."""

from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock

from dishka import Container, Provider, Scope, make_container, provide
from ditto_core.backtest.data_feed import DataFeed
from ditto_core.backtest.risk.pre_trade import CompositePreTradeCheck
from ditto_core.execution.brokerage import Brokerage
from ditto_core.execution.planner import ExecutionPlanner
from ditto_core.strategy.pipeline import StrategyPipeline
from ditto_core.strategy.specs import StrategySpec
from ditto_datahub.models.strategy import StrategySpecRecord
from ditto_datahub.services.audit import ExecutionAuditService
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_datahub.services.strategy.strategy_artifact_service import (
    StrategyArtifactService as DataHubStrategyArtifactService,
)
from ditto_datahub.services.strategy.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_datahub.services.strategy.strategy_run_service import (
    StrategyRunService as DataHubStrategyRunService,
)
from ditto_datahub.sources.source import DataSources
from ditto_port.registry import ConfigProvider
from ditto_port.registry.datahub import RuntimeProvider
from ditto_port.registry.port import StrategyProvider, get_port_providers
from ditto_port.services.strategy import (
    BacktestRuntimeBuilder,
    BacktestService,
    BacktestServiceConfig,
    MarketServiceDataFeed,
    StrategyFacade,
    StrategyInputAssembler,
    StrategyRunMode,
    StrategyRunService,
    StrategyRunServiceConfig,
    StrategySliceBuilder,
)
from ditto_port.services.strategy.factory import StrategyServiceFactory


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
        def metadata_service(self) -> MetadataService:
            return MagicMock(spec=MetadataService)

        @provide
        def market_service(self) -> MarketService:
            return MagicMock(spec=MarketService)

    return StrategyRuntimeDepsProvider()


def _make_test_container() -> Container:
    return make_container(
        ConfigProvider(),
        _sources_provider(),
        RuntimeProvider(),
        _strategy_runtime_deps_provider(),
        StrategyProvider(),
    )


class TestStrategyProvider:
    """Tests for Port strategy service factory wiring."""

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

    def test_registry_exports_strategy_provider(self) -> None:
        """Root registry 应导出 StrategyProvider。"""
        import ditto_port.registry as root_registry
        import ditto_port.registry.port as port_registry

        provider_names = [type(provider).__name__ for provider in get_port_providers()]

        assert "StrategyProvider" in provider_names
        assert "StrategyProvider" in root_registry.__all__
        assert "StrategyProvider" in port_registry.__all__

    def test_provider_builds_catalog_backed_strategy_run_service(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """StrategyProvider 应支持从 published catalog 直接构造 StrategyRunService。"""
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
        """StrategyProvider 应返回预接好控制面服务的 StrategyServiceFactory。"""
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
        assert isinstance(run_service._artifact_service, DataHubStrategyArtifactService)
        assert isinstance(run_service._run_service, DataHubStrategyRunService)
        assert isinstance(run_service._assembler, StrategyInputAssembler)
        assert run_service._assembler.strategy_id == "momentum-etf"

        assert isinstance(backtest_service, BacktestService)
        assert isinstance(
            backtest_service._options.audit_service,
            ExecutionAuditService,
        )
        assert isinstance(
            backtest_service._options.artifact_service,
            DataHubStrategyArtifactService,
        )
        assert isinstance(
            backtest_service._options.run_service,
            DataHubStrategyRunService,
        )
        container.close()

    def test_provider_builds_strategy_facade(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """StrategyProvider 应暴露统一的 StrategyFacade。"""
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
        """StrategyProvider 应暴露 StrategySliceBuilder。"""
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
        """StrategyProvider 应支持从 published catalog 直接构造 BacktestService。"""
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
        assert isinstance(service._data_feed, MarketServiceDataFeed)
        container.close()
