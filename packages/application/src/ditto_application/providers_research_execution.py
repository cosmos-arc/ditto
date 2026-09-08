"""
R3 研究执行 bundle 的 DI Provider — 把 C1 frozen builders 装配成 execution graph。

这个模块是 R3 execution bundle wiring 的 composition 边界：它把 C1 已经验证的
``IndexedResearchInputsResolver`` / ``IndexedResearchArtifactLoader`` /
``build_code_environment_lock`` 与 durable execution resolver、frozen audit
backtest factory、first attempt factory 和 fold worker 串成一条从 coordinator 到
``ResearchExperimentWorker`` 的完整尝试分发链路。

约束：
- 只做 wiring（构造对象、注入依赖），不包含业务逻辑。
- 不读 git/lockfile（application 层禁做 git I/O）；``CodeEnvironmentLock`` 从
  :class:`ResearchExecutionSettings` 读 code_version + environment_lock_hash，由
  apps composition root（C3）从真实 git HEAD + Python 环境身份摘要 写入。
- 通过 Protocol 类型（``FrozenResearchInputsResolver`` 等）注册，让消费侧的
  ``__init__`` 类型注解能直接解析到这些实例。
"""

from __future__ import annotations

from functools import partial

from dishka import Provider, Scope, provide
from ditto_analysis.experiments import ExperimentReaderProtocol
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_features.factors.core_daily_catalog import R3_CORE_FACTOR_CATALOG
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunCheckpointReaderProtocol,
    StrategyRunCheckpointStore,
    StrategyRunCheckpointWriterProtocol,
)

from ditto_application.builders import (
    IndexedBacktestReportArtifactAdapter,
    IndexedFoldSelectionTraceArtifactAdapter,
    IndexedResearchArtifactLoader,
    IndexedResearchInputsResolver,
    PublishedBaselineRuntimeBuilder,
    ResearchEvidenceReplayRuntimeBuilder,
    ResearchRuntimeBuilder,
    build_code_environment_lock,
)
from ditto_application.builders.research_backtest_factory import (
    ExactResearchArtifactLoader,
    FrozenAuditResearchBacktestFactory,
)
from ditto_application.builders.research_execution_resolver import (
    DurableResearchExecutionResolver,
    ResearchExecutionRuntimeBuilders,
)
from ditto_application.commands.candidate_selection import CandidateSelectionProcess
from ditto_application.processes.experiments._control_runtime import (
    CONTROL_COORDINATOR_LEASE_DURATION,
    CONTROL_COORDINATOR_OWNER_TOKEN,
)
from ditto_application.processes.experiments._execution_resolution_evidence import (
    FrozenResearchInputsResolver,
)
from ditto_application.processes.experiments._fold_selection_trace_artifacts import (
    FoldSelectionTraceArtifactPublisher,
    FoldSelectionTraceArtifactReader,
)
from ditto_application.processes.experiments._report_evidence import (
    BacktestReportArtifactPublisher,
    BacktestReportArtifactReader,
)
from ditto_application.processes.experiments._selection_evidence_artifact import (
    DurableSelectionEvidenceService,
)
from ditto_application.processes.experiments._walk_forward_evidence_collection import (
    WalkForwardEvidenceAssembler,
)
from ditto_application.processes.experiments.candidate_evidence_reader import (
    CandidateEvidenceReader,
)
from ditto_application.processes.experiments.coordinator import (
    ExperimentExecutionCoordinator,
)
from ditto_application.processes.experiments.evidence_collector import (
    ExperimentEvidenceCollector,
)
from ditto_application.processes.experiments.execution_bundle import CodeEnvironmentLock
from ditto_application.processes.experiments.factor_diagnostics_reader import (
    FactorDiagnosticsReader,
    PersistedFactorDiagnosticsSource,
)
from ditto_application.processes.experiments.regime_diagnostics_reader import (
    RegimeDiagnosticsReader,
)
from ditto_application.processes.experiments.research_backtest_checkpoint import (
    research_checkpoint_available,
    research_checkpoint_resumable,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStore,
    FirstAttemptFactory,
)
from ditto_application.processes.experiments.worker import (
    ExecutionBundleFirstAttemptFactory,
    ExistingBacktestResearchFoldRunner,
    ResearchBacktestServiceFactory,
    ResearchExecutionSemanticsResolver,
    ResearchExperimentWorker,
    ResearchFoldRunner,
    ResearchWorkerCoordinator,
)
from ditto_application.settings import ResearchExecutionSettings

__all__ = ["AppResearchExecutionProvider"]


class AppResearchExecutionProvider(Provider):
    """R3 研究执行 bundle 的 DI Provider。"""

    scope = Scope.APP

    @provide
    def frozen_research_inputs_resolver(
        self,
        artifact_service: ResearchArtifactService,
    ) -> FrozenResearchInputsResolver:
        """C1 indexed resolver: frozen manifest + rules to verified inputs."""
        return IndexedResearchInputsResolver(artifact_service=artifact_service)

    @provide
    def exact_research_artifact_loader(
        self,
        artifact_service: ResearchArtifactService,
    ) -> ExactResearchArtifactLoader:
        """C1 indexed loader 直接按 content-addressed id 读 verified Parquet bytes。"""
        return IndexedResearchArtifactLoader(artifact_service=artifact_service)

    @provide
    def indexed_backtest_report_artifact_adapter(
        self,
        artifact_service: ResearchArtifactService,
        experiment_reader: ExperimentReaderProtocol,
    ) -> IndexedBacktestReportArtifactAdapter:
        """Build one APP-scoped immutable report publisher/reader adapter."""
        return IndexedBacktestReportArtifactAdapter(
            artifact_service=artifact_service,
            artifact_index_reader=experiment_reader,
        )

    @provide
    def backtest_report_artifact_publisher(
        self,
        adapter: IndexedBacktestReportArtifactAdapter,
    ) -> BacktestReportArtifactPublisher:
        """Expose the shared report adapter through the worker write port."""
        return adapter

    @provide
    def backtest_report_artifact_reader(
        self,
        adapter: IndexedBacktestReportArtifactAdapter,
    ) -> BacktestReportArtifactReader:
        """Expose the same APP-scoped adapter through the evidence read port."""
        return adapter

    @provide
    def indexed_fold_selection_trace_artifact_adapter(
        self,
        artifact_service: ResearchArtifactService,
        experiment_reader: ExperimentReaderProtocol,
    ) -> IndexedFoldSelectionTraceArtifactAdapter:
        """Build the APP-scoped four-table fold trace publisher."""
        return IndexedFoldSelectionTraceArtifactAdapter(
            artifact_service=artifact_service,
            artifact_index_reader=experiment_reader,
        )

    @provide
    def fold_selection_trace_artifact_publisher(
        self,
        adapter: IndexedFoldSelectionTraceArtifactAdapter,
    ) -> FoldSelectionTraceArtifactPublisher:
        """Expose the indexed fold trace adapter through its worker port."""
        return adapter

    @provide
    def fold_selection_trace_artifact_reader(
        self,
        adapter: IndexedFoldSelectionTraceArtifactAdapter,
    ) -> FoldSelectionTraceArtifactReader:
        """Expose the same APP-scoped adapter through the evidence read port."""
        return adapter

    @provide
    def walk_forward_evidence_assembler(
        self,
        report_reader: BacktestReportArtifactReader,
        fold_selection_trace_reader: FoldSelectionTraceArtifactReader,
        semantics_resolver: ResearchExecutionSemanticsResolver,
    ) -> WalkForwardEvidenceAssembler:
        """Build exact persisted walk-forward evidence for review publication."""
        return WalkForwardEvidenceAssembler(
            report_reader=report_reader,
            fold_selection_trace_reader=fold_selection_trace_reader,
            semantics_resolver=semantics_resolver,
        )

    @provide
    def candidate_evidence_reader(
        self,
        scheduler_store: ExperimentSchedulerStore,
        walk_forward_assembler: WalkForwardEvidenceAssembler,
        research_artifact_service: ResearchArtifactService,
    ) -> CandidateEvidenceReader:
        """Bind drill-down pages to current comparison and verified artifacts."""
        return CandidateEvidenceReader(
            scheduler_store=scheduler_store,
            walk_forward_assembler=walk_forward_assembler,
            artifact_service=research_artifact_service,
        )

    @provide
    def candidate_selection_process(
        self,
        scheduler_store: ExperimentSchedulerStore,
        candidate_evidence_reader: CandidateEvidenceReader,
    ) -> CandidateSelectionProcess:
        """Bind candidate preselection to the scheduler's fenced event store."""
        return CandidateSelectionProcess(
            store=scheduler_store,
            candidate_evidence_reader=candidate_evidence_reader,
        )

    @provide
    def factor_diagnostics_source(
        self,
        scheduler_store: ExperimentSchedulerStore,
        walk_forward_assembler: WalkForwardEvidenceAssembler,
    ) -> PersistedFactorDiagnosticsSource:
        """Reuse verified comparison assembly for factor diagnostics lookup."""
        return PersistedFactorDiagnosticsSource(
            scheduler_store=scheduler_store,
            walk_forward_assembler=walk_forward_assembler,
        )

    @provide
    def factor_diagnostics_reader(
        self,
        source: PersistedFactorDiagnosticsSource,
    ) -> FactorDiagnosticsReader:
        """Bind diagnostics to the governed core-factor registry hash."""
        return FactorDiagnosticsReader(
            source=source,
            expected_registry_hash=R3_CORE_FACTOR_CATALOG.payload_hash,
        )

    @provide
    def regime_diagnostics_reader(
        self,
        artifact_service: ResearchArtifactService,
    ) -> RegimeDiagnosticsReader:
        """Bind the PIT regime reader to exact indexed research artifacts."""
        return RegimeDiagnosticsReader(artifacts=artifact_service)

    @provide
    def code_environment_lock(
        self,
        settings: ResearchExecutionSettings,
    ) -> CodeEnvironmentLock:
        """Build code environment lock from settings (no git I/O)."""
        return build_code_environment_lock(
            git_commit_sha=settings.code_version,
            environment_lock_hash=settings.environment_lock_hash,
        )

    @provide
    def research_execution_runtime_builders(
        self,
        candidate: ResearchRuntimeBuilder,
        candidate_replay: ResearchEvidenceReplayRuntimeBuilder,
        published_baseline: PublishedBaselineRuntimeBuilder,
    ) -> ResearchExecutionRuntimeBuilders:
        """Bundle active, historical-replay, and published-baseline runtimes."""
        return ResearchExecutionRuntimeBuilders(
            candidate=candidate,
            candidate_replay=candidate_replay,
            published_baseline=published_baseline,
        )

    @provide
    def durable_research_execution_resolver(
        self,
        experiment_reader: ExperimentReaderProtocol,
        strategy_catalog: StrategyCatalogService,
        runtime_builders: ResearchExecutionRuntimeBuilders,
        input_resolver: FrozenResearchInputsResolver,
        environment: CodeEnvironmentLock,
    ) -> ResearchExecutionSemanticsResolver:
        """把 durable launch evidence 解析成 exact pre-claim execution semantics。"""
        return DurableResearchExecutionResolver(
            experiment_reader=experiment_reader,
            strategy_reader=strategy_catalog,
            runtime_builders=runtime_builders,
            input_resolver=input_resolver,
            environment=environment,
        )

    @provide
    def research_backtest_checkpoint_reader(
        self,
        store: StrategyRunCheckpointStore,
    ) -> StrategyRunCheckpointReaderProtocol:
        """Adapt checkpoint store to the backtest reader Protocol."""
        return store

    @provide
    def frozen_audit_research_backtest_factory(
        self,
        strategy_catalog: StrategyCatalogService,
        runtime_builder: ResearchRuntimeBuilder,
        published_baseline_builder: PublishedBaselineRuntimeBuilder,
        artifact_loader: ExactResearchArtifactLoader,
        environment: CodeEnvironmentLock,
        checkpoint_reader: StrategyRunCheckpointReaderProtocol,
        checkpoint_writer: StrategyRunCheckpointWriterProtocol,
    ) -> ResearchBacktestServiceFactory:
        """从一个 immutable audit 构造 provider-free 的真实 research backtest。"""
        return FrozenAuditResearchBacktestFactory(
            strategy_reader=strategy_catalog,
            runtime_builder=runtime_builder,
            published_baseline_builder=published_baseline_builder,
            artifact_loader=artifact_loader,
            environment=environment,
            checkpoint_reader=checkpoint_reader,
            checkpoint_writer=checkpoint_writer,
        )

    @provide
    def existing_backtest_research_fold_runner(
        self,
        factory: ResearchBacktestServiceFactory,
    ) -> ResearchFoldRunner:
        """薄 adapter 把 numerical execution 保留在 BacktestService。"""
        return ExistingBacktestResearchFoldRunner(factory=factory)

    @provide
    def execution_bundle_first_attempt_factory(
        self,
        resolver: ResearchExecutionSemanticsResolver,
    ) -> FirstAttemptFactory:
        """Freeze stable first/successor attempt identity (replaces placeholder)."""
        return ExecutionBundleFirstAttemptFactory(resolver=resolver)

    @provide
    def experiment_execution_coordinator(
        self,
        store: ExperimentSchedulerStore,
        first_attempt_factory: FirstAttemptFactory,
        evidence_collector: ExperimentEvidenceCollector,
        selection_evidence: DurableSelectionEvidenceService,
        candidate_selection_process: CandidateSelectionProcess,
        checkpoint_reader: StrategyRunCheckpointReaderProtocol,
    ) -> ExperimentExecutionCoordinator:
        """Wire one lease owner to execution, evidence, and checkpoint ports."""
        return ExperimentExecutionCoordinator(
            store=store,
            first_attempt_factory=first_attempt_factory,
            owner_token=CONTROL_COORDINATOR_OWNER_TOKEN,
            lease_duration=CONTROL_COORDINATOR_LEASE_DURATION,
            selection_evidence_provider=selection_evidence,
            evidence_collector=evidence_collector,
            selection_evidence_publisher=selection_evidence,
            candidate_selection_process=candidate_selection_process,
            checkpoint_available=partial(
                research_checkpoint_available,
                checkpoint_reader,
            ),
            checkpoint_resumable=partial(
                research_checkpoint_resumable,
                checkpoint_reader,
            ),
        )

    @provide
    def research_worker_coordinator(
        self,
        coordinator: ExperimentExecutionCoordinator,
    ) -> ResearchWorkerCoordinator:
        """把 coordinator 适配成 worker 需要的 narrow lease-fenced Protocol。"""
        return coordinator

    @provide
    def research_experiment_worker(
        self,
        coordinator: ResearchWorkerCoordinator,
        semantics_resolver: ResearchExecutionSemanticsResolver,
        runner: ResearchFoldRunner,
        report_publisher: BacktestReportArtifactPublisher,
        trace_publisher: FoldSelectionTraceArtifactPublisher,
        checkpoint_reader: StrategyRunCheckpointReaderProtocol,
    ) -> ResearchExperimentWorker:
        """执行 claimed fold 并持久化一个 typed terminal outcome。"""
        return ResearchExperimentWorker(
            coordinator=coordinator,
            semantics_resolver=semantics_resolver,
            runner=runner,
            report_publisher=report_publisher,
            fold_selection_trace_publisher=trace_publisher,
            checkpoint_available=partial(
                research_checkpoint_available,
                checkpoint_reader,
            ),
        )
