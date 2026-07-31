"""Tests for App 层 DI Provider 结构和容器集成."""

import inspect
from pathlib import Path
from typing import Any, get_type_hints
from unittest.mock import MagicMock

import pytest
from dishka import Provider, Scope, make_container, provide
from ditto_application.builders import (
    BacktestRuntimeBuilder,
    PublishedBaselineRuntimeBuilder,
    ResearchRuntimeBuilder,
    StrategyRuntimeBuilder,
    StrategyServiceFactory,
    StrategySliceBuilder,
)
from ditto_application.builders.node_pipeline_builder import NodePipelineBuilder
from ditto_application.builders.research_executor_probe import (
    BuilderBackedResearchExecutorProbe,
)
from ditto_application.builders.research_validation_authority import (
    ProductionResearchValidationAuthorityProbe,
)
from ditto_application.commands.account import ImportAccountBaselineHandler
from ditto_application.commands.catalog import (
    ReviewDatasetPromotionEvidenceHandler,
    RevokeDatasetMaturityPromotionHandler,
)
from ditto_application.commands.catalog_remediation import (
    CatalogRemediationIngestDatePort,
    ExecuteCatalogRemediationApprovalHandler,
)
from ditto_application.commands.experiments import LaunchExperimentHandler
from ditto_application.commands.quality_check import CheckDataQualityHandler
from ditto_application.commands.trade import ProjectedFillCorrectionAdapter
from ditto_application.processes.execution.manual_sizing import (
    AShareTradeDateResolver,
    ManualSizingContextBuilder,
)
from ditto_application.processes.execution.replay_process import (
    IndexedResearchReplayArtifactReader,
    ReplayProcess,
)
from ditto_application.processes.execution.signal_package import SignalPackagePublisher
from ditto_application.processes.execution.strategy_run_process import StrategyFacade
from ditto_application.processes.experiments.planning_process import (
    ExperimentPlanningProcess,
)
from ditto_application.processes.experiments.scheduler_store import (
    FirstAttemptFactory,
)
from ditto_application.processes.experiments.worker import (
    ResearchExperimentWorker,
    ResearchFoldRunner,
)
from ditto_application.processes.materialization.cascade_orchestrator import (
    InvalidationCascadeOrchestrator,
)
from ditto_application.processes.materialization.orchestrator import (
    DerivedMaterializationOrchestrator,
    MaterializationRuntimePorts,
)
from ditto_application.processes.materialization.publication_facade import (
    DerivedPublicationFacade,
)
from ditto_application.processes.quality import (
    QualityBatchCoordinator,
    QualityCompletenessService,
    QualityPatrolService,
)
from ditto_application.providers import (
    AppBuilderFactory,
    AppCommandProvider,
    AppProcessProvider,
    AppResearchExecutionProvider,
    get_app_providers,
)
from ditto_application.providers_market import AppMarketQueryProvider
from ditto_application.providers_portfolio import AppPortfolioQueryProvider
from ditto_application.providers_strategy import AppStrategyQueryProvider
from ditto_application.queries.catalog import CatalogQueryFacade
from ditto_application.queries.derived import DerivedQueryFacade
from ditto_application.queries.experiments import ExperimentQueryFacade
from ditto_application.queries.ingestion_status import IngestionStatusQueryFacade
from ditto_application.queries.lineage import LineageQueryFacade
from ditto_application.queries.remediation import CatalogRemediationQueryFacade
from ditto_application.queries.research_certification import (
    DataReadinessCertificationProbe,
)
from ditto_application.queries.source import SourceDataPort
from ditto_application.settings import ResearchExecutionSettings, TradingSettings
from ditto_data.catalog import InMemoryDataCatalog
from ditto_data.config.data_source import DataSourceSettings
from ditto_data.config.data_store import DataStoreSettings
from ditto_data.di import (
    CapitalProvider,
    FundamentalProvider,
    MacroProvider,
    MarketProvider,
    MetadataProvider,
    QualityProvider,
    RuntimeProvider,
)
from ditto_data.lineage import InMemoryDataLineage
from ditto_data.quality.golden import GoldenDatasetSpec
from ditto_data.quality.protocols import (
    ComparisonStoreProtocol,
    InstrumentStoreProtocol,
    TdxSourceProtocol,
)
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.sources.exchange_transformers import ExchangeTransformers
from ditto_data.sources.source import DataSources
from ditto_data.sources.tdx.source import TdxSource
from ditto_features.compile_cache import SQLiteCompileCacheBackend
from ditto_platform.foundation import DataCache, Environment
from ditto_platform.services.notification import AlertManager
from ditto_strategy.alpha.node_registry import NodeRegistry

_tdx_mock = MagicMock(spec=TdxSource)

# ---------------------------------------------------------------------------
# Test fixtures: 辅助 Provider（替代 Interfaces 层 ConfigProvider）
# ---------------------------------------------------------------------------


class _TestConfigProvider(Provider):
    """测试用最小配置 Provider — 替代 ditto_apps.registry.infra.ConfigProvider."""

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
    def data_source_settings(self) -> DataSourceSettings:
        """提供无外部凭据的测试数据源配置。"""
        return DataSourceSettings()

    @provide
    def data_root(self) -> Path:
        """提供数据根目录路径."""
        return self._data_root

    @provide
    def trading_settings(self) -> TradingSettings:
        """提供测试用交易配置."""
        return TradingSettings()

    @provide
    def research_execution_settings(self) -> ResearchExecutionSettings:
        """提供测试用 R3 研究执行 bundle 配置（默认 testing/staging sentinel 值）。"""
        return ResearchExecutionSettings()

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


class _ProtocolAdapterProvider(Provider):
    """测试用 Protocol 适配器 — 桥接 concrete mock → Protocol 接口."""

    scope = Scope.APP

    @provide
    def tdx_source_protocol(self, source: TdxSource) -> TdxSourceProtocol:
        return source

    @provide
    def comparison_store_protocol(self) -> ComparisonStoreProtocol:
        return MagicMock(spec=ComparisonStoreProtocol)

    @provide
    def instrument_store_protocol(self) -> InstrumentStoreProtocol:
        return MagicMock(spec=InstrumentStoreProtocol)

    @provide
    def compile_cache_backend(self) -> SQLiteCompileCacheBackend:
        return MagicMock(spec=SQLiteCompileCacheBackend)

    @provide
    def source_data_port(self) -> SourceDataPort:
        return MagicMock(spec=SourceDataPort)

    @provide
    def catalog_remediation_ingest_date_port(
        self,
    ) -> CatalogRemediationIngestDatePort:
        return MagicMock()


# ---------------------------------------------------------------------------
# 结构测试:验证 Provider 类拥有正确的 provide 方法
# ---------------------------------------------------------------------------


class TestAppProviderStructure:
    """验证 App 层 Provider 结构."""

    def test_get_app_providers_returns_seven_providers(self) -> None:
        """get_app_providers() 应返回 7 个 Provider 实例."""
        providers = get_app_providers()
        assert len(providers) == 7
        names = [type(p).__name__ for p in providers]
        assert "AppCommandProvider" in names
        assert "AppMarketQueryProvider" in names
        assert "AppStrategyQueryProvider" in names
        assert "AppPortfolioQueryProvider" in names
        assert "AppProcessProvider" in names
        assert "AppBuilderFactory" in names
        assert "AppResearchExecutionProvider" in names

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
            "catalog_query_facade",
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
            "experiment_query_facade",
            "lineage_query_facade",
            "catalog_remediation_query_facade",
            "comparison_query_facade",
        }
        assert expected.issubset(method_names)

    def test_experiment_query_facade_receives_analysis_reader_port(self) -> None:
        """Experiment queries must retain the injected typed read boundary."""
        provider = AppStrategyQueryProvider()
        reader = MagicMock()

        facade = provider.experiment_query_facade(reader=reader)

        assert isinstance(facade, ExperimentQueryFacade)
        assert facade._reader is reader

    def test_app_portfolio_query_provider_methods(self) -> None:
        """AppPortfolioQueryProvider 应包含组合/交易查询的 provide 方法."""
        provider = AppPortfolioQueryProvider()
        method_names = {name for name in dir(provider) if not name.startswith("_")}
        expected = {
            "daily_decision_query_facade",
            "trade_query_facade",
            "portfolio_actual_query_facade",
            "signal_query_facade",
            "signal_deviation_query_facade",
        }
        assert expected.issubset(method_names)

    def test_app_command_provider_methods(self) -> None:
        """AppCommandProvider 应包含 1 个 provide 方法."""
        provider = AppCommandProvider()
        method_names = {name for name in dir(provider) if not name.startswith("_")}
        expected = {
            "check_data_quality_handler",
            "launch_experiment_handler",
        }
        assert expected.issubset(method_names)

    def test_launch_experiment_handler_receives_planning_process(self) -> None:
        """Experiment command wiring must retain the exact planning process."""
        provider = AppCommandProvider()
        process = MagicMock()

        handler = provider.launch_experiment_handler(process=process)

        assert isinstance(handler, LaunchExperimentHandler)
        assert handler._process is process

    def test_account_baseline_handler_receives_both_aggregate_ports(self) -> None:
        """Provider wiring must preserve complete replacement audit evidence."""
        provider = AppCommandProvider()
        account_port = MagicMock()
        position_port = MagicMock()

        handler = provider.import_account_baseline_handler(
            account_port=account_port,
            position_port=position_port,
        )

        assert isinstance(handler, ImportAccountBaselineHandler)
        assert handler._account_port is account_port
        assert handler._position_port is position_port

    def test_projected_fill_correction_adapter_wires_all_atomic_ports(self) -> None:
        """Reconciliation provider must not expose a raw fill-only correction."""
        provider = AppCommandProvider()
        intent_port = MagicMock()
        fill_port = MagicMock()
        position_port = MagicMock()
        tracker = MagicMock()
        opening_baseline_resolver = MagicMock()

        adapter = provider.projected_fill_correction_adapter(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=opening_baseline_resolver,
        )

        assert isinstance(adapter, ProjectedFillCorrectionAdapter)
        assert adapter._intent is intent_port
        assert adapter._fill is fill_port
        assert adapter._position is position_port
        assert adapter._tracker is tracker
        assert adapter._opening_baseline is opening_baseline_resolver

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
            "quality_batch_coordinator",
            "quality_completeness_service",
            "quality_patrol_service",
            "research_certification_probe",
            "research_executor_probe",
            "research_validation_authority_probe",
            "experiment_planning_process",
            "manual_sizing_context_builder",
            "a_share_trade_date_resolver",
        }
        assert expected.issubset(method_names)

    def test_experiment_planning_provider_wires_exact_ports(self) -> None:
        """Planning provider must preserve reader, writer, and read-only probes."""
        provider = AppProcessProvider()
        reader = MagicMock()
        writer = MagicMock()
        certification_probe = MagicMock()
        executor_probe = MagicMock()
        authority_probe = MagicMock()

        process = provider.experiment_planning_process(
            reader=reader,
            writer=writer,
            certification_probe=certification_probe,
            executor_probe=executor_probe,
            authority_probe=authority_probe,
        )

        assert isinstance(process, ExperimentPlanningProcess)
        assert process._reader is reader
        assert process._writer is writer
        assert process._certification_probe is certification_probe
        assert process._executor_probe is executor_probe
        assert process._authority_probe is authority_probe

    def test_evidence_providers_wire_walk_forward_assembler(self) -> None:
        """Reuse one assembler/service across selection, holdout, and collector."""
        from ditto_application.processes.experiments._selection_evidence_artifact import (  # noqa: E501
            DurableSelectionEvidenceService,
        )
        from ditto_application.processes.experiments._walk_forward_evidence_collection import (  # noqa: E501
            WalkForwardEvidenceAssembler,
        )
        from ditto_application.processes.experiments.evidence_collector import (
            ExperimentEvidenceCollector,
        )
        from ditto_application.processes.experiments.r2_live_gate_evidence import (
            NullR2LiveGateEvidenceReader,
        )

        report_reader = MagicMock()
        trace_reader = MagicMock()
        semantics_resolver = MagicMock()
        assembler = AppResearchExecutionProvider().walk_forward_evidence_assembler(
            report_reader=report_reader,
            fold_selection_trace_reader=trace_reader,
            semantics_resolver=semantics_resolver,
        )
        process_provider = AppProcessProvider()
        scheduler_store = MagicMock()
        reader = MagicMock()
        artifact_service = MagicMock()
        r2_live_gate_evidence_reader = NullR2LiveGateEvidenceReader()
        selection_service = process_provider.durable_selection_evidence_service(
            scheduler_store=scheduler_store,
            reader=reader,
            research_artifact_service=artifact_service,
            walk_forward_assembler=assembler,
        )
        collector = process_provider.experiment_evidence_collector(
            scheduler_store=scheduler_store,
            reader=reader,
            writer=MagicMock(),
            walk_forward_assembler=assembler,
            selection_evidence_reader=selection_service,
            r2_live_gate_evidence_reader=r2_live_gate_evidence_reader,
        )

        assert isinstance(assembler, WalkForwardEvidenceAssembler)
        assert assembler._report_reader is report_reader
        assert assembler._fold_selection_trace_reader is trace_reader
        assert assembler._semantics_resolver is semantics_resolver
        assert isinstance(selection_service, DurableSelectionEvidenceService)
        assert selection_service.walk_forward_assembler is assembler
        assert selection_service.artifact_service is artifact_service
        assert isinstance(collector, ExperimentEvidenceCollector)
        assert collector.walk_forward_assembler is assembler
        assert collector.selection_evidence_reader is selection_service
        assert collector.r2_live_gate_evidence_reader is r2_live_gate_evidence_reader

    def test_replay_provider_wires_verified_schema_v1_reader(self) -> None:
        provider = AppProcessProvider()
        strategy_artifacts = MagicMock()
        experiment_reader = MagicMock()
        research_artifacts = MagicMock()

        verified_reader = provider.verified_replay_artifact_reader(
            strategy_artifact_service=strategy_artifacts,
            experiment_reader=experiment_reader,
            research_artifact_service=research_artifacts,
        )
        process = provider.replay_process(
            strategy_facade=MagicMock(),
            artifact_service=strategy_artifacts,
            run_model=MagicMock(),
            verified_artifact_reader=verified_reader,
        )

        assert isinstance(verified_reader, IndexedResearchReplayArtifactReader)
        assert isinstance(process, ReplayProcess)
        assert process._verified_artifact_reader is verified_reader

    def test_research_validation_authority_provider_is_production_fail_closed(
        self,
    ) -> None:
        provider = AppProcessProvider()

        authority = provider.research_validation_authority_probe()

        assert isinstance(authority, ProductionResearchValidationAuthorityProbe)

    def test_quality_batch_coordinator_provider_wires_application_dependencies(
        self,
    ) -> None:
        provider = AppProcessProvider()
        patrol = MagicMock()
        metadata = MagicMock()
        verifier = MagicMock()
        alert_manager = MagicMock()

        coordinator = provider.quality_batch_coordinator(
            quality_patrol_service=patrol,
            metadata_facade=metadata,
            evidence_verifier=verifier,
            alert_manager=alert_manager,
        )

        assert isinstance(coordinator, QualityBatchCoordinator)
        assert coordinator._patrol is patrol
        assert coordinator._metadata is metadata
        assert coordinator._evidence_verifier is verifier
        assert coordinator._alert_manager is alert_manager

    def test_quality_completeness_provider_wires_market_facade(self) -> None:
        provider = AppProcessProvider()
        market = MagicMock()

        service = provider.quality_completeness_service(market_facade=market)

        assert isinstance(service, QualityCompletenessService)
        assert service._market is market

    def test_signal_package_provider_reuses_sizing_snapshot_and_runtime_ports(
        self,
    ) -> None:
        """Publisher 必须复用带 sizing 的 snapshot，并注入 fill/date 事实源。"""
        provider_source = AppProcessProvider.__dict__["signal_package_publisher"]
        signature = inspect.signature(provider_source.origin)

        assert list(signature.parameters) == [
            "self",
            "snapshot_process",
            "intent_port",
            "fill_port",
            "date_resolver",
            "artifact_service",
        ]

    def test_materialization_orchestrator_provider_accepts_runtime_ports(self) -> None:
        """Materialization orchestrator provider should consume assembled ports."""
        provider_source = AppProcessProvider.__dict__[
            "derived_materialization_orchestrator"
        ]
        provider_origin = provider_source.origin
        signature = inspect.signature(provider_origin)
        public_params = [
            param for param in signature.parameters.values() if param.name != "self"
        ]
        hints = get_type_hints(provider_origin)

        assert [param.name for param in public_params] == ["ports"]
        assert hints["ports"] is MaterializationRuntimePorts
        assert hints["return"] is DerivedMaterializationOrchestrator

    def test_app_builder_factory_methods(self) -> None:
        """AppBuilderFactory 应包含 runtime 与 node compiler provide 方法."""
        provider = AppBuilderFactory()
        method_names = {name for name in dir(provider) if not name.startswith("_")}
        expected = {
            "node_registry",
            "node_pipeline_builder",
            "strategy_runtime_builder",
            "backtest_runtime_builder",
            "strategy_slice_builder",
            "strategy_service_factory",
            "strategy_facade",
        }
        assert expected.issubset(method_names)

    def test_lineage_query_facade_receives_data_readers(self) -> None:
        """LineageQueryFacade 应接收 data runtime 和 source-health read ports。"""
        provider = AppStrategyQueryProvider()
        lineage_reader = InMemoryDataLineage()
        catalog_reader = InMemoryDataCatalog()
        catalog_query_facade = MagicMock()
        facade = provider.lineage_query_facade(
            run_service=MagicMock(),
            data_lineage_reader=lineage_reader,
            data_catalog_reader=catalog_reader,
            catalog_query_facade=catalog_query_facade,
        )

        assert isinstance(facade, LineageQueryFacade)
        assert facade._data_lineage_reader is lineage_reader
        assert facade._data_catalog_reader is catalog_reader
        assert facade._source_health_summary_query is catalog_query_facade

    def test_catalog_query_facade_receives_data_catalog_reader(self) -> None:
        """CatalogQueryFacade 应接收 data runtime 提供的 catalog reader。"""
        provider = AppMarketQueryProvider()
        reader = InMemoryDataCatalog()
        history_reader = MagicMock()
        fallback_policy_reader = MagicMock()
        facade = provider.catalog_query_facade(
            data_catalog_reader=reader,
            maturity_promotion_history_reader=history_reader,
            catalog_source_fallback_policy_reader=fallback_policy_reader,
        )

        assert isinstance(facade, CatalogQueryFacade)
        assert facade._data_catalog_reader is reader
        assert facade._maturity_promotion_history_reader is history_reader
        assert facade._source_fallback_policy_reader is fallback_policy_reader

    def test_market_query_facade_receives_maturity_promotion_reader(self) -> None:
        """MarketQueryFacade 应接收 maturity promotion reader 以执行 read gate。"""
        provider = AppMarketQueryProvider()
        market_service = MagicMock()
        capital_store = MagicMock()
        maturity_promotion_reader = MagicMock()

        facade = provider.market_query_facade(
            market_service=market_service,
            capital_store=capital_store,
            maturity_promotion_reader=maturity_promotion_reader,
        )

        assert facade._service is market_service
        assert facade._capital_store is capital_store
        assert facade._maturity_promotion_reader is maturity_promotion_reader

    def test_source_query_facade_receives_maturity_promotion_reader(self) -> None:
        """SourceQueryFacade 应接收 maturity promotion reader 以执行 read gate。"""
        provider = AppMarketQueryProvider()
        source_data = MagicMock()
        metadata_service = MagicMock()
        maturity_promotion_reader = MagicMock()

        facade = provider.source_query_facade(
            source_data=source_data,
            metadata_service=metadata_service,
            maturity_promotion_reader=maturity_promotion_reader,
        )

        assert facade._source is source_data
        assert facade._metadata is metadata_service
        assert facade._maturity_promotion_reader is maturity_promotion_reader

    def test_fundamental_query_facade_receives_maturity_promotion_reader(self) -> None:
        """FundamentalQueryFacade 应接收 maturity promotion reader 以执行 read gate。"""
        provider = AppMarketQueryProvider()
        fundamental_store = MagicMock()
        maturity_promotion_reader = MagicMock()

        facade = provider.fundamental_query_facade(
            fundamental_store=fundamental_store,
            maturity_promotion_reader=maturity_promotion_reader,
        )

        assert facade._service is fundamental_store
        assert facade._maturity_promotion_reader is maturity_promotion_reader

    def test_capital_query_facade_receives_maturity_promotion_reader(self) -> None:
        """CapitalQueryFacade 应接收 maturity promotion reader 以执行 read gate。"""
        provider = AppMarketQueryProvider()
        capital_store = MagicMock()
        maturity_promotion_reader = MagicMock()

        facade = provider.capital_query_facade(
            capital_store=capital_store,
            maturity_promotion_reader=maturity_promotion_reader,
        )

        assert facade._service is capital_store
        assert facade._maturity_promotion_reader is maturity_promotion_reader

    def test_macro_query_facade_receives_maturity_promotion_reader(self) -> None:
        """MacroQueryFacade 应接收 maturity promotion reader 以执行 read gate。"""
        provider = AppMarketQueryProvider()
        macro_service = MagicMock()
        maturity_promotion_reader = MagicMock()

        facade = provider.macro_query_facade(
            macro_service=macro_service,
            maturity_promotion_reader=maturity_promotion_reader,
        )

        assert facade._service is macro_service
        assert facade._maturity_promotion_reader is maturity_promotion_reader

    def test_ingestion_status_query_facade_receives_data_catalog_reader(self) -> None:
        """IngestionStatusQueryFacade 应接收 catalog reader 以暴露 freshness."""
        provider = AppMarketQueryProvider()
        reader = InMemoryDataCatalog()
        promotion_reader = MagicMock()
        maturity_promotion_reader = MagicMock()
        maturity_promotion_history_reader = MagicMock()
        catalog_query_facade = MagicMock()
        facade = provider.ingestion_status_query_facade(
            ingestion_log_store=MagicMock(),
            data_catalog_reader=reader,
            promotion_evidence_reader=promotion_reader,
            maturity_promotion_reader=maturity_promotion_reader,
            maturity_promotion_history_reader=maturity_promotion_history_reader,
            catalog_query_facade=catalog_query_facade,
        )

        assert isinstance(facade, IngestionStatusQueryFacade)
        assert facade._data_catalog_reader is reader
        assert facade._promotion_evidence_reader is promotion_reader
        assert facade._maturity_promotion_reader is maturity_promotion_reader
        assert facade._maturity_promotion_history_reader is (
            maturity_promotion_history_reader
        )
        assert facade._source_health_summary_query is catalog_query_facade

    def test_catalog_remediation_query_facade_composes_existing_query_facades(
        self,
    ) -> None:
        """Remediation backlog facade should compose existing backend reports."""
        provider = AppStrategyQueryProvider()
        catalog_facade = MagicMock()
        ingestion_status_facade = MagicMock()
        lineage_facade = MagicMock()

        facade = provider.catalog_remediation_query_facade(
            catalog_query_facade=catalog_facade,
            ingestion_status_query_facade=ingestion_status_facade,
            lineage_query_facade=lineage_facade,
        )

        assert isinstance(facade, CatalogRemediationQueryFacade)
        assert facade._catalog_facade is catalog_facade
        assert facade._ingestion_status_facade is ingestion_status_facade
        assert facade._lineage_facade is lineage_facade

    def test_review_dataset_promotion_handler_receives_evidence_ports(self) -> None:
        """Promotion review handler 应接收 data-owned evidence 读写端口。"""
        provider = AppCommandProvider()
        evidence_reader = MagicMock()
        evidence_writer = MagicMock()
        maturity_promotion_reader = MagicMock()
        maturity_promotion_writer = MagicMock()

        handler = provider.review_dataset_promotion_evidence_handler(
            promotion_evidence_writer=evidence_writer,
            promotion_evidence_reader=evidence_reader,
            maturity_promotion_writer=maturity_promotion_writer,
            maturity_promotion_reader=maturity_promotion_reader,
        )

        assert isinstance(handler, ReviewDatasetPromotionEvidenceHandler)
        assert handler._evidence_writer is evidence_writer
        assert handler._evidence_reader is evidence_reader
        assert handler._maturity_promotion_writer is maturity_promotion_writer
        assert handler._maturity_promotion_reader is maturity_promotion_reader

    def test_revoke_dataset_promotion_handler_receives_reversal_ports(self) -> None:
        """Promotion revoke handler 应接收 current reader 和 revoker 端口。"""
        provider = AppCommandProvider()
        maturity_promotion_reader = MagicMock()
        maturity_promotion_revoker = MagicMock()

        handler = provider.revoke_dataset_maturity_promotion_handler(
            maturity_promotion_reader=maturity_promotion_reader,
            maturity_promotion_revoker=maturity_promotion_revoker,
        )

        assert isinstance(handler, RevokeDatasetMaturityPromotionHandler)
        assert handler._maturity_promotion_reader is maturity_promotion_reader
        assert handler._maturity_promotion_revoker is maturity_promotion_revoker

    def test_execute_remediation_approval_handler_wires_promotion_executor(
        self,
    ) -> None:
        """Remediation execution handler 应通过 application executor registry 编排。"""
        provider = AppCommandProvider()
        approval_reader = MagicMock()
        approval_writer = MagicMock()
        review_handler = MagicMock(spec=ReviewDatasetPromotionEvidenceHandler)
        ingest_date_port = MagicMock()

        handler = provider.execute_catalog_remediation_approval_handler(
            catalog_remediation_approval_reader=approval_reader,
            catalog_remediation_approval_writer=approval_writer,
            promotion_review_handler=review_handler,
            catalog_remediation_ingest_date_port=ingest_date_port,
        )

        assert isinstance(handler, ExecuteCatalogRemediationApprovalHandler)
        assert handler._approval_reader is approval_reader
        assert handler._approval_writer is approval_writer
        assert (
            handler._executor_registry.get("submit_or_fix_promotion_evidence")
            is not None
        )
        assert (
            handler._executor_registry.get("repair_catalog_source_coverage") is not None
        )
        assert handler._executor_registry.get("repair_catalog_freshness") is not None
        assert (
            handler._executor_registry.get("repair_lineage_catalog_asset") is not None
        )


# ---------------------------------------------------------------------------
# 集成测试:验证 App Provider 可以在完整容器中正确解析服务
# ---------------------------------------------------------------------------


class TestAppProviderIntegration:
    """验证 App 层 Provider 与完整容器的集成."""

    @pytest.fixture
    def app_container(self, monkeypatch, tmp_path):
        """构建包含所有层级的完整测试容器."""
        from ditto_analysis.di import AnalysisStorageProvider
        from ditto_execution.di import ExecutionStorageProvider
        from ditto_features.di import FeaturesStorageProvider
        from ditto_strategy.di.storage import StrategyStorageProvider

        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        monkeypatch.setenv("SQLITE_PATH", (tmp_path / "metadata.sqlite").as_posix())

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
            FeaturesStorageProvider(),
            AnalysisStorageProvider(),
            ExecutionStorageProvider(),
            StrategyStorageProvider(),
            _notification_provider(),
            _ProtocolAdapterProvider(),
            *get_app_providers(),
            _runtime_deps_provider(),
        )
        yield container
        container.close()

    def test_query_services_resolved(self, app_container) -> None:
        """AppMarketQueryProvider 的服务应可从容器解析."""
        assert isinstance(app_container.get(DerivedQueryFacade), DerivedQueryFacade)
        assert isinstance(app_container.get(CatalogQueryFacade), CatalogQueryFacade)
        assert isinstance(
            app_container.get(CatalogRemediationQueryFacade),
            CatalogRemediationQueryFacade,
        )
        assert isinstance(
            app_container.get(ExperimentQueryFacade),
            ExperimentQueryFacade,
        )

    def test_process_services_resolved(self, app_container) -> None:
        """AppProcessProvider 的服务应可从容器解析."""
        assert isinstance(
            app_container.get(DataReadinessCertificationProbe),
            DataReadinessCertificationProbe,
        )
        assert isinstance(
            app_container.get(BuilderBackedResearchExecutorProbe),
            BuilderBackedResearchExecutorProbe,
        )
        assert isinstance(
            app_container.get(ExperimentPlanningProcess),
            ExperimentPlanningProcess,
        )
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
        assert isinstance(
            app_container.get(QualityBatchCoordinator), QualityBatchCoordinator
        )
        assert isinstance(
            app_container.get(QualityCompletenessService),
            QualityCompletenessService,
        )
        assert isinstance(
            app_container.get(ManualSizingContextBuilder),
            ManualSizingContextBuilder,
        )
        assert isinstance(
            app_container.get(AShareTradeDateResolver),
            AShareTradeDateResolver,
        )
        assert isinstance(
            app_container.get(SignalPackagePublisher),
            SignalPackagePublisher,
        )

    def test_builder_services_resolved(self, app_container) -> None:
        """AppBuilderFactory 的服务应可从容器解析."""
        assert isinstance(app_container.get(NodeRegistry), NodeRegistry)
        assert isinstance(
            app_container.get(NodePipelineBuilder),
            NodePipelineBuilder,
        )
        assert isinstance(
            app_container.get(StrategyRuntimeBuilder),
            StrategyRuntimeBuilder,
        )
        assert isinstance(
            app_container.get(ResearchRuntimeBuilder),
            ResearchRuntimeBuilder,
        )
        assert isinstance(
            app_container.get(PublishedBaselineRuntimeBuilder),
            PublishedBaselineRuntimeBuilder,
        )
        probe = app_container.get(BuilderBackedResearchExecutorProbe)
        assert probe._builder is app_container.get(ResearchRuntimeBuilder)
        assert probe._published_baseline_builder is app_container.get(
            PublishedBaselineRuntimeBuilder
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
            app_container.get(LaunchExperimentHandler),
            LaunchExperimentHandler,
        )
        assert isinstance(
            app_container.get(CheckDataQualityHandler),
            CheckDataQualityHandler,
        )
        assert isinstance(
            app_container.get(ExecuteCatalogRemediationApprovalHandler),
            ExecuteCatalogRemediationApprovalHandler,
        )

    def test_research_execution_bundle_resolved(self, app_container) -> None:
        """AppResearchExecutionProvider 的 execution bundle 链路应可从容器解析。

        Providers 注册的是消费侧 ``__init__`` 注解用的 Protocol 类型；返回的实例
        必须是 C1/C2 的具体实现类。
        """
        from ditto_application.builders.fold_selection_trace_artifact_adapter import (
            IndexedFoldSelectionTraceArtifactAdapter,
        )
        from ditto_application.builders.research_artifact_loader import (
            IndexedBacktestReportArtifactAdapter,
            IndexedResearchArtifactLoader,
        )
        from ditto_application.builders.research_backtest_factory import (
            ExactResearchArtifactLoader,
            FrozenAuditResearchBacktestFactory,
        )
        from ditto_application.builders.research_execution_resolver import (
            DurableResearchExecutionResolver,
            ResearchExecutionRuntimeBuilders,
        )
        from ditto_application.builders.research_input_resolver import (
            IndexedResearchInputsResolver,
        )
        from ditto_application.processes.experiments._execution_resolution_evidence import (  # noqa: E501
            FrozenResearchInputsResolver,
        )
        from ditto_application.processes.experiments._fold_selection_trace_artifacts import (  # noqa: E501
            FoldSelectionTraceArtifactPublisher,
            FoldSelectionTraceArtifactReader,
        )
        from ditto_application.processes.experiments._report_evidence import (
            BacktestReportArtifactPublisher,
            BacktestReportArtifactReader,
        )
        from ditto_application.processes.experiments._selection_evidence_artifact import (  # noqa: E501
            DurableSelectionEvidenceService,
        )
        from ditto_application.processes.experiments._walk_forward_evidence_collection import (  # noqa: E501
            WalkForwardEvidenceAssembler,
        )
        from ditto_application.processes.experiments.coordinator import (
            ExperimentExecutionCoordinator,
        )
        from ditto_application.processes.experiments.evidence_collector import (
            ExperimentEvidenceCollector,
        )
        from ditto_application.processes.experiments.execution_bundle import (
            CodeEnvironmentLock,
        )
        from ditto_application.processes.experiments.worker import (
            ExecutionBundleFirstAttemptFactory,
            ExistingBacktestResearchFoldRunner,
            ResearchBacktestServiceFactory,
            ResearchExecutionSemanticsResolver,
        )

        assert isinstance(
            app_container.get(FrozenResearchInputsResolver),
            IndexedResearchInputsResolver,
        )
        assert isinstance(
            app_container.get(ExactResearchArtifactLoader),
            IndexedResearchArtifactLoader,
        )
        assert isinstance(
            app_container.get(CodeEnvironmentLock),
            CodeEnvironmentLock,
        )
        assert isinstance(
            app_container.get(ResearchExecutionRuntimeBuilders),
            ResearchExecutionRuntimeBuilders,
        )
        assert isinstance(
            app_container.get(ResearchExecutionSemanticsResolver),
            DurableResearchExecutionResolver,
        )
        assert isinstance(
            app_container.get(ResearchBacktestServiceFactory),
            FrozenAuditResearchBacktestFactory,
        )
        assert isinstance(
            app_container.get(ResearchFoldRunner),
            ExistingBacktestResearchFoldRunner,
        )
        report_adapter = app_container.get(IndexedBacktestReportArtifactAdapter)
        assert isinstance(report_adapter, IndexedBacktestReportArtifactAdapter)
        assert app_container.get(BacktestReportArtifactPublisher) is report_adapter
        assert app_container.get(BacktestReportArtifactReader) is report_adapter
        trace_adapter = app_container.get(IndexedFoldSelectionTraceArtifactAdapter)
        assert isinstance(
            trace_adapter,
            IndexedFoldSelectionTraceArtifactAdapter,
        )
        assert app_container.get(FoldSelectionTraceArtifactPublisher) is trace_adapter
        assert app_container.get(FoldSelectionTraceArtifactReader) is trace_adapter
        assembler = app_container.get(WalkForwardEvidenceAssembler)
        assert isinstance(assembler, WalkForwardEvidenceAssembler)
        selection_service = app_container.get(DurableSelectionEvidenceService)
        assert isinstance(selection_service, DurableSelectionEvidenceService)
        assert selection_service.walk_forward_assembler is assembler
        collector = app_container.get(ExperimentEvidenceCollector)
        assert isinstance(collector, ExperimentEvidenceCollector)
        assert collector.walk_forward_assembler is assembler
        assert collector.selection_evidence_reader is selection_service
        coordinator = app_container.get(ExperimentExecutionCoordinator)
        assert coordinator._selection_evidence_publisher is selection_service
        assert (
            coordinator._holdout._process._selection_evidence_provider
            is selection_service
        )
        assert isinstance(
            app_container.get(FirstAttemptFactory),
            ExecutionBundleFirstAttemptFactory,
        )
        worker = app_container.get(ResearchExperimentWorker)
        assert isinstance(worker, ResearchExperimentWorker)

    def test_coordinator_uses_execution_bundle_factory(self, app_container) -> None:
        """FirstAttemptFactory resolves to the real execution bundle factory."""
        from ditto_application.processes.experiments.worker import (
            ExecutionBundleFirstAttemptFactory,
        )

        factory = app_container.get(FirstAttemptFactory)
        assert isinstance(factory, ExecutionBundleFirstAttemptFactory)

    def test_manual_tracker_receives_trading_calendar(self, app_container) -> None:
        """ManualTracker 应从 MetadataService 加载交易日历（非空 tuple）."""
        from ditto_application.processes.execution.manual_tracker import ManualTracker

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
        from ditto_application.providers import get_trading_calendar_range
        from ditto_application.settings import TradingSettings

        settings = TradingSettings()
        start, end = get_trading_calendar_range(settings)
        assert start == "2020-01-01"
        assert end == "2030-12-31"

    def test_custom_values(self) -> None:
        """自定义 TradingSettings 应返回自定义日期范围."""
        from ditto_application.providers import get_trading_calendar_range
        from ditto_application.settings import TradingSettings

        settings = TradingSettings(
            trading_calendar_start="2019-06-01",
            trading_calendar_end="2040-06-30",
        )
        start, end = get_trading_calendar_range(settings)
        assert start == "2019-06-01"
        assert end == "2040-06-30"

    def test_only_start_customized(self) -> None:
        """仅自定义 START 时 END 应保持默认值."""
        from ditto_application.providers import get_trading_calendar_range
        from ditto_application.settings import TradingSettings

        settings = TradingSettings(trading_calendar_start="2018-01-01")
        start, end = get_trading_calendar_range(settings)
        assert start == "2018-01-01"
        assert end == "2030-12-31"

    def test_env_alias_populates_settings(self) -> None:
        """TradingSettings 应通过构造参数覆盖默认值."""
        from ditto_application.settings import TradingSettings

        settings = TradingSettings(
            trading_calendar_start="2021-03-01",
            trading_calendar_end="2035-06-30",
        )
        assert settings.trading_calendar_start == "2021-03-01"
        assert settings.trading_calendar_end == "2035-06-30"
