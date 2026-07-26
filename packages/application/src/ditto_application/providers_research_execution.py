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
  apps composition root（C3）从真实 git HEAD + pixi.lock sha256 写入。
- 通过 Protocol 类型（``FrozenResearchInputsResolver`` 等）注册，让消费侧的
  ``__init__`` 类型注解能直接解析到这些实例。
"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_analysis.experiments import ExperimentReaderProtocol
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunCheckpointReaderProtocol,
    StrategyRunCheckpointStore,
    StrategyRunCheckpointWriterProtocol,
)

from ditto_application.builders import (
    IndexedResearchArtifactLoader,
    IndexedResearchInputsResolver,
    PublishedBaselineRuntimeBuilder,
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
from ditto_application.processes.experiments._execution_resolution_evidence import (
    FrozenResearchInputsResolver,
)
from ditto_application.processes.experiments.coordinator import (
    ExperimentExecutionCoordinator,
)
from ditto_application.processes.experiments.execution_bundle import CodeEnvironmentLock
from ditto_application.processes.experiments.scheduler_store import FirstAttemptFactory
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
        published_baseline: PublishedBaselineRuntimeBuilder,
    ) -> ResearchExecutionRuntimeBuilders:
        """把 candidate + published-baseline runtime lanes 打包成 typed dataclass。"""
        return ResearchExecutionRuntimeBuilders(
            candidate=candidate,
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
    ) -> ResearchExperimentWorker:
        """执行 claimed fold 并持久化一个 typed terminal outcome。"""
        return ResearchExperimentWorker(
            coordinator=coordinator,
            semantics_resolver=semantics_resolver,
            runner=runner,
        )
