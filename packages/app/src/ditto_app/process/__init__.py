"""App Process 模块 — 编排协调."""

from __future__ import annotations

from ditto_app.process._coordinator_constants import SWIndustryProvider
from ditto_app.process.backfill_manager import BackfillManager
from ditto_app.process.backtest_service import (
    BacktestService,
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_app.process.cascade_orchestrator import (
    CascadeDepthExceededError,
    CascadeStatus,
    InvalidationCascadeOrchestrator,
    RepairBatchResult,
)
from ditto_app.process.certification_rules import build_certification_checks
from ditto_app.process.coordinator_factory import create_coordinator
from ditto_app.process.data_writer import IngestionDataWriter
from ditto_app.process.factor_orthogonalization import (
    FactorOrthogonalizationService,
)
from ditto_app.process.ingestion_config import (
    IngestionConfig,
    IngestionCoordinatorConfig,
)
from ditto_app.process.ingestion_coordinator import IngestionCoordinator
from ditto_app.process.list_date_inference import (
    ListDateInferenceService,
)
from ditto_app.process.materialization_dependencies import apply_cs_amplification
from ditto_app.process.materialization_helpers import (
    build_manifest_record,
    build_minimal_dq_record,
    dependency_refs,
    resolve_shadow_baseline,
)
from ditto_app.process.materialization_orchestrator import (
    DerivedMaterializationOrchestrator,
    UniverseProvider,
)
from ditto_app.process.materialization_types import (
    DerivedInputProvider,
    InMemoryDerivedInputProvider,
    InputContext,
    MissingDependencyError,
    UnavailableDerivedInputProvider,
    earliest_pending_start,
    hydrate_spec,
    prepare_input_frame,
)
from ditto_app.process.metadata_manager import MetadataManager
from ditto_app.process.publication_facade import DerivedPublicationFacade
from ditto_app.process.quality import (
    ComparisonStoreProtocol,
    InstrumentStoreProtocol,
    L3BatchService,
    QualityReconciliationService,
    QualityService,
    ReconciliationResult,
    TdxSourceProtocol,
)
from ditto_app.process.result_handler import IngestionResultHandler
from ditto_app.process.retry_manager import RetryManager
from ditto_app.process.runtime_input_provider import RuntimeDerivedInputProvider
from ditto_app.process.strategy_run_service import (
    StrategyFacade,
    StrategyRunMode,
    StrategyRunResult,
    StrategyRunService,
    StrategyRunServiceConfig,
)
from ditto_app.process.strategy_types import (
    RunLifecycleService,
    StrategyInputAssembler,
)

__all__ = [
    "BackfillManager",
    "BacktestService",
    "BacktestServiceConfig",
    "BacktestServiceOptions",
    "CascadeDepthExceededError",
    "CascadeStatus",
    "ComparisonStoreProtocol",
    "DerivedInputProvider",
    "DerivedMaterializationOrchestrator",
    "DerivedPublicationFacade",
    "FactorOrthogonalizationService",
    "InMemoryDerivedInputProvider",
    "IngestionConfig",
    "IngestionCoordinator",
    "IngestionCoordinatorConfig",
    "IngestionDataWriter",
    "IngestionResultHandler",
    "InputContext",
    "InstrumentStoreProtocol",
    "InvalidationCascadeOrchestrator",
    "L3BatchService",
    "ListDateInferenceService",
    "MetadataManager",
    "MissingDependencyError",
    "QualityReconciliationService",
    "QualityService",
    "ReconciliationResult",
    "RepairBatchResult",
    "RetryManager",
    "RunLifecycleService",
    "RuntimeDerivedInputProvider",
    "SWIndustryProvider",
    "StrategyFacade",
    "StrategyInputAssembler",
    "StrategyRunMode",
    "StrategyRunResult",
    "StrategyRunService",
    "StrategyRunServiceConfig",
    "TdxSourceProtocol",
    "UnavailableDerivedInputProvider",
    "UniverseProvider",
    "apply_cs_amplification",
    "build_certification_checks",
    "build_manifest_record",
    "build_minimal_dq_record",
    "create_coordinator",
    "dependency_refs",
    "earliest_pending_start",
    "hydrate_spec",
    "prepare_input_frame",
    "resolve_shadow_baseline",
]
