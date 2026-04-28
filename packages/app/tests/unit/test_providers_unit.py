"""Tests for App 层 DI Provider 结构和容器集成."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from dishka import Provider, Scope, make_container, provide
from ditto_app.builders import (
    BacktestRuntimeBuilder,
    StrategyRuntimeBuilder,
    StrategyServiceFactory,
    StrategySliceBuilder,
)
from ditto_app.command.quality_check import CheckDataQualityHandler
from ditto_app.process.execution.strategy_run_process import StrategyFacade
from ditto_app.process.materialization.cascade_orchestrator import (
    InvalidationCascadeOrchestrator,
)
from ditto_app.process.materialization.orchestrator import (
    DerivedMaterializationOrchestrator,
)
from ditto_app.process.materialization.publication_facade import (
    DerivedPublicationFacade,
)
from ditto_app.process.quality import QualityPatrolService
from ditto_app.providers import (
    AppBuilderFactory,
    AppCommandProvider,
    AppProcessProvider,
    get_app_providers,
)
from ditto_app.providers_market import AppMarketQueryProvider
from ditto_app.providers_portfolio import AppPortfolioQueryProvider
from ditto_app.providers_strategy import AppStrategyQueryProvider
from ditto_app.query.derived import DerivedQueryFacade
from ditto_data.config.data_store import DataStoreSettings
from ditto_data.di import (
    CapitalProvider,
    DerivedProvider,
    FundamentalProvider,
    MacroProvider,
    MarketProvider,
    MetadataProvider,
    QualityProvider,
    RuntimeProvider,
    TradeProvider,
)
from ditto_data.quality.golden import GoldenDatasetSpec
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.sources.exchange_transformers import ExchangeTransformers
from ditto_data.sources.source import DataSources
from ditto_data.sources.tdx.source import TdxSource
from ditto_infra.foundation.cache import DataCache
from ditto_infra.foundation.config.environment import Environment
from ditto_infra.foundation.config.settings import TradingSettings
from ditto_infra.services.notification import AlertManager

_tdx_mock = MagicMock(spec=TdxSource)

# ---------------------------------------------------------------------------
# Test fixtures: 辅助 Provider（替代 Interfaces 层 ConfigProvider）
# ---------------------------------------------------------------------------


class _TestConfigProvider(Provider):
    """测试用最小配置 Provider — 替代 ditto_interfaces.registry.infra.ConfigProvider."""

    scope = Scope.APP

    def __init__(self, data_root: Path) -> None:
        super().__init__()
        self._data_root = data_root

    @provide
    def environment(self) -> Environment:
        """提供测试环境枚举。"""
        return Environment.TESTING

    @provide
    def data_store_settings(self) -> DataStoreSettings:
        """提供测试用数据存储配置."""
        return DataStoreSettings(data_root=self._data_root)

    @provide
    def data_root(self) -> Path:
        """提供数据根目录路径."""
        return self._data_root

    @provide
    def trading_settings(self) -> TradingSettings:
        """提供测试用交易配置."""
        return TradingSettings()

    @provide
    def data_cache(self) -> DataCache[Any]:  # type: ignore[misc]
        """提供测试用内存缓存."""
        return DataCache(ttl_seconds=300, max_size=100)


def _sources_provider() -> Provider:
    class SourcesProvider(Provider):
        scope = Scope.APP

        @provide
        def data_sources(self) -> DataSources:
            return DataSources(tushare=MagicMock(), fred=None)

        @provide
        def exchange_transformers(self) -> ExchangeTransformers:
            return ExchangeTransformers(
                tushare=MagicMock(),
                tdx=MagicMock(),
            )

    return SourcesProvider()


def _runtime_deps_provider() -> Provider:
    class RuntimeDepsProvider(Provider):
        scope = Scope.APP

        @provide
        def metadata_service(self) -> MetadataService:
            svc = MagicMock(spec=MetadataService)
            svc.list_trading_days.return_value = [
                "2026-04-06",
                "2026-04-07",
                "2026-04-08",
                "2026-04-09",
                "2026-04-10",
                "2026-04-13",
                "2026-04-14",
                "2026-04-15",
                "2026-04-16",
                "2026-04-17",
            ]
            return svc

        @provide
        def market_service(self) -> MarketService:
            return MagicMock(spec=MarketService)

    return RuntimeDepsProvider()


def _notification_provider() -> Provider:
    """测试用通知 Provider — 提供 mock AlertManager."""

    class NotificationProvider(Provider):
        scope = Scope.APP

        @provide
        def alert_manager(self) -> AlertManager:
            return MagicMock(spec=AlertManager)

    return NotificationProvider()


class _TdxMockProvider(Provider):
    """测试用 TdxSource mock Provider — 替代 SourcesProvider.tdx_source."""

    scope = Scope.APP

    @provide
    def tdx_source(self) -> TdxSource:
        return _tdx_mock


class _GoldenNoneProvider(Provider):
    """测试用 GoldenDatasetSpec mock Provider — 返回 None."""

    scope = Scope.APP

    @provide
    def golden_dataset_spec(self) -> GoldenDatasetSpec | None:
        return None


# ---------------------------------------------------------------------------
# 结构测试:验证 Provider 类拥有正确的 provide 方法
# ---------------------------------------------------------------------------


class TestAppProviderStructure:
    """验证 App 层 Provider 结构."""

    def test_get_app_providers_returns_six_providers(self) -> None:
        """get_app_providers() 应返回 6 个 Provider 实例."""
        providers = get_app_providers()
        assert len(providers) == 6
        names = [type(p).__name__ for p in providers]
        assert "AppCommandProvider" in names
        assert "AppMarketQueryProvider" in names
        assert "AppStrategyQueryProvider" in names
        assert "AppPortfolioQueryProvider" in names
        assert "AppProcessProvider" in names
        assert "AppBuilderFactory" in names

    def test_app_market_query_provider_methods(self) -> None:
        """AppMarketQueryProvider 应包含市场数据查询的 provide 方法."""
        provider = AppMarketQueryProvider()
        method_names = {name for name in dir(provider) if not name.startswith("_")}
        expected = {
            "forward_return_service",
            "derived_query_facade",
            "market_query_facade",
            "source_query_facade",
            "research_dataset_facade",
            "metadata_query_facade",
            "capital_query_facade",
            "fundamental_query_facade",
            "macro_query_facade",
            "fx_query_facade",
            "commodity_query_facade",
            "universe_query_facade",
            "ingestion_status_query_facade",
        }
        assert expected.issubset(method_names)

    def test_app_strategy_query_provider_methods(self) -> None:
        """AppStrategyQueryProvider 应包含策略/回测查询的 provide 方法."""
        provider = AppStrategyQueryProvider()
        method_names = {name for name in dir(provider) if not name.startswith("_")}
        expected = {
            "backtest_trade_query_facade",
            "backtest_artifact_reader",
            "backtest_query_facade",
            "run_read_model",
            "strategy_query_facade",
            "lineage_query_facade",
            "comparison_query_facade",
        }
        assert expected.issubset(method_names)

    def test_app_portfolio_query_provider_methods(self) -> None:
        """AppPortfolioQueryProvider 应包含组合/交易查询的 provide 方法."""
        provider = AppPortfolioQueryProvider()
        method_names = {name for name in dir(provider) if not name.startswith("_")}
        expected = {
            "trade_query_facade",
            "portfolio_actual_query_facade",
            "signal_query_facade",
        }
        assert expected.issubset(method_names)

    def test_app_command_provider_methods(self) -> None:
        """AppCommandProvider 应包含 1 个 provide 方法."""
        provider = AppCommandProvider()
        method_names = {name for name in dir(provider) if not name.startswith("_")}
        expected = {
            "check_data_quality_handler",
        }
        assert expected.issubset(method_names)

    def test_app_process_provider_methods(self) -> None:
        """AppProcessProvider 应包含 provide 方法."""
        provider = AppProcessProvider()
        method_names = {name for name in dir(provider) if not name.startswith("_")}
        expected = {
            "compile_cache_service",
            "derived_input_provider",
            "derived_materialization_orchestrator",
            "derived_invalidation_orchestrator",
            "derived_publication_facade",
            "quality_patrol_service",
        }
        assert expected.issubset(method_names)

    def test_app_builder_factory_methods(self) -> None:
        """AppBuilderFactory 应包含 5 个 provide 方法."""
        provider = AppBuilderFactory()
        method_names = {name for name in dir(provider) if not name.startswith("_")}
        expected = {
            "strategy_runtime_builder",
            "backtest_runtime_builder",
            "strategy_slice_builder",
            "strategy_service_factory",
            "strategy_facade",
        }
        assert expected.issubset(method_names)


# ---------------------------------------------------------------------------
# 集成测试:验证 App Provider 可以在完整容器中正确解析服务
# ---------------------------------------------------------------------------


class TestAppProviderIntegration:
    """验证 App 层 Provider 与完整容器的集成."""

    @pytest.fixture
    def app_container(self, monkeypatch, tmp_path):
        """构建包含所有层级的完整测试容器."""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())

        container = make_container(
            _TestConfigProvider(tmp_path),
            QualityProvider(),
            _sources_provider(),
            _TdxMockProvider(),
            _GoldenNoneProvider(),
            RuntimeProvider(),
            MetadataProvider(),
            MarketProvider(),
            CapitalProvider(),
            FundamentalProvider(),
            MacroProvider(),
            DerivedProvider(),
            TradeProvider(),
            _notification_provider(),
            *get_app_providers(),
            _runtime_deps_provider(),
        )
        yield container
        container.close()

    def test_query_services_resolved(self, app_container) -> None:
        """AppMarketQueryProvider 的服务应可从容器解析."""
        assert isinstance(app_container.get(DerivedQueryFacade), DerivedQueryFacade)

    def test_process_services_resolved(self, app_container) -> None:
        """AppProcessProvider 的服务应可从容器解析."""
        assert isinstance(
            app_container.get(DerivedMaterializationOrchestrator),
            DerivedMaterializationOrchestrator,
        )
        assert isinstance(
            app_container.get(InvalidationCascadeOrchestrator),
            InvalidationCascadeOrchestrator,
        )
        assert isinstance(
            app_container.get(DerivedPublicationFacade),
            DerivedPublicationFacade,
        )
        assert isinstance(app_container.get(QualityPatrolService), QualityPatrolService)

    def test_builder_services_resolved(self, app_container) -> None:
        """AppBuilderFactory 的服务应可从容器解析."""
        assert isinstance(
            app_container.get(StrategyRuntimeBuilder),
            StrategyRuntimeBuilder,
        )
        assert isinstance(
            app_container.get(BacktestRuntimeBuilder),
            BacktestRuntimeBuilder,
        )
        assert isinstance(
            app_container.get(StrategySliceBuilder),
            StrategySliceBuilder,
        )
        assert isinstance(
            app_container.get(StrategyServiceFactory),
            StrategyServiceFactory,
        )
        assert isinstance(app_container.get(StrategyFacade), StrategyFacade)

    def test_command_services_resolved(self, app_container) -> None:
        """AppCommandProvider 的服务应可从容器解析."""
        assert isinstance(
            app_container.get(CheckDataQualityHandler),
            CheckDataQualityHandler,
        )

    def test_manual_tracker_receives_trading_calendar(self, app_container) -> None:
        """ManualTracker 应从 MetadataService 加载交易日历（非空 tuple）."""
        from ditto_app.process.execution.manual_tracker import ManualTracker

        tracker = app_container.get(ManualTracker)
        assert isinstance(tracker, ManualTracker)
        assert isinstance(tracker._calendar, tuple)
        assert len(tracker._calendar) > 0


# ---------------------------------------------------------------------------
# 日期范围配置测试
# ---------------------------------------------------------------------------


class TestTradingCalendarRange:
    """测试 get_trading_calendar_range 类型化配置."""

    def test_default_values(self) -> None:
        """默认 TradingSettings 应返回默认日期范围."""
        from ditto_app.providers import get_trading_calendar_range
        from ditto_infra.foundation.config.settings import TradingSettings

        settings = TradingSettings()
        start, end = get_trading_calendar_range(settings)
        assert start == "2020-01-01"
        assert end == "2030-12-31"

    def test_custom_values(self) -> None:
        """自定义 TradingSettings 应返回自定义日期范围."""
        from ditto_app.providers import get_trading_calendar_range
        from ditto_infra.foundation.config.settings import TradingSettings

        settings = TradingSettings(
            trading_calendar_start="2019-06-01",
            trading_calendar_end="2040-06-30",
        )
        start, end = get_trading_calendar_range(settings)
        assert start == "2019-06-01"
        assert end == "2040-06-30"

    def test_only_start_customized(self) -> None:
        """仅自定义 START 时 END 应保持默认值."""
        from ditto_app.providers import get_trading_calendar_range
        from ditto_infra.foundation.config.settings import TradingSettings

        settings = TradingSettings(trading_calendar_start="2018-01-01")
        start, end = get_trading_calendar_range(settings)
        assert start == "2018-01-01"
        assert end == "2030-12-31"

    def test_env_alias_populates_settings(self) -> None:
        """TradingSettings 应通过构造参数覆盖默认值."""
        from ditto_infra.foundation.config.settings import TradingSettings

        settings = TradingSettings(
            trading_calendar_start="2021-03-01",
            trading_calendar_end="2035-06-30",
        )
        assert settings.trading_calendar_start == "2021-03-01"
        assert settings.trading_calendar_end == "2035-06-30"
