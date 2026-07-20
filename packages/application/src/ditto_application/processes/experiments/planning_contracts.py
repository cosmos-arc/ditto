"""Neutral request and preflight contracts for R3 experiment planning."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ditto_analysis.experiments import ExperimentFailurePolicy
from ditto_strategy.models import StrategySpecRecord

from ditto_application.processes.experiments.planning import (
    CandidateMatrixSpec,
    ExperimentBudgetSpec,
    ResourceCostModel,
)
from ditto_application.processes.experiments.planning_probes import (
    ExperimentSnapshotIdentity,
    ResearchDatasetRequirement,
)
from ditto_application.research_validation_protocol import ValidationProtocolRequest

__all__ = [
    "ExperimentPlanningRequest",
    "ExperimentPreflightCheck",
    "PreflightOutcome",
]


class PreflightOutcome(StrEnum):
    """Stable three-way outcome for one preflight rule."""

    PASS = "pass"  # noqa: S105 - policy outcome, not a credential
    FAIL = "fail"
    WARN = "warn"


@dataclass(frozen=True, slots=True)
class ExperimentPreflightCheck:
    """One deterministic pass/fail/warn result with remediation."""

    rule_id: str
    outcome: PreflightOutcome
    code: str | None
    reason: str | None
    remediation: str | None
    observed: Mapping[str, object]
    policy: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ExperimentPlanningRequest:
    """Frozen identities and pure inputs used by preflight and launch replay."""

    experiment_id: str
    research_cycle_id: str
    research_cycle_hash: str
    strategy_record: StrategySpecRecord
    snapshot_identity: ExperimentSnapshotIdentity
    validation_request: ValidationProtocolRequest
    matrix_spec: CandidateMatrixSpec
    dataset_requirements: tuple[ResearchDatasetRequirement, ...]
    cost_model: ResourceCostModel
    budget: ExperimentBudgetSpec
    seed: int
    worker_count: int
    failure_policy: ExperimentFailurePolicy
    created_at: datetime
