"""Exact nominal-type and family edges for promotion objective contracts."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import cast

import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments import promotion_models
from ditto_analysis.experiments.metric_schema import (
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
    partition_observation_date_grid_hash,
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


def _hash(character: str) -> ContentHash:
    return ContentHash(character * 64)


def _trial(
    *,
    candidate: str = "candidate-1",
    ordinal: int = 1,
    kind: TrialKind = TrialKind.CURRENT,
) -> LogicalTrialIdentity:
    return LogicalTrialIdentity(
        ExperimentId("experiment-1"),
        CandidateId(candidate),
        ordinal,
        _hash(str(ordinal)),
        kind,
    )


def _objective(
    *,
    family: TrialFamilyDeclaration | None = None,
    prior_evidence: tuple[PriorTrialEvidenceDeclaration, ...] = (),
) -> PromotionObjective:
    current = _trial()
    return PromotionObjective(
        primary=ObjectiveMetric(
            ResearchMetricId.NET_RETURN,
            ResearchMetricDirection.MAXIMIZE,
        ),
        hard_constraints=(
            MetricConstraint(
                ResearchMetricValue(ResearchMetricId.MAX_DRAWDOWN, -20.0),
                ConstraintOperator.GREATER_THAN_OR_EQUAL,
            ),
        ),
        tie_break_order=(
            ObjectiveMetric(
                ResearchMetricId.TURNOVER,
                ResearchMetricDirection.MINIMIZE,
            ),
        ),
        baseline_candidate_id=current.candidate_id,
        economic_rationale="Capture robust returns after costs.",
        trial_family=(
            TrialFamilyDeclaration("family-1", (current,)) if family is None else family
        ),
        prior_trial_evidence=prior_evidence,
    )


def _sharpe_pbo_plan() -> PboPartitionPlan:
    partitions = tuple(
        PboPartitionIdentity(
            partition_id=f"partition-{ordinal}",
            ordinal=ordinal,
            window_start=date(2026, 1, 1) + timedelta(days=ordinal - 1),
            window_end=date(2026, 1, 1) + timedelta(days=ordinal - 1),
            observation_count=1,
            observation_date_grid_hash=partition_observation_date_grid_hash(
                (date(2026, 1, 1) + timedelta(days=ordinal - 1),)
            ),
        )
        for ordinal in range(1, 5)
    )
    return PboPartitionPlan(
        score_metric_id=ResearchMetricId.SHARPE_RATIO,
        direction=ResearchMetricDirection.MAXIMIZE,
        estimator=PboEstimator.SHARPE_RATIO,
        return_unit=SamplingReturnUnit.PER_PERIOD_DECIMAL,
        return_frequency=ReturnFrequency.DAILY,
        periods_per_year=252,
        partitions=partitions,
    )


def _reason(exc_info: pytest.ExceptionInfo[ExperimentSpecError]) -> object:
    return exc_info.value.details["reason_code"]


def test_ordered_contract_values_reject_strings_and_untyped_members() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        promotion_models._ordered_values("values", ObjectiveMetric, "values")
    assert _reason(exc_info) == "invalid_promotion_objective"

    with pytest.raises(ExperimentSpecError) as exc_info:
        promotion_models._ordered_values((object(),), ObjectiveMetric, "values")
    assert _reason(exc_info) == "invalid_promotion_objective"


def test_objective_metric_requires_rankable_exact_metric_nodes() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        ObjectiveMetric(
            cast("ResearchMetricId", "net_return"),
            ResearchMetricDirection.MAXIMIZE,
        )
    assert _reason(exc_info) == "invalid_objective_metric"

    with pytest.raises(ExperimentSpecError) as exc_info:
        ObjectiveMetric(
            ResearchMetricId.NET_RETURN,
            cast("ResearchMetricDirection", "maximize"),
        )
    assert _reason(exc_info) == "invalid_metric_direction"

    with pytest.raises(ExperimentSpecError) as exc_info:
        ObjectiveMetric(
            ResearchMetricId.DECAY,
            ResearchMetricDirection.CONTEXT_ONLY,
        )
    assert _reason(exc_info) == "unrankable_objective_metric"


def test_metric_constraint_requires_exact_threshold_and_operator() -> None:
    constraint = _objective().hard_constraints[0]
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(
            constraint,
            threshold=cast("ResearchMetricValue", object()),
        )
    assert _reason(exc_info) == "invalid_metric_constraint_threshold"

    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(
            constraint,
            operator=cast("ConstraintOperator", "greater_than_or_equal"),
        )
    assert _reason(exc_info) == "invalid_constraint_operator"


def test_prior_evidence_can_only_bind_a_prior_logical_trial() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        PriorTrialEvidenceDeclaration(_trial(), _hash("a"))
    assert _reason(exc_info) == "invalid_prior_trial_evidence_declaration"


def test_promotion_objective_requires_exact_primary_and_unique_metric_lists() -> None:
    objective = _objective()
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(objective, primary=cast("ObjectiveMetric", object()))
    assert _reason(exc_info) == "invalid_promotion_objective"

    constraint = objective.hard_constraints[0]
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(objective, hard_constraints=(constraint, constraint))
    assert _reason(exc_info) == "duplicate_constraint_metric"

    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(objective, tie_break_order=(objective.primary,))
    assert _reason(exc_info) == "duplicate_tie_break_metric"


def test_promotion_objective_rejects_untyped_identity_and_text_fields() -> None:
    objective = _objective()
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(
            objective,
            baseline_candidate_id=cast("CandidateId", "candidate-1"),
        )
    assert _reason(exc_info) == "invalid_promotion_objective"

    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(objective, economic_rationale=" ")
    assert _reason(exc_info) == "invalid_promotion_objective"

    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(
            objective,
            trial_family=cast("TrialFamilyDeclaration", object()),
        )
    assert _reason(exc_info) == "invalid_promotion_objective"


def test_promotion_objective_rejects_untyped_or_mismatched_pbo_plan() -> None:
    objective = _objective()
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(objective, pbo_partition_plan=cast("PboPartitionPlan", object()))
    assert _reason(exc_info) == "invalid_promotion_objective"

    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(objective, pbo_partition_plan=_sharpe_pbo_plan())
    assert _reason(exc_info) == "pbo_plan_objective_mismatch"


def test_prior_evidence_must_cover_family_once_and_baseline_must_be_current() -> None:
    current = _trial()
    prior = _trial(candidate="prior-candidate", ordinal=2, kind=TrialKind.PRIOR)
    family = TrialFamilyDeclaration("family-1", (current, prior))
    evidence = PriorTrialEvidenceDeclaration(prior, _hash("a"))
    objective = _objective(family=family, prior_evidence=(evidence,))

    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(objective, prior_trial_evidence=(evidence, evidence))
    assert _reason(exc_info) == "prior_trial_evidence_family_mismatch"

    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(objective, baseline_candidate_id=CandidateId("missing-baseline"))
    assert _reason(exc_info) == "promotion_baseline_trial_missing"
