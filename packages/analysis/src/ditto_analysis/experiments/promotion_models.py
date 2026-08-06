"""Typed, versioned promotion objective value objects."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.metric_schema import (
    R3_RESEARCH_METRIC_SCHEMA,
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
)
from ditto_analysis.experiments.models import CandidateId, ContentHash
from ditto_analysis.experiments.pbo_plan import PboPartitionPlan
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialFamilyDeclaration,
    TrialKind,
)

__all__ = [
    "ConstraintOperator",
    "MetricConstraint",
    "ObjectiveMetric",
    "PriorTrialEvidenceDeclaration",
    "PromotionObjective",
]

_METRIC_ORDER = {
    definition.metric_id: index
    for index, definition in enumerate(R3_RESEARCH_METRIC_SCHEMA.definitions)
}


def _objective_error(
    message: str,
    reason_code: str,
    **details: object,
) -> ExperimentSpecError:
    return ExperimentSpecError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _ordered_values(
    value: object,
    expected_type: type,
    field_name: str,
) -> tuple[object, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _objective_error(
            f"{field_name} must be an ordered sequence",
            "invalid_promotion_objective",
            field=field_name,
        )
    items = tuple(cast("Sequence[object]", value))
    if any(type(item) is not expected_type for item in items):
        raise _objective_error(
            f"{field_name} contains an invalid value",
            "invalid_promotion_objective",
            field=field_name,
        )
    return items


class ConstraintOperator(StrEnum):
    """Supported deterministic hard-constraint comparisons."""

    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"


@dataclass(frozen=True, slots=True)
class ObjectiveMetric:
    """Typed scalar metric and its schema-owned optimization direction."""

    metric_id: ResearchMetricId
    direction: ResearchMetricDirection

    def __post_init__(self) -> None:
        """Reject string lookalikes, profiles, and direction substitutions."""
        if type(self.metric_id) is not ResearchMetricId:
            raise _objective_error(
                "objective metric id must be ResearchMetricId",
                "invalid_objective_metric",
            )
        if type(self.direction) is not ResearchMetricDirection:
            raise _objective_error(
                "objective direction must be ResearchMetricDirection",
                "invalid_metric_direction",
            )
        definition = R3_RESEARCH_METRIC_SCHEMA.definition(self.metric_id)
        if not definition.is_scalar or (
            definition.direction is ResearchMetricDirection.CONTEXT_ONLY
        ):
            raise _objective_error(
                "objective metric must be a rankable scalar",
                "unrankable_objective_metric",
                metric_id=self.metric_id.value,
            )
        if self.direction is not definition.direction:
            raise _objective_error(
                "objective direction must match the versioned metric schema",
                "metric_direction_mismatch",
                metric_id=self.metric_id.value,
                expected_direction=definition.direction.value,
                supplied_direction=self.direction.value,
            )


@dataclass(frozen=True, slots=True)
class MetricConstraint:
    """Hard threshold bound to one typed metric value and canonical unit."""

    threshold: ResearchMetricValue
    operator: ConstraintOperator

    def __post_init__(self) -> None:
        """Require exact typed threshold and comparison operator nodes."""
        if type(self.threshold) is not ResearchMetricValue:
            raise _objective_error(
                "constraint threshold must be ResearchMetricValue",
                "invalid_metric_constraint_threshold",
            )
        if type(self.operator) is not ConstraintOperator:
            raise _objective_error(
                "constraint operator must be ConstraintOperator",
                "invalid_constraint_operator",
            )

    @property
    def metric_id(self) -> ResearchMetricId:
        """Return the threshold's exact metric identity."""
        return self.threshold.metric_id


@dataclass(frozen=True, slots=True)
class PriorTrialEvidenceDeclaration:
    """Expected canonical artifact hash for one declared prior logical trial."""

    trial: LogicalTrialIdentity
    outcome_content_hash: ContentHash

    def __post_init__(self) -> None:
        """Require an exact prior identity and immutable SHA-256 content id."""
        if (
            type(self.trial) is not LogicalTrialIdentity
            or self.trial.kind is not TrialKind.PRIOR
            or type(self.outcome_content_hash) is not ContentHash
        ):
            raise _objective_error(
                "prior evidence declaration must bind one exact prior trial",
                "invalid_prior_trial_evidence_declaration",
            )

    def canonical_payload(self) -> dict[str, object]:
        """Return the strict trial-to-artifact binding payload."""
        return {
            "trial": {
                "origin_experiment_id": str(self.trial.origin_experiment_id),
                "candidate_id": str(self.trial.candidate_id),
                "ordinal": self.trial.ordinal,
                "parameter_hash": str(self.trial.parameter_hash),
                "kind": self.trial.kind.value,
            },
            "outcome_content_hash": str(self.outcome_content_hash),
        }


@dataclass(frozen=True, slots=True)
class PromotionObjective:
    """Promotion criteria frozen against an exact logical trial family."""

    primary: ObjectiveMetric
    hard_constraints: Sequence[MetricConstraint]
    tie_break_order: Sequence[ObjectiveMetric]
    baseline_candidate_id: CandidateId
    economic_rationale: str
    trial_family: TrialFamilyDeclaration
    pbo_partition_plan: PboPartitionPlan | None = None
    prior_trial_evidence: Sequence[PriorTrialEvidenceDeclaration] = ()

    def __post_init__(self) -> None:  # noqa: C901 - aggregate invariant gate
        """Freeze, canonicalize, and validate every objective declaration."""
        if type(self.primary) is not ObjectiveMetric:
            raise _objective_error(
                "primary must be ObjectiveMetric",
                "invalid_promotion_objective",
                field="primary",
            )
        constraints = cast(
            "tuple[MetricConstraint, ...]",
            _ordered_values(
                self.hard_constraints,
                MetricConstraint,
                "hard_constraints",
            ),
        )
        tie_breaks = cast(
            "tuple[ObjectiveMetric, ...]",
            _ordered_values(
                self.tie_break_order,
                ObjectiveMetric,
                "tie_break_order",
            ),
        )
        constraint_ids = tuple(item.metric_id for item in constraints)
        if len(set(constraint_ids)) != len(constraint_ids):
            raise _objective_error(
                "hard constraint metrics must be unique",
                "duplicate_constraint_metric",
            )
        tie_ids = tuple(item.metric_id for item in tie_breaks)
        if len(set(tie_ids)) != len(tie_ids) or self.primary.metric_id in tie_ids:
            raise _objective_error(
                "tie-break metrics must be unique and exclude the primary metric",
                "duplicate_tie_break_metric",
            )
        if type(self.baseline_candidate_id) is not CandidateId:
            raise _objective_error(
                "baseline_candidate_id must be CandidateId",
                "invalid_promotion_objective",
                field="baseline_candidate_id",
            )
        if (
            type(self.economic_rationale) is not str
            or not self.economic_rationale.strip()
            or self.economic_rationale != self.economic_rationale.strip()
        ):
            raise _objective_error(
                "economic rationale must be a non-empty unpadded string",
                "invalid_promotion_objective",
                field="economic_rationale",
            )
        if type(self.trial_family) is not TrialFamilyDeclaration:
            raise _objective_error(
                "trial_family must be TrialFamilyDeclaration",
                "invalid_promotion_objective",
                field="trial_family",
            )
        if self.pbo_partition_plan is not None and (
            type(self.pbo_partition_plan) is not PboPartitionPlan
        ):
            raise _objective_error(
                "pbo_partition_plan must be PboPartitionPlan or None",
                "invalid_promotion_objective",
                field="pbo_partition_plan",
            )
        if self.pbo_partition_plan is not None and (
            self.pbo_partition_plan.score_metric_id is not self.primary.metric_id
            or self.pbo_partition_plan.direction is not self.primary.direction
        ):
            raise _objective_error(
                "PBO plan metric and direction must equal the primary objective",
                "pbo_plan_objective_mismatch",
            )
        prior_evidence = cast(
            "tuple[PriorTrialEvidenceDeclaration, ...]",
            _ordered_values(
                self.prior_trial_evidence,
                PriorTrialEvidenceDeclaration,
                "prior_trial_evidence",
            ),
        )
        prior_members = self.trial_family.prior_members
        evidence_trials = tuple(item.trial for item in prior_evidence)
        if len(set(evidence_trials)) != len(evidence_trials) or (
            prior_evidence and set(evidence_trials) != set(prior_members)
        ):
            raise _objective_error(
                "prior evidence must bind every prior trial exactly once",
                "prior_trial_evidence_family_mismatch",
            )
        if self.baseline_candidate_id not in {
            member.candidate_id for member in self.trial_family.current_members
        }:
            raise _objective_error(
                "baseline candidate must be a declared current logical trial",
                "promotion_baseline_trial_missing",
            )
        object.__setattr__(
            self,
            "hard_constraints",
            tuple(sorted(constraints, key=lambda item: _METRIC_ORDER[item.metric_id])),
        )
        object.__setattr__(self, "tie_break_order", tie_breaks)
        prior_order = {trial: index for index, trial in enumerate(prior_members)}
        object.__setattr__(
            self,
            "prior_trial_evidence",
            tuple(sorted(prior_evidence, key=lambda item: prior_order[item.trial])),
        )

    @property
    def declared_trial_count(self) -> int:
        """Return multiplicity derived from the exact frozen family."""
        return self.trial_family.declared_trial_count
