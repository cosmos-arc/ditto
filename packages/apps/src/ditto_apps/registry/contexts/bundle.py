"""上下文组合包定义."""

from dataclasses import dataclass

from ditto_application.commands.candidate_selection import CandidateSelectionHandler
from ditto_application.commands.data_product_certification import (
    DataProductCertificationCommands,
)
from ditto_application.commands.experiments import (
    CancelExperimentHandler,
    ClaimHoldoutCandidateHandler,
    LaunchExperimentHandler,
    PauseExperimentHandler,
    ResumeExperimentHandler,
    RetryExperimentFoldHandler,
)
from ditto_application.processes.execution.manual_sizing import (
    AShareTradeDateResolver,
    ManualSizingContextBuilder,
)
from ditto_application.processes.execution.signal_package import SignalPackagePublisher
from ditto_application.processes.execution.strategy_run_process import StrategyFacade
from ditto_application.processes.execution.strategy_types import RunLifecycleService
from ditto_application.processes.experiments.candidate_evidence_reader import (
    CandidateEvidenceReader,
)
from ditto_application.processes.experiments.coordinator import (
    ExperimentExecutionCoordinator,
)
from ditto_application.processes.experiments.factor_diagnostics_reader import (
    FactorDiagnosticsReader,
)
from ditto_application.processes.experiments.planning_process import (
    ExperimentPlanningProcess,
)
from ditto_application.processes.experiments.worker import ResearchExperimentWorker
from ditto_application.processes.ingestion.backfill_manager import BackfillManager
from ditto_application.processes.ingestion.retry_manager import RetryManager
from ditto_application.processes.ingestion.source_selection import (
    IngestionCoordinatorLike,
)
from ditto_application.processes.ingestion.sparse_recovery import (
    SparsePITReattestationProcess,
)
from ditto_application.processes.materialization.cascade_orchestrator import (
    InvalidationCascadeOrchestrator,
)
from ditto_application.processes.materialization.orchestrator import (
    DerivedMaterializationOrchestrator,
)
from ditto_application.processes.materialization.publication_facade import (
    DerivedPublicationFacade,
)
from ditto_application.processes.strategy.seed_bootstrap import SeedStrategyBootstrap
from ditto_application.queries.data_products import DataProductsQueryFacade
from ditto_application.queries.data_readiness import DataReadinessQueryFacade
from ditto_application.queries.experiments import ExperimentQueryFacade
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_application.queries.research import ResearchDatasetFacade
from ditto_data.sources.exchange_transformers import ExchangeTransformers
from ditto_strategy.contracts import (
    StrategyCatalogReader,
    StrategyRunStatusWriter,
)


@dataclass(frozen=True)
class IngestionBundle:
    """
    摄取上下文组合包.

    包含数据摄入所需的所有服务和协调器。
    解决 ARCH-003（组合逻辑分散）和 ARCH-004（重复容器）问题。
    """

    coordinator: IngestionCoordinatorLike
    backfill_manager: BackfillManager
    retry_manager: RetryManager
    sparse_pit_reattestation: SparsePITReattestationProcess
    metadata_facade: MetadataQueryFacade
    exchange_transformers: ExchangeTransformers
    data_products_query: DataProductsQueryFacade
    certification_commands: DataProductCertificationCommands


@dataclass(frozen=True)
class MaterializationBundle:
    """物化上下文组合包。"""

    materialization_service: DerivedMaterializationOrchestrator
    invalidation_service: InvalidationCascadeOrchestrator
    publication_facade: DerivedPublicationFacade
    research_dataset_facade: ResearchDatasetFacade


@dataclass(frozen=True)
class StrategyBundle:
    """策略上下文组合包。"""

    strategy_facade: StrategyFacade
    catalog_service: StrategyCatalogReader | None = None
    run_service: RunLifecycleService | None = None
    run_writer: StrategyRunStatusWriter | None = None
    signal_package_publisher: SignalPackagePublisher | None = None
    sizing_context_builder: ManualSizingContextBuilder | None = None
    trade_date_resolver: AShareTradeDateResolver | None = None
    seed_bootstrap: SeedStrategyBootstrap | None = None
    data_readiness_query: DataReadinessQueryFacade | None = None


@dataclass(frozen=True)
class ResearchBundle:
    """研究实验上下文组合包（planning + control + query）。"""

    experiment_query: ExperimentQueryFacade
    planning_process: ExperimentPlanningProcess
    launch_handler: LaunchExperimentHandler
    pause_handler: PauseExperimentHandler
    cancel_handler: CancelExperimentHandler
    resume_handler: ResumeExperimentHandler
    retry_fold_handler: RetryExperimentFoldHandler
    candidate_selection_handler: CandidateSelectionHandler
    holdout_claim_handler: ClaimHoldoutCandidateHandler
    candidate_evidence_reader: CandidateEvidenceReader
    factor_diagnostics_reader: FactorDiagnosticsReader


@dataclass(frozen=True)
class ExperimentExecutionBundle:
    """
    Experiment scheduler tick composition root bundle.

    Holds the concrete coordinator + worker wired by the DI container; the
    flow entrypoint adapts this into the Protocol-typed
    :class:`ExperimentTickRuntime` required by ``experiment_scheduler_tick_flow``.
    Keeping the bundle concrete (not Protocol-typed) lets the composition root
    stay decoupled from the jobs/flows layer and avoids a registry -> jobs
    reverse dependency.
    """

    coordinator: ExperimentExecutionCoordinator
    worker: ResearchExperimentWorker
