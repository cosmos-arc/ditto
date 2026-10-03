"""Command 层 DI Provider — Command Handler 注册。"""

from __future__ import annotations

import polars as pl
from dishka import Provider, Scope, provide
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.ingestion.quality_record_store import (
    QualityRecordStore,
)
from ditto_data.quality import QualityEngine
from ditto_data.quality.golden import GoldenDatasetSpec
from ditto_data.quality.protocols import (
    ComparisonStoreProtocol,
    ExDividendInstrumentSourceProtocol,
    InstrumentStoreProtocol,
    SecondaryBarsSourceProtocol,
    SecondaryIdentityResolverProtocol,
)
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_execution.contracts import (
    AccountDataPort,
    FillDataPort,
    IntentDataPort,
    PositionDataPort,
)
from ditto_strategy.governance.service import GovernanceService
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunCheckpointStore,
    StrategyRunLifecycleStore,
)

from ditto_application.commands.account import ImportAccountBaselineHandler
from ditto_application.commands.backtest import (
    BacktestRunHandler,
    CancelRunHandler,
    ResumeRunHandler,
    RetryRunHandler,
)
from ditto_application.commands.candidate_selection import (
    CandidateSelectionHandler,
)
from ditto_application.commands.experiments import (
    CancelExperimentHandler,
    ClaimHoldoutCandidateHandler,
    ExperimentControlNotifier,
    LaunchExperimentHandler,
    PauseExperimentHandler,
    ResumeExperimentHandler,
    RetryExperimentFoldHandler,
)
from ditto_application.commands.quality_check import CheckDataQualityHandler
from ditto_application.commands.quality_reconciliation import ReconcileSourcesHandler
from ditto_application.commands.research_dataset_export import ResearchDatasetExport
from ditto_application.commands.strategy import (
    CreateStrategyHandler,
    PublishStrategyHandler,
    UpdateStrategyHandler,
)
from ditto_application.commands.strategy_governance import (
    ApproveReviewHandler,
    DeprecateStrategyHandler,
    PublishStrategyVersionHandler,
    ReactivateStrategyHandler,
    RejectReviewHandler,
    ReviewPacketReader,
    SubmitReviewHandler,
)
from ditto_application.commands.trade import (
    ProjectedFillAppendAdapter,
    ProjectedFillCorrectionAdapter,
    RecordFillHandler,
    ReplaceFillHandler,
    UpdateIntentStatusHandler,
    VoidFillHandler,
)
from ditto_application.commands.universe import (
    CreateCustomUniverseHandler,
    DeleteCustomUniverseHandler,
    UpdateCustomUniverseHandler,
)
from ditto_application.opening_baseline import OpeningBaselinePort
from ditto_application.processes.execution.factor_bridge import FactorBridge
from ditto_application.processes.execution.manual_tracker import ManualTracker
from ditto_application.processes.execution.strategy_types import RunLifecycleService
from ditto_application.processes.experiments.coordinator import (
    ExperimentExecutionCoordinator,
)
from ditto_application.processes.experiments.planning_process import (
    ExperimentPlanningProcess,
)
from ditto_application.processes.strategy.promotion import (
    StrategyPromotionProcess,
)
from ditto_application.queries.account import AccountBaselineQuery
from ditto_application.queries.opening_baseline import OpeningBaselineResolver


class _MetadataSecondaryIdentityResolver:
    """辅源身份只读反解：fuyao 映射优先，裸码前缀规则唯一匹配兜底。"""

    def __init__(self, metadata: MetadataService) -> None:
        self._metadata = metadata

    def resolve_secondary_ids(
        self, source_tickers: list[str], source: str
    ) -> dict[str, int]:
        """裸码/thscode → instrument_id（只读，不写映射；键与输入一致）。"""
        if source != "fuyao" or not source_tickers:
            return {}
        return self._metadata.instrument.resolve_fuyao_instrument_ids(
            [str(ticker) for ticker in source_tickers],
            register_missing=False,
        )


class _AdjFactorExDividendSource:
    """除权日（adj_factor 事件日）标的：当日因子 ≠ 此前最近因子。"""

    _LOOKBACK_DAYS = 40
    _FACTOR_EPSILON = 1e-12

    def __init__(self, market: MarketService) -> None:
        self._market = market

    def ex_dividend_instruments(self, trade_date: str) -> frozenset[int]:
        """返回该交易日 adj_factor 发生变化的 instrument_id 集合。"""
        from datetime import date, timedelta  # noqa: PLC0415 - 局部工具导入

        target = date.fromisoformat(trade_date)
        start = (target - timedelta(days=self._LOOKBACK_DAYS)).isoformat()
        frame = self._market.get_adj_factors(start, trade_date)
        required = {"instrument_id", "trade_date", "adj_factor"}
        if frame.is_empty() or not required.issubset(frame.columns):
            return frozenset()
        if frame["trade_date"].dtype == pl.String:
            frame = frame.with_columns(pl.col("trade_date").str.to_date())
        current = frame.filter(pl.col("trade_date") == target)
        previous = frame.filter(pl.col("trade_date") < target)
        if current.is_empty() or previous.is_empty():
            return frozenset()
        previous_latest = (
            previous.sort("trade_date")
            .group_by("instrument_id")
            .agg(pl.col("adj_factor").last().alias("prev_factor"))
        )
        joined = current.join(previous_latest, on="instrument_id", how="inner")
        changed = joined.filter(
            (pl.col("adj_factor") - pl.col("prev_factor")).abs() > self._FACTOR_EPSILON
        )
        return frozenset(int(v) for v in changed["instrument_id"].to_list())


class AppCommandProvider(Provider):
    """App Command 层 DI Provider — Command Handler 注册。"""

    scope = Scope.APP

    @provide
    def research_dataset_export(
        self,
        research_artifact_service: ResearchArtifactService,
        research_catalog_service: ResearchCatalogService,
        snapshots: ProviderSnapshotReader,
    ) -> ResearchDatasetExport:
        """Wire saved snapshot export with minimal usage constraints."""
        return ResearchDatasetExport(
            research_artifact_service=research_artifact_service,
            research_catalog_service=research_catalog_service,
            snapshots=snapshots,
        )

    @provide
    def candidate_selection_handler(
        self,
        process: ExperimentExecutionCoordinator,
    ) -> CandidateSelectionHandler:
        """Expose durable server-side preselection through the coordinator lease."""
        return CandidateSelectionHandler(process)

    @provide
    def launch_experiment_handler(
        self,
        process: ExperimentPlanningProcess,
    ) -> LaunchExperimentHandler:
        """Expose confirmed experiment launch through the command boundary."""
        return LaunchExperimentHandler(process)

    @provide
    def pause_experiment_handler(
        self,
        process: ExperimentExecutionCoordinator,
        notifier: ExperimentControlNotifier,
    ) -> PauseExperimentHandler:
        """Persist pause intent, then notify each persisted live run to stop."""
        return PauseExperimentHandler(process=process, notifier=notifier)

    @provide
    def cancel_experiment_handler(
        self,
        process: ExperimentExecutionCoordinator,
        notifier: ExperimentControlNotifier,
    ) -> CancelExperimentHandler:
        """Persist cancel intent, then notify each persisted live run to stop."""
        return CancelExperimentHandler(process=process, notifier=notifier)

    @provide
    def resume_experiment_handler(
        self,
        process: ExperimentExecutionCoordinator,
        notifier: ExperimentControlNotifier,
    ) -> ResumeExperimentHandler:
        """Persist resume intent, then wake the scheduler for one paused experiment."""
        return ResumeExperimentHandler(process=process, notifier=notifier)

    @provide
    def retry_experiment_fold_handler(
        self,
        process: ExperimentExecutionCoordinator,
        notifier: ExperimentControlNotifier,
    ) -> RetryExperimentFoldHandler:
        """Persist one fold retry intent, then wake the scheduler to dispatch it."""
        return RetryExperimentFoldHandler(process=process, notifier=notifier)

    @provide
    def claim_holdout_candidate_handler(
        self,
        process: ExperimentExecutionCoordinator,
        notifier: ExperimentControlNotifier,
    ) -> ClaimHoldoutCandidateHandler:
        """Commit one holdout claim, then wake the scheduler for dispatch."""
        return ClaimHoldoutCandidateHandler(process=process, notifier=notifier)

    @provide
    def opening_baseline_resolver(
        self,
        account_query: AccountBaselineQuery,
        artifact_service: StrategyArtifactService,
    ) -> OpeningBaselinePort:
        """Resolve one manual intent to its exact account opening aggregate."""
        return OpeningBaselineResolver(
            account_query=account_query,
            package_reader=artifact_service,
        )

    @provide
    def import_account_baseline_handler(
        self,
        account_port: AccountDataPort,
        position_port: PositionDataPort,
    ) -> ImportAccountBaselineHandler:
        """账户与持仓期初基线导入 Handler."""
        return ImportAccountBaselineHandler(
            account_port=account_port,
            position_port=position_port,
        )

    @provide
    def check_data_quality_handler(
        self,
        dq_engine: QualityEngine,
        quality_record_store: QualityRecordStore,
    ) -> CheckDataQualityHandler:
        """数据质量检查 Handler."""
        return CheckDataQualityHandler(
            engine=dq_engine,
            quarantine_writer=quality_record_store,
        )

    @provide
    def secondary_identity_resolver(
        self,
        metadata: MetadataService,
    ) -> SecondaryIdentityResolverProtocol:
        """辅源身份只读反解（#395 来源映射 → instrument_id）。"""
        return _MetadataSecondaryIdentityResolver(metadata)

    @provide
    def ex_dividend_instrument_source(
        self,
        market: MarketService,
    ) -> ExDividendInstrumentSourceProtocol:
        """除权日（adj_factor 事件日）标的来源。"""
        return _AdjFactorExDividendSource(market)

    @provide
    def reconcile_sources_handler(
        self,
        dq_engine: QualityEngine,
        secondary_source: SecondaryBarsSourceProtocol,
        comparison_store: ComparisonStoreProtocol,
        instrument_store: InstrumentStoreProtocol,
        secondary_identity_resolver: SecondaryIdentityResolverProtocol,
        ex_dividend_source: ExDividendInstrumentSourceProtocol,
        golden_dataset: GoldenDatasetSpec | None,
    ) -> ReconcileSourcesHandler:
        """
        数据源对账 Handler（辅源身份反解 + 除权日标记 + 黄金集过滤，#395）。

        golden_dataset 以必填 Optional 注入：黄金集配置由 GoldenDatasetProvider
        提供（无配置文件时为 None = 不过滤），修复此前默认参数导致的
        生产路径黄金集过滤从未生效的问题。
        """
        return ReconcileSourcesHandler(
            engine=dq_engine,
            secondary_source=secondary_source,
            comparison_store=comparison_store,
            instrument_store=instrument_store,
            secondary_identity_resolver=secondary_identity_resolver,
            ex_dividend_source=ex_dividend_source,
            golden_dataset=golden_dataset,
        )

    @provide
    def create_strategy_handler(
        self,
        governance_service: GovernanceService,
    ) -> CreateStrategyHandler:
        """策略创建 Handler（governance-backed append-only）."""
        return CreateStrategyHandler(governance=governance_service)

    @provide
    def update_strategy_handler(
        self,
        catalog_service: StrategyCatalogService,
        governance_service: GovernanceService,
    ) -> UpdateStrategyHandler:
        """策略更新 Handler（catalog 读 existing + governance 写 draft）."""
        return UpdateStrategyHandler(
            catalog_service=catalog_service,
            governance=governance_service,
        )

    @provide
    def publish_strategy_handler(
        self,
        governance_service: GovernanceService,
    ) -> PublishStrategyHandler:
        """策略发布 Handler（governance publish_and_activate）."""
        return PublishStrategyHandler(governance=governance_service)

    @provide
    def submit_review_handler(
        self,
        governance_service: GovernanceService,
        reader: ReviewPacketReader,
    ) -> SubmitReviewHandler:
        """策略版本提交审查 Handler（governance submit_review）."""
        return SubmitReviewHandler(governance=governance_service, reader=reader)

    @provide
    def approve_review_handler(
        self,
        governance_service: GovernanceService,
    ) -> ApproveReviewHandler:
        """策略版本审批 Handler（governance approve）."""
        return ApproveReviewHandler(governance=governance_service)

    @provide
    def reject_review_handler(
        self,
        governance_service: GovernanceService,
    ) -> RejectReviewHandler:
        """策略版本驳回 Handler（governance reject）."""
        return RejectReviewHandler(governance=governance_service)

    @provide
    def deprecate_strategy_handler(
        self,
        governance_service: GovernanceService,
    ) -> DeprecateStrategyHandler:
        """策略版本弃用 Handler（governance deprecate）."""
        return DeprecateStrategyHandler(governance=governance_service)

    @provide
    def reactivate_strategy_handler(
        self,
        governance_service: GovernanceService,
    ) -> ReactivateStrategyHandler:
        """策略版本重新激活 Handler（governance activate + expected pointer CAS）."""
        return ReactivateStrategyHandler(governance=governance_service)

    @provide
    def publish_strategy_version_handler(
        self,
        process: StrategyPromotionProcess,
        reader: ReviewPacketReader,
    ) -> PublishStrategyVersionHandler:
        """Promote one reviewed version after evidence-gated validation."""
        return PublishStrategyVersionHandler(process=process, reader=reader)

    @provide
    def record_fill_handler(
        self,
        intent_port: IntentDataPort,
        fill_port: FillDataPort,
        position_port: PositionDataPort,
        manual_tracker: ManualTracker,
        opening_baseline_resolver: OpeningBaselinePort,
        projected_fill_adapter: ProjectedFillAppendAdapter,
    ) -> RecordFillHandler:
        """成交录入 Handler."""
        return RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=manual_tracker,
            opening_baseline_resolver=opening_baseline_resolver,
            projected_fill_adapter=projected_fill_adapter,
        )

    @provide
    def projected_fill_append_adapter(
        self,
        intent_port: IntentDataPort,
        fill_port: FillDataPort,
        position_port: PositionDataPort,
        manual_tracker: ManualTracker,
        opening_baseline_resolver: OpeningBaselinePort,
    ) -> ProjectedFillAppendAdapter:
        """Broker/manual fill append adapter with atomic derived projections."""
        return ProjectedFillAppendAdapter(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=manual_tracker,
            opening_baseline_resolver=opening_baseline_resolver,
        )

    @provide
    def void_fill_handler(
        self,
        intent_port: IntentDataPort,
        fill_port: FillDataPort,
        position_port: PositionDataPort,
        manual_tracker: ManualTracker,
        opening_baseline_resolver: OpeningBaselinePort,
    ) -> VoidFillHandler:
        """Append-only 成交作废 Handler。"""
        return VoidFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=manual_tracker,
            opening_baseline_resolver=opening_baseline_resolver,
        )

    @provide
    def replace_fill_handler(
        self,
        intent_port: IntentDataPort,
        fill_port: FillDataPort,
        position_port: PositionDataPort,
        manual_tracker: ManualTracker,
        opening_baseline_resolver: OpeningBaselinePort,
    ) -> ReplaceFillHandler:
        """Append-only 成交替换 Handler。"""
        return ReplaceFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=manual_tracker,
            opening_baseline_resolver=opening_baseline_resolver,
        )

    @provide
    def projected_fill_correction_adapter(
        self,
        intent_port: IntentDataPort,
        fill_port: FillDataPort,
        position_port: PositionDataPort,
        manual_tracker: ManualTracker,
        opening_baseline_resolver: OpeningBaselinePort,
    ) -> ProjectedFillCorrectionAdapter:
        """为 reconciliation 提供原子 ledger + projection 修正适配器。"""
        return ProjectedFillCorrectionAdapter(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=manual_tracker,
            opening_baseline_resolver=opening_baseline_resolver,
        )

    @provide
    def update_intent_status_handler(
        self,
        intent_port: IntentDataPort,
    ) -> UpdateIntentStatusHandler:
        """交易意图状态更新 Handler."""
        return UpdateIntentStatusHandler(intent_port=intent_port)

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
    def resume_run_handler(
        self,
        run_service: StrategyRunLifecycleStore,
        checkpoint_store: StrategyRunCheckpointStore,
    ) -> ResumeRunHandler:
        """回测运行 checkpoint 恢复 Handler."""
        return ResumeRunHandler(
            run_service=run_service,
            checkpoint_reader=checkpoint_store,
        )

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
