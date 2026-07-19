"""
Experiment pure domain contracts.

This package does not schedule work and does not persist records. Application
orchestration and adapters consume these immutable analysis-owned contracts.
"""

from ditto_analysis.experiments.models import (
    AttemptId,
    AttemptRecord,
    BacktestRunId,
    CandidateId,
    CandidateRecord,
    CheckpointRef,
    ContentHash,
    ExperimentDesiredState,
    ExperimentFailureCode,
    ExperimentId,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
    FoldId,
    FoldRecord,
    SnapshotId,
    StrategyVersion,
    validate_status_transition,
)
from ditto_analysis.experiments.protocols import (
    ExperimentReaderProtocol,
    ExperimentWriterProtocol,
)
from ditto_analysis.experiments.specs import (
    CandidateSpec,
    ExperimentBudget,
    ExperimentFailurePolicy,
    ExperimentLaunchSpec,
    FoldProtocolSpec,
)

__all__ = [
    "AttemptId",
    "AttemptRecord",
    "BacktestRunId",
    "CandidateId",
    "CandidateRecord",
    "CandidateSpec",
    "CheckpointRef",
    "ContentHash",
    "ExperimentBudget",
    "ExperimentDesiredState",
    "ExperimentFailureCode",
    "ExperimentFailurePolicy",
    "ExperimentId",
    "ExperimentLaunchSpec",
    "ExperimentReaderProtocol",
    "ExperimentRecord",
    "ExperimentStage",
    "ExperimentStatus",
    "ExperimentWriterProtocol",
    "FoldId",
    "FoldProtocolSpec",
    "FoldRecord",
    "SnapshotId",
    "StrategyVersion",
    "validate_status_transition",
]
