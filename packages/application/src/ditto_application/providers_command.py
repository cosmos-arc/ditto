"""Command 层 DI Provider — Command Handler 注册。"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_data.catalog.fallback_policy import (
    CatalogSourceFallbackPolicyReader,
    CatalogSourceFallbackPolicyWriter,
)
from ditto_data.catalog.promotion import (
    DatasetMaturityPromotionReader,
    DatasetMaturityPromotionRevoker,
    DatasetMaturityPromotionWriter,
    DatasetPromotionEvidenceReader,
    DatasetPromotionEvidenceWriter,
)
from ditto_data.catalog.remediation import (
    CatalogRemediationApprovalReader,
    CatalogRemediationApprovalWriter,
)
from ditto_data.ingestion.quality_record_store import (
    QualityRecordStore,
)
from ditto_data.quality import QualityEngine
from ditto_data.quality.golden import GoldenDatasetSpec
from ditto_data.quality.protocols import (
    ComparisonStoreProtocol,
    InstrumentStoreProtocol,
    TdxSourceProtocol,
)
from ditto_data.services.metadata_service import MetadataService
from ditto_execution.contracts import (
    AccountDataPort,
    FillDataPort,
    IntentDataPort,
    PositionDataPort,
)
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
from ditto_application.commands.catalog import (
    ReviewDatasetPromotionEvidenceHandler,
    RevokeDatasetMaturityPromotionHandler,
)
from ditto_application.commands.catalog_remediation import (
    CatalogFreshnessRemediationExecutor,
    CatalogRemediationActionExecutorRegistry,
    CatalogRemediationIngestDatePort,
    CatalogSourceCoverageRemediationExecutor,
    DatasetPromotionEvidenceRemediationExecutor,
    DecideCatalogRemediationApprovalHandler,
    ExecuteCatalogRemediationApprovalHandler,
    LineageCatalogAssetRemediationExecutor,
    RequestCatalogRemediationApprovalHandler,
)
from ditto_application.commands.quality_check import CheckDataQualityHandler
from ditto_application.commands.quality_reconciliation import ReconcileSourcesHandler
from ditto_application.commands.source_fallback_policy import (
    ActivateCatalogSourceFallbackPolicyHandler,
    ApproveCatalogSourceFallbackPolicyHandler,
    DraftCatalogSourceFallbackPolicyHandler,
    RetireCatalogSourceFallbackPolicyHandler,
)
from ditto_application.commands.strategy import (
    CreateStrategyHandler,
    PublishStrategyHandler,
    UpdateStrategyHandler,
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
from ditto_application.queries.account import AccountBaselineQuery
from ditto_application.queries.opening_baseline import OpeningBaselineResolver


class AppCommandProvider(Provider):
    """App Command 层 DI Provider — Command Handler 注册。"""

    scope = Scope.APP

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
    def reconcile_sources_handler(
        self,
        dq_engine: QualityEngine,
        tdx_source: TdxSourceProtocol,
        comparison_store: ComparisonStoreProtocol,
        instrument_store: InstrumentStoreProtocol,
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
    def review_dataset_promotion_evidence_handler(
        self,
        promotion_evidence_writer: DatasetPromotionEvidenceWriter,
        promotion_evidence_reader: DatasetPromotionEvidenceReader,
        maturity_promotion_writer: DatasetMaturityPromotionWriter,
        maturity_promotion_reader: DatasetMaturityPromotionReader,
    ) -> ReviewDatasetPromotionEvidenceHandler:
        """Dataset promotion reviewer evidence handler."""
        return ReviewDatasetPromotionEvidenceHandler(
            evidence_writer=promotion_evidence_writer,
            evidence_reader=promotion_evidence_reader,
            maturity_promotion_writer=maturity_promotion_writer,
            maturity_promotion_reader=maturity_promotion_reader,
        )

    @provide
    def revoke_dataset_maturity_promotion_handler(
        self,
        maturity_promotion_reader: DatasetMaturityPromotionReader,
        maturity_promotion_revoker: DatasetMaturityPromotionRevoker,
    ) -> RevokeDatasetMaturityPromotionHandler:
        """Dataset maturity promotion reversal handler."""
        return RevokeDatasetMaturityPromotionHandler(
            maturity_promotion_reader=maturity_promotion_reader,
            maturity_promotion_revoker=maturity_promotion_revoker,
        )

    @provide
    def request_catalog_remediation_approval_handler(
        self,
        catalog_remediation_approval_writer: CatalogRemediationApprovalWriter,
    ) -> RequestCatalogRemediationApprovalHandler:
        """Catalog remediation approval request handler."""
        return RequestCatalogRemediationApprovalHandler(
            approval_writer=catalog_remediation_approval_writer,
        )

    @provide
    def draft_catalog_source_fallback_policy_handler(
        self,
        catalog_source_fallback_policy_writer: CatalogSourceFallbackPolicyWriter,
    ) -> DraftCatalogSourceFallbackPolicyHandler:
        """Catalog source fallback policy draft handler."""
        return DraftCatalogSourceFallbackPolicyHandler(
            policy_writer=catalog_source_fallback_policy_writer,
        )

    @provide
    def approve_catalog_source_fallback_policy_handler(
        self,
        catalog_source_fallback_policy_reader: CatalogSourceFallbackPolicyReader,
        catalog_source_fallback_policy_writer: CatalogSourceFallbackPolicyWriter,
    ) -> ApproveCatalogSourceFallbackPolicyHandler:
        """Catalog source fallback policy approval handler."""
        return ApproveCatalogSourceFallbackPolicyHandler(
            policy_reader=catalog_source_fallback_policy_reader,
            policy_writer=catalog_source_fallback_policy_writer,
        )

    @provide
    def activate_catalog_source_fallback_policy_handler(
        self,
        catalog_source_fallback_policy_reader: CatalogSourceFallbackPolicyReader,
        catalog_source_fallback_policy_writer: CatalogSourceFallbackPolicyWriter,
    ) -> ActivateCatalogSourceFallbackPolicyHandler:
        """Catalog source fallback policy activation handler."""
        return ActivateCatalogSourceFallbackPolicyHandler(
            policy_reader=catalog_source_fallback_policy_reader,
            policy_writer=catalog_source_fallback_policy_writer,
        )

    @provide
    def retire_catalog_source_fallback_policy_handler(
        self,
        catalog_source_fallback_policy_reader: CatalogSourceFallbackPolicyReader,
        catalog_source_fallback_policy_writer: CatalogSourceFallbackPolicyWriter,
    ) -> RetireCatalogSourceFallbackPolicyHandler:
        """Catalog source fallback policy retirement handler."""
        return RetireCatalogSourceFallbackPolicyHandler(
            policy_reader=catalog_source_fallback_policy_reader,
            policy_writer=catalog_source_fallback_policy_writer,
        )

    @provide
    def decide_catalog_remediation_approval_handler(
        self,
        catalog_remediation_approval_reader: CatalogRemediationApprovalReader,
        catalog_remediation_approval_writer: CatalogRemediationApprovalWriter,
    ) -> DecideCatalogRemediationApprovalHandler:
        """Catalog remediation approval decision handler."""
        return DecideCatalogRemediationApprovalHandler(
            approval_reader=catalog_remediation_approval_reader,
            approval_writer=catalog_remediation_approval_writer,
        )

    @provide
    def execute_catalog_remediation_approval_handler(
        self,
        catalog_remediation_approval_reader: CatalogRemediationApprovalReader,
        catalog_remediation_approval_writer: CatalogRemediationApprovalWriter,
        promotion_review_handler: ReviewDatasetPromotionEvidenceHandler,
        catalog_remediation_ingest_date_port: CatalogRemediationIngestDatePort,
    ) -> ExecuteCatalogRemediationApprovalHandler:
        """Catalog remediation approval-backed execution handler."""
        return ExecuteCatalogRemediationApprovalHandler(
            approval_reader=catalog_remediation_approval_reader,
            approval_writer=catalog_remediation_approval_writer,
            executor_registry=CatalogRemediationActionExecutorRegistry(
                (
                    DatasetPromotionEvidenceRemediationExecutor(
                        promotion_review_handler
                    ),
                    CatalogSourceCoverageRemediationExecutor(
                        catalog_remediation_ingest_date_port
                    ),
                    CatalogFreshnessRemediationExecutor(
                        catalog_remediation_ingest_date_port
                    ),
                    LineageCatalogAssetRemediationExecutor(
                        catalog_remediation_ingest_date_port
                    ),
                )
            ),
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
