"""Command 层 DI Provider — Command Handler 注册。"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_data.ingestion.quality_record_service import QualityRecordService
from ditto_data.quality import QualityEngine
from ditto_data.quality.golden import GoldenDatasetSpec
from ditto_data.services.metadata_service import MetadataService
from ditto_data.sources.tdx.source import TdxSource
from ditto_data.storage.metadata.instrument import InstrumentReader
from ditto_data.storage.runtime.quality import ComparisonWriter
from ditto_execution.contracts import TradeDataPort
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunLifecycleStore,
)

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
from ditto_application.processes.execution.strategy_types import RunLifecycleService


class AppCommandProvider(Provider):
    """App Command 层 DI Provider — Command Handler 注册。"""

    scope = Scope.APP

    @provide
    def check_data_quality_handler(
        self,
        dq_engine: QualityEngine,
        quality_record_service: QualityRecordService,
    ) -> CheckDataQualityHandler:
        """数据质量检查 Handler."""
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
        """数据源对账 Handler."""
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
        """策略创建 Handler."""
        return CreateStrategyHandler(catalog_service=catalog_service)

    @provide
    def update_strategy_handler(
        self,
        catalog_service: StrategyCatalogService,
    ) -> UpdateStrategyHandler:
        """策略更新 Handler."""
        return UpdateStrategyHandler(catalog_service=catalog_service)

    @provide
    def publish_strategy_handler(
        self,
        catalog_service: StrategyCatalogService,
    ) -> PublishStrategyHandler:
        """策略发布 Handler."""
        return PublishStrategyHandler(catalog_service=catalog_service)

    @provide
    def record_fill_handler(
        self,
        trade_service: TradeDataPort,
        manual_tracker: ManualTracker,
    ) -> RecordFillHandler:
        """成交录入 Handler."""
        return RecordFillHandler(
            trade_service=trade_service,
            manual_tracker=manual_tracker,
        )

    @provide
    def update_intent_status_handler(
        self,
        trade_service: TradeDataPort,
    ) -> UpdateIntentStatusHandler:
        """交易意图状态更新 Handler."""
        return UpdateIntentStatusHandler(trade_service=trade_service)

    @provide
    def backtest_run_handler(
        self,
        catalog_service: StrategyCatalogService,
        run_service: StrategyRunLifecycleStore,
        factor_bridge: FactorBridge,
    ) -> BacktestRunHandler:
        """回测运行触发 Handler."""
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
        """回测运行取消 Handler."""
        return CancelRunHandler(run_service=run_service)

    @provide
    def retry_run_handler(
        self,
        run_service: StrategyRunLifecycleStore,
    ) -> RetryRunHandler:
        """回测运行重试 Handler."""
        return RetryRunHandler(run_service=run_service)

    @provide
    def run_lifecycle_service(
        self,
        run_service: StrategyRunLifecycleStore,
    ) -> RunLifecycleService:
        """策略运行生命周期服务."""
        return run_service

    @provide
    def create_custom_universe_handler(
        self,
        metadata_service: MetadataService,
    ) -> CreateCustomUniverseHandler:
        """自定义 Universe 创建 Handler."""
        return CreateCustomUniverseHandler(metadata_service=metadata_service)

    @provide
    def update_custom_universe_handler(
        self,
        metadata_service: MetadataService,
    ) -> UpdateCustomUniverseHandler:
        """自定义 Universe 更新 Handler."""
        return UpdateCustomUniverseHandler(metadata_service=metadata_service)

    @provide
    def delete_custom_universe_handler(
        self,
        metadata_service: MetadataService,
    ) -> DeleteCustomUniverseHandler:
        """自定义 Universe 删除 Handler."""
        return DeleteCustomUniverseHandler(metadata_service=metadata_service)
