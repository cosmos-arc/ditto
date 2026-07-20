"""Read-only certification and executor probes for experiment planning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast

from ditto_strategy.models import StrategySpecRecord

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.planning import (
    BaselineDescriptor,
    BinderCandidatePlan,
)
from ditto_application.research_certification_contracts import (
    ExperimentSnapshotIdentity,
    ResearchCertificationProbe,
    ResearchCertificationRequest,
    ResearchCertificationResult,
    ResearchDatasetRequirement,
    ResearchSnapshotEvidence,
    is_canonical_content_hash,
    is_canonical_identity,
)
from ditto_application.research_validation_contracts import RuntimeValidationEvidence

__all__ = [
    "R3_RESEARCH_CERTIFICATION_PROFILE",
    "CandidateExecutorEvidence",
    "ExperimentSnapshotIdentity",
    "PlanningIdentityInput",
    "ResearchCertificationProbe",
    "ResearchCertificationRequest",
    "ResearchCertificationResult",
    "ResearchDatasetRequirement",
    "ResearchExecutorProbe",
    "ResearchExecutorProbeRequest",
    "ResearchExecutorProbeResult",
    "ResearchSnapshotEvidence",
    "RuntimeValidationEvidence",
    "is_canonical_content_hash",
    "validate_planning_identity",
]

R3_RESEARCH_CERTIFICATION_PROFILE = "r2-modern-a-share-v1"


@dataclass(frozen=True, slots=True)
class PlanningIdentityInput:
    """Scalar identities that must be valid before any planning-side probe."""

    experiment_id: str
    research_cycle_id: str
    research_cycle_hash: str
    strategy_record: StrategySpecRecord
    snapshot_identity: ExperimentSnapshotIdentity
    dataset_requirements: tuple[ResearchDatasetRequirement, ...]
    created_at: datetime


def validate_planning_identity(value: PlanningIdentityInput) -> None:
    """Fail before reads or writes when a planning identity is ambiguous."""
    raw_requirements: object = value.dataset_requirements
    if type(raw_requirements) is not tuple:
        raise AppProcessError(
            "planning request is not reproducible",
            details={"code": "SPEC_INVALID", "reason": "invalid_planning_identity"},
        )
    raw_items = cast("tuple[object, ...]", raw_requirements)
    if not raw_items or any(
        type(item) is not ResearchDatasetRequirement for item in raw_items
    ):
        raise AppProcessError(
            "planning request is not reproducible",
            details={"code": "SPEC_INVALID", "reason": "invalid_planning_identity"},
        )
    requirements = cast("tuple[ResearchDatasetRequirement, ...]", raw_items)
    if (
        not isinstance(cast("object", value.created_at), datetime)
        or value.created_at.tzinfo is None
        or value.created_at.utcoffset() != UTC.utcoffset(value.created_at)
        or not is_canonical_identity(value.experiment_id)
        or not is_canonical_identity(value.research_cycle_id)
        or not is_canonical_content_hash(value.research_cycle_hash)
        or not isinstance(cast("object", value.strategy_record), StrategySpecRecord)
        or not is_canonical_identity(value.strategy_record.strategy_id)
        or type(value.strategy_record.version) is not int
        or value.strategy_record.version <= 0
        or not isinstance(
            cast("object", value.snapshot_identity), ExperimentSnapshotIdentity
        )
        or not is_canonical_identity(value.snapshot_identity.snapshot_id)
        or not is_canonical_content_hash(value.snapshot_identity.manifest_hash)
        or len({item.dataset_id for item in requirements}) != len(requirements)
    ):
        raise AppProcessError(
            "planning request is not reproducible",
            details={"code": "SPEC_INVALID", "reason": "invalid_planning_identity"},
        )


@dataclass(frozen=True, slots=True)
class CandidateExecutorEvidence:
    """Build-time identity for one non-baseline candidate."""

    candidate_hash: str
    resolved_spec_hash: str
    parameter_hash: str


@dataclass(frozen=True, slots=True)
class ResearchExecutorProbeRequest:
    """All values needed to validate real candidate runtime construction."""

    strategy_record: StrategySpecRecord
    snapshot_identity: ExperimentSnapshotIdentity
    baseline: BaselineDescriptor
    candidates: tuple[BinderCandidatePlan, ...]


@dataclass(frozen=True, slots=True)
class ResearchExecutorProbeResult:
    """Typed executor availability and candidate build evidence."""

    available: bool
    code: str | None
    reason: str | None
    remediation: str | None
    strategy_spec_hash: str | None
    node_registry_manifest_hash: str | None
    required_datasets: tuple[str, ...]
    candidates: tuple[CandidateExecutorEvidence, ...]
    runtime_validation_evidence: RuntimeValidationEvidence | None = None


class ResearchExecutorProbe(Protocol):
    """Pure runtime-build probe; implementations must not enqueue work."""

    def probe(
        self, request: ResearchExecutorProbeRequest
    ) -> ResearchExecutorProbeResult:
        """Validate every executable candidate without scheduling work."""
        ...
