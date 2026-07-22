"""Unit tests for the canonical promotion-objective evidence codec."""

from copy import deepcopy
from datetime import date, timedelta

import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments import (
    R3_RESEARCH_METRIC_SCHEMA,
    CandidateId,
    ContentHash,
    ExperimentId,
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
)
from ditto_analysis.experiments.promotion_objective import (
    decode_promotion_objective,
    promotion_objective_payload,
)
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialFamilyDeclaration,
    TrialKind,
)
from ditto_analysis.experiments.trial_ledger import (
    ConstraintOperator,
    MetricConstraint,
    ObjectiveMetric,
    PromotionObjective,
)
from ditto_analysis.experiments.trial_statistics import (
    PboEstimator,
    PboPartitionIdentity,
    PboPartitionPlan,
    ReturnFrequency,
    SamplingReturnUnit,
    partition_observation_date_grid_hash,
)


def _pbo_plan() -> PboPartitionPlan:
    return PboPartitionPlan(
        score_metric_id=ResearchMetricId.NET_RETURN,
        direction=ResearchMetricDirection.MAXIMIZE,
        estimator=PboEstimator.COMPOUND_RETURN,
        return_unit=SamplingReturnUnit.PER_PERIOD_DECIMAL,
        return_frequency=ReturnFrequency.DAILY,
        periods_per_year=252,
        partitions=tuple(
            PboPartitionIdentity(
                f"partition-{ordinal}",
                ordinal,
                date(2026, 1, 1) + timedelta(days=ordinal - 1),
                date(2026, 1, 1) + timedelta(days=ordinal - 1),
                1,
                partition_observation_date_grid_hash(
                    (date(2026, 1, 1) + timedelta(days=ordinal - 1),)
                ),
            )
            for ordinal in range(1, 5)
        ),
    )


def _objective(*, pbo_plan: PboPartitionPlan | None = None) -> PromotionObjective:
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
        baseline_candidate_id=CandidateId("candidate-1"),
        economic_rationale="Capture durable returns after costs.",
        trial_family=TrialFamilyDeclaration(
            "family-1",
            (
                LogicalTrialIdentity(
                    ExperimentId("experiment-1"),
                    CandidateId("candidate-1"),
                    1,
                    ContentHash("a" * 64),
                    TrialKind.CURRENT,
                ),
            ),
        ),
        pbo_partition_plan=pbo_plan,
    )


def test_objective_payload_binds_the_complete_metric_schema() -> None:
    payload = promotion_objective_payload(_objective())

    assert payload["schema_id"] == "r3-promotion-objective"
    assert payload["schema_version"] == 1
    assert payload["metric_schema"] == R3_RESEARCH_METRIC_SCHEMA.canonical_payload()
    family = payload["trial_family"]
    assert isinstance(family, dict)
    assert family["schema_id"] == "r3-trial-family"
    assert family["schema_version"] == 1
    assert decode_promotion_objective(payload) == _objective()


def test_objective_payload_freezes_the_exact_pbo_partition_plan() -> None:
    objective = _objective(pbo_plan=_pbo_plan())

    payload = promotion_objective_payload(objective)

    assert payload["pbo_partition_plan"] == _pbo_plan().canonical_payload()
    assert decode_promotion_objective(payload) == objective

    changed = deepcopy(payload)
    plan = changed["pbo_partition_plan"]
    assert isinstance(plan, dict)
    partitions = plan["partitions"]
    assert isinstance(partitions, list)
    partition = partitions[0]
    assert isinstance(partition, dict)
    partition["window_start"] = "2025-12-31"

    changed_objective = decode_promotion_objective(changed)

    assert changed_objective != objective
    assert promotion_objective_payload(changed_objective) == changed


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("unit", "ratio"),
        ("direction", "minimize"),
        ("scale", "annualized"),
        ("periods_per_year", 365),
        ("minimum", -99.0),
        ("maximum", 999.0),
    ],
)
def test_objective_decoder_rejects_metric_schema_field_drift(
    field: str,
    replacement: object,
) -> None:
    payload = deepcopy(promotion_objective_payload(_objective()))
    metric_schema = payload["metric_schema"]
    assert isinstance(metric_schema, dict)
    definitions = metric_schema["definitions"]
    assert isinstance(definitions, list)
    definition = definitions[0]
    assert isinstance(definition, dict)
    definition[field] = replacement

    with pytest.raises(ExperimentSpecError) as exc_info:
        decode_promotion_objective(payload)

    assert exc_info.value.details["reason_code"] == (
        "invalid_promotion_objective_graph"
    )
