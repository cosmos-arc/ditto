"""Strict canonical codec for a typed, pre-registered promotion objective."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any, cast

from ditto_analysis.errors import AnalysisError, ExperimentSpecError
from ditto_analysis.experiments.metric_schema import (
    R3_RESEARCH_METRIC_SCHEMA,
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
)
from ditto_analysis.experiments.models import (
    CandidateId,
    ContentHash,
    ExperimentId,
)
from ditto_analysis.experiments.pbo_plan import (
    PboEstimator,
    PboPartitionIdentity,
    PboPartitionPlan,
    ReturnFrequency,
    SamplingReturnUnit,
)
from ditto_analysis.experiments.promotion_models import (
    ConstraintOperator,
    MetricConstraint,
    ObjectiveMetric,
    PriorTrialEvidenceDeclaration,
    PromotionObjective,
)
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialFamilyDeclaration,
    TrialKind,
)

__all__ = [
    "decode_promotion_objective",
    "promotion_objective_payload",
    "trial_family_payload",
    "validate_promotion_objective_graph",
]

_OBJECTIVE_SCHEMA_ID = "r3-promotion-objective"
_OBJECTIVE_SCHEMA_VERSION = 1
_TRIAL_FAMILY_SCHEMA_ID = "r3-trial-family"
_TRIAL_FAMILY_SCHEMA_VERSION = 1


def _invalid(
    message: str = "promotion objective graph is invalid",
) -> ExperimentSpecError:
    return ExperimentSpecError(
        message,
        details={"reason_code": "invalid_promotion_objective_graph"},
    )


def _exact_graph(value: object) -> PromotionObjective:
    if type(value) is not PromotionObjective:
        raise _invalid()
    objective = value
    constraints = cast("object", objective.hard_constraints)
    tie_breaks = cast("object", objective.tie_break_order)
    family = cast("object", objective.trial_family)
    pbo_plan = cast("object", objective.pbo_partition_plan)
    prior_evidence = cast("object", objective.prior_trial_evidence)
    if (
        type(objective.primary) is not ObjectiveMetric
        or type(objective.primary.metric_id) is not ResearchMetricId
        or type(objective.primary.direction) is not ResearchMetricDirection
        or type(constraints) is not tuple
        or type(tie_breaks) is not tuple
        or type(objective.baseline_candidate_id) is not CandidateId
        or type(objective.economic_rationale) is not str
        or type(family) is not TrialFamilyDeclaration
        or type(family.family_id) is not str
        or type(family.members) is not tuple
        or (pbo_plan is not None and type(pbo_plan) is not PboPartitionPlan)
        or type(prior_evidence) is not tuple
    ):
        raise _invalid()
    typed_family = family
    if any(
        type(item) is not MetricConstraint
        or type(item.threshold) is not ResearchMetricValue
        or type(item.threshold.metric_id) is not ResearchMetricId
        or type(item.threshold.value) is not float
        or type(item.operator) is not ConstraintOperator
        for item in cast("tuple[object, ...]", constraints)
    ) or any(
        type(item) is not ObjectiveMetric
        or type(item.metric_id) is not ResearchMetricId
        or type(item.direction) is not ResearchMetricDirection
        for item in cast("tuple[object, ...]", tie_breaks)
    ):
        raise _invalid()
    if any(
        type(item) is not PriorTrialEvidenceDeclaration
        or type(item.trial) is not LogicalTrialIdentity
        or type(item.outcome_content_hash) is not ContentHash
        for item in cast("tuple[object, ...]", prior_evidence)
    ):
        raise _invalid()
    if any(
        type(item) is not LogicalTrialIdentity
        or type(item.origin_experiment_id) is not ExperimentId
        or type(item.candidate_id) is not CandidateId
        or type(item.ordinal) is not int
        or type(item.parameter_hash) is not ContentHash
        or type(item.kind) is not TrialKind
        for item in cast("tuple[object, ...]", typed_family.members)
    ):
        raise _invalid()
    return objective


def _copy_metric(metric: ObjectiveMetric) -> ObjectiveMetric:
    return ObjectiveMetric(metric.metric_id, metric.direction)


def _copy_trial(member: LogicalTrialIdentity) -> LogicalTrialIdentity:
    return LogicalTrialIdentity(
        ExperimentId(str(member.origin_experiment_id)),
        CandidateId(str(member.candidate_id)),
        member.ordinal,
        ContentHash(str(member.parameter_hash)),
        member.kind,
    )


def _copy_pbo_plan(value: PboPartitionPlan | None) -> PboPartitionPlan | None:
    if value is None:
        return None
    return PboPartitionPlan(
        value.score_metric_id,
        value.direction,
        value.estimator,
        value.return_unit,
        value.return_frequency,
        value.periods_per_year,
        tuple(
            PboPartitionIdentity(
                item.partition_id,
                item.ordinal,
                item.window_start,
                item.window_end,
                item.observation_count,
                ContentHash(str(item.observation_date_grid_hash)),
            )
            for item in value.partitions
        ),
    )


def validate_promotion_objective_graph(value: object) -> PromotionObjective:
    """Rebuild and detach every typed objective node from caller-owned objects."""
    objective = _exact_graph(value)
    constraints = cast("tuple[MetricConstraint, ...]", objective.hard_constraints)
    tie_breaks = cast("tuple[ObjectiveMetric, ...]", objective.tie_break_order)
    try:
        return PromotionObjective(
            primary=_copy_metric(objective.primary),
            hard_constraints=tuple(
                MetricConstraint(
                    ResearchMetricValue(
                        item.threshold.metric_id,
                        item.threshold.value,
                    ),
                    item.operator,
                )
                for item in constraints
            ),
            tie_break_order=tuple(_copy_metric(item) for item in tie_breaks),
            baseline_candidate_id=CandidateId(str(objective.baseline_candidate_id)),
            economic_rationale=objective.economic_rationale,
            trial_family=TrialFamilyDeclaration(
                objective.trial_family.family_id,
                tuple(_copy_trial(item) for item in objective.trial_family.members),
            ),
            pbo_partition_plan=_copy_pbo_plan(objective.pbo_partition_plan),
            prior_trial_evidence=tuple(
                PriorTrialEvidenceDeclaration(
                    _copy_trial(item.trial),
                    ContentHash(str(item.outcome_content_hash)),
                )
                for item in objective.prior_trial_evidence
            ),
        )
    except AnalysisError as exc:
        raise _invalid() from exc


def _metric_payload(metric: ObjectiveMetric) -> dict[str, object]:
    return {
        "metric_id": metric.metric_id.value,
        "direction": metric.direction.value,
    }


def _trial_payload(member: LogicalTrialIdentity) -> dict[str, object]:
    return {
        "origin_experiment_id": str(member.origin_experiment_id),
        "candidate_id": str(member.candidate_id),
        "ordinal": member.ordinal,
        "parameter_hash": str(member.parameter_hash),
        "kind": member.kind.value,
    }


def trial_family_payload(value: object) -> Mapping[str, object]:
    """Return the versioned canonical declaration of one exact trial family."""
    if type(value) is not TrialFamilyDeclaration:
        raise _invalid("trial family must be a TrialFamilyDeclaration")
    family = value
    if any(type(member) is not LogicalTrialIdentity for member in family.members):
        raise _invalid("trial family members must be logical trial identities")
    return {
        "schema_id": _TRIAL_FAMILY_SCHEMA_ID,
        "schema_version": _TRIAL_FAMILY_SCHEMA_VERSION,
        "family_id": family.family_id,
        "members": [_trial_payload(member) for member in family.members],
    }


def promotion_objective_payload(value: object) -> Mapping[str, object]:
    """Return the complete objective in stable, versioned declaration order."""
    objective = validate_promotion_objective_graph(value)
    return {
        "schema_id": _OBJECTIVE_SCHEMA_ID,
        "schema_version": _OBJECTIVE_SCHEMA_VERSION,
        "metric_schema": R3_RESEARCH_METRIC_SCHEMA.canonical_payload(),
        "primary": _metric_payload(objective.primary),
        "hard_constraints": [
            {
                "threshold": item.threshold.canonical_payload(),
                "operator": item.operator.value,
            }
            for item in objective.hard_constraints
        ],
        "tie_break_order": [
            _metric_payload(item) for item in objective.tie_break_order
        ],
        "baseline_candidate_id": str(objective.baseline_candidate_id),
        "economic_rationale": objective.economic_rationale,
        "trial_family": trial_family_payload(objective.trial_family),
        "pbo_partition_plan": (
            None
            if objective.pbo_partition_plan is None
            else objective.pbo_partition_plan.canonical_payload()
        ),
        "prior_trial_evidence": [
            item.canonical_payload() for item in objective.prior_trial_evidence
        ],
    }


def _mapping(value: object) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise _invalid("promotion objective payload must be an object")
    return cast("Mapping[str, Any]", value)


def _list(value: object) -> list[object]:
    if type(value) is not list:
        raise _invalid("promotion objective payload must use JSON arrays")
    return cast("list[object]", value)


def _metric_from_payload(value: object) -> ObjectiveMetric:
    item = _mapping(value)
    return ObjectiveMetric(
        ResearchMetricId(item["metric_id"]),
        ResearchMetricDirection(item["direction"]),
    )


def _metric_value_from_payload(value: object) -> ResearchMetricValue:
    item = _mapping(value)
    metric_value = ResearchMetricValue(
        ResearchMetricId(item["metric_id"]),
        item["value"],
    )
    if item != metric_value.canonical_payload():
        raise _invalid("promotion objective metric value is not canonical")
    return metric_value


def _trial_from_payload(value: object) -> LogicalTrialIdentity:
    item = _mapping(value)
    return LogicalTrialIdentity(
        ExperimentId(item["origin_experiment_id"]),
        CandidateId(item["candidate_id"]),
        item["ordinal"],
        ContentHash(item["parameter_hash"]),
        TrialKind(item["kind"]),
    )


def _pbo_plan_from_payload(value: object) -> PboPartitionPlan | None:
    if value is None:
        return None
    item = _mapping(value)
    if item["schema_id"] != "r3-pbo-partition-plan" or item["schema_version"] != 1:
        raise _invalid("PBO partition plan schema is unsupported")
    return PboPartitionPlan(
        ResearchMetricId(item["score_metric_id"]),
        ResearchMetricDirection(item["direction"]),
        PboEstimator(item["estimator"]),
        SamplingReturnUnit(item["return_unit"]),
        ReturnFrequency(item["return_frequency"]),
        item["periods_per_year"],
        tuple(
            PboPartitionIdentity(
                partition["partition_id"],
                partition["ordinal"],
                date.fromisoformat(partition["window_start"]),
                date.fromisoformat(partition["window_end"]),
                partition["observation_count"],
                ContentHash(partition["observation_date_grid_hash"]),
            )
            for raw_partition in _list(item["partitions"])
            for partition in (_mapping(raw_partition),)
        ),
    )


def decode_promotion_objective(value: object) -> PromotionObjective:
    """Decode strict JSON-shaped objective evidence and validate its full graph."""
    try:
        root = _mapping(value)
        if (
            root["schema_id"] != _OBJECTIVE_SCHEMA_ID
            or root["schema_version"] != _OBJECTIVE_SCHEMA_VERSION
        ):
            raise _invalid("promotion objective schema is unsupported")
        schema = _mapping(root["metric_schema"])
        if schema != R3_RESEARCH_METRIC_SCHEMA.canonical_payload():
            raise _invalid("promotion objective metric schema is unsupported")
        family = _mapping(root["trial_family"])
        if (
            family["schema_id"] != _TRIAL_FAMILY_SCHEMA_ID
            or family["schema_version"] != _TRIAL_FAMILY_SCHEMA_VERSION
        ):
            raise _invalid("trial family schema is unsupported")
        objective = PromotionObjective(
            primary=_metric_from_payload(root["primary"]),
            hard_constraints=tuple(
                MetricConstraint(
                    _metric_value_from_payload(item["threshold"]),
                    ConstraintOperator(item["operator"]),
                )
                for raw_item in _list(root["hard_constraints"])
                for item in (_mapping(raw_item),)
            ),
            tie_break_order=tuple(
                _metric_from_payload(item) for item in _list(root["tie_break_order"])
            ),
            baseline_candidate_id=CandidateId(root["baseline_candidate_id"]),
            economic_rationale=root["economic_rationale"],
            trial_family=TrialFamilyDeclaration(
                family["family_id"],
                tuple(_trial_from_payload(item) for item in _list(family["members"])),
            ),
            pbo_partition_plan=_pbo_plan_from_payload(root["pbo_partition_plan"]),
            prior_trial_evidence=tuple(
                PriorTrialEvidenceDeclaration(
                    _trial_from_payload(item["trial"]),
                    ContentHash(item["outcome_content_hash"]),
                )
                for raw_item in _list(root["prior_trial_evidence"])
                for item in (_mapping(raw_item),)
            ),
        )
    except (KeyError, TypeError, ValueError, AnalysisError) as exc:
        if (
            isinstance(exc, ExperimentSpecError)
            and exc.details.get("reason_code") == "invalid_promotion_objective_graph"
        ):
            raise
        raise _invalid("promotion objective payload is malformed") from exc
    canonical = promotion_objective_payload(objective)
    if root != canonical:
        raise _invalid("promotion objective payload is not canonical")
    return validate_promotion_objective_graph(objective)
