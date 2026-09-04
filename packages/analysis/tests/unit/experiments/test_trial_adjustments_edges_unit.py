"""Fail-closed and numerical edges for multiple-testing adjustments."""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import cast

import pytest
from ditto_analysis.experiments import trial_adjustments
from ditto_analysis.experiments.metric_schema import (
    ResearchMetricDirection,
    ResearchMetricId,
)
from ditto_analysis.experiments.pbo_plan import (
    PboEstimator,
    ReturnFrequency,
    SamplingReturnUnit,
)
from ditto_analysis.experiments.promotion_models import PromotionObjective
from ditto_analysis.experiments.trial_outcomes import TrialOutcome, TrialStatus
from ditto_analysis.experiments.trial_statistics import (
    PboSamplingEvidence,
    SharpeSamplingEvidence,
)


def _sharpe_sampling(
    per_period_sharpe: float,
    **overrides: object,
) -> SharpeSamplingEvidence:
    values: dict[str, object] = {
        "per_period_sharpe": per_period_sharpe,
        "return_frequency": ReturnFrequency.DAILY,
        "periods_per_year": 252,
        "return_skewness": 0.0,
        "pearson_kurtosis": 3.0,
        "observation_count": 20,
    }
    values.update(overrides)
    return cast(
        "SharpeSamplingEvidence",
        cast("object", SimpleNamespace(**values)),
    )


def _pbo_sampling(
    returns: tuple[tuple[float, ...], ...],
    **overrides: object,
) -> PboSamplingEvidence:
    identities = cast(
        "tuple[str, ...]",
        overrides.pop(
            "identities",
            tuple(f"partition-{index}" for index in range(1, len(returns) + 1)),
        ),
    )
    partitions = tuple(
        SimpleNamespace(identity=identity, returns=values)
        for identity, values in zip(identities, returns, strict=True)
    )
    values: dict[str, object] = {
        "score_metric_id": ResearchMetricId.NET_RETURN,
        "direction": ResearchMetricDirection.MAXIMIZE,
        "estimator": PboEstimator.COMPOUND_RETURN,
        "return_unit": SamplingReturnUnit.PER_PERIOD_DECIMAL,
        "return_frequency": ReturnFrequency.DAILY,
        "periods_per_year": 252,
        "partitions": partitions,
    }
    values.update(overrides)
    return cast(
        "PboSamplingEvidence",
        cast("object", SimpleNamespace(**values)),
    )


def _trial(
    *,
    sharpe_sampling: SharpeSamplingEvidence | None = None,
    pbo_sampling: PboSamplingEvidence | None = None,
    status: TrialStatus = TrialStatus.COMPLETED,
    candidate_id: str = "candidate",
) -> TrialOutcome:
    return cast(
        "TrialOutcome",
        cast(
            "object",
            SimpleNamespace(
                sharpe_sampling=sharpe_sampling,
                pbo_sampling=pbo_sampling,
                status=status,
                candidate_id=candidate_id,
            ),
        ),
    )


def _plan(
    partitions: tuple[str, ...],
    **overrides: object,
) -> object:
    values: dict[str, object] = {
        "score_metric_id": ResearchMetricId.NET_RETURN,
        "direction": ResearchMetricDirection.MAXIMIZE,
        "estimator": PboEstimator.COMPOUND_RETURN,
        "return_unit": SamplingReturnUnit.PER_PERIOD_DECIMAL,
        "return_frequency": ReturnFrequency.DAILY,
        "periods_per_year": 252,
        "partitions": partitions,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _objective(
    *,
    declared_trial_count: int = 2,
    pbo_partition_plan: object | None = None,
    primary_metric: ResearchMetricId = ResearchMetricId.NET_RETURN,
    prior_members: tuple[object, ...] = (),
    prior_trial_evidence: tuple[object, ...] = (),
) -> PromotionObjective:
    return cast(
        "PromotionObjective",
        cast(
            "object",
            SimpleNamespace(
                declared_trial_count=declared_trial_count,
                pbo_partition_plan=pbo_partition_plan,
                primary=SimpleNamespace(metric_id=primary_metric),
                trial_family=SimpleNamespace(prior_members=prior_members),
                prior_trial_evidence=prior_trial_evidence,
            ),
        ),
    )


@pytest.mark.parametrize(
    ("returns", "expected"),
    [
        (((0.1,),), 0.0),
        (((0.0, 0.0),), 0.0),
        (((0.1, 0.1),), math.inf),
        (((-0.1, -0.1),), -math.inf),
        (((0.0, 0.2),), math.sqrt(0.5)),
    ],
)
def test_sharpe_split_performance_handles_short_constant_and_variable_returns(
    returns: tuple[tuple[float, ...], ...],
    expected: float,
) -> None:
    sampling = _pbo_sampling(returns, estimator=PboEstimator.SHARPE_RATIO)

    result = trial_adjustments._combined_performance(sampling, (0,))

    assert result == pytest.approx(expected)


def test_compound_split_performance_recomputes_from_raw_returns() -> None:
    sampling = _pbo_sampling(((0.1, -0.05),))

    result = trial_adjustments._combined_performance(sampling, (0,))

    assert result == pytest.approx(0.045)


def test_minimization_midrank_counts_larger_scores_as_worse() -> None:
    rank = trial_adjustments._midrank_worst_first(
        1.0,
        (1.0, 1.0, 2.0),
        ResearchMetricDirection.MINIMIZE,
    )

    assert rank == 2.5


def test_deflated_sharpe_requires_at_least_two_trials() -> None:
    sampling = _sharpe_sampling(0.5)
    trial = _trial(sharpe_sampling=sampling)

    evidence = trial_adjustments.deflated_sharpe_evidence(
        _objective(),
        (trial,),
        (trial,),
    )

    assert evidence.reason == "insufficient_trial_count"
    assert evidence.completed_sharpe_trial_count == 1


def test_deflated_sharpe_rejects_unaligned_sampling_frequency() -> None:
    daily = _trial(sharpe_sampling=_sharpe_sampling(0.5), candidate_id="daily")
    weekly = _trial(
        sharpe_sampling=_sharpe_sampling(
            0.4,
            return_frequency=ReturnFrequency.WEEKLY,
            periods_per_year=52,
        ),
        candidate_id="weekly",
    )

    evidence = trial_adjustments.deflated_sharpe_evidence(
        _objective(),
        (daily, weekly),
        (daily, weekly),
    )

    assert evidence.reason == "unaligned_sharpe_sampling_frequency"


def test_deflated_sharpe_rejects_non_positive_sampling_variance() -> None:
    selected = _trial(
        sharpe_sampling=_sharpe_sampling(
            1.0,
            return_skewness=2.0,
            pearson_kurtosis=1.0,
        ),
        candidate_id="selected",
    )
    comparison = _trial(
        sharpe_sampling=_sharpe_sampling(0.0),
        candidate_id="comparison",
    )

    evidence = trial_adjustments.deflated_sharpe_evidence(
        _objective(),
        (selected, comparison),
        (selected, comparison),
    )

    assert evidence.reason == "non_positive_sharpe_sampling_variance"
    assert evidence.candidate_id == "selected"


def test_pbo_alignment_rejects_failed_and_incomplete_trials() -> None:
    sampling = _pbo_sampling(((0.1,),) * 4)
    objective = _objective(
        pbo_partition_plan=_plan(
            tuple(partition.identity for partition in sampling.partitions),
        ),
    )

    failed = trial_adjustments._aligned_pbo_sampling(
        objective,
        (_trial(pbo_sampling=sampling, status=TrialStatus.FAILED),),
    )
    incomplete = trial_adjustments._aligned_pbo_sampling(
        objective,
        (_trial(pbo_sampling=None),),
    )

    assert failed == (None, "failed_trial_in_family")
    assert incomplete == (None, "incomplete_trial_partition_evidence")


def test_pbo_alignment_requires_a_preregistered_exact_plan() -> None:
    sampling = _pbo_sampling(((0.1,),) * 4)
    trial = _trial(pbo_sampling=sampling)

    missing_plan = trial_adjustments._aligned_pbo_sampling(
        _objective(),
        (trial,),
    )
    mismatched_plan = trial_adjustments._aligned_pbo_sampling(
        _objective(
            pbo_partition_plan=_plan(
                tuple(partition.identity for partition in sampling.partitions),
                periods_per_year=52,
            ),
        ),
        (trial,),
    )

    assert missing_plan == (sampling, "pbo_partition_plan_not_preregistered")
    assert mismatched_plan == (sampling, "pbo_partition_plan_mismatch")


def test_pbo_alignment_rejects_objective_metric_substitution() -> None:
    sampling = _pbo_sampling(((0.1,),) * 4)
    plan = _plan(tuple(partition.identity for partition in sampling.partitions))

    result = trial_adjustments._aligned_pbo_sampling(
        _objective(
            pbo_partition_plan=plan,
            primary_metric=ResearchMetricId.SHARPE_RATIO,
        ),
        (_trial(pbo_sampling=sampling),),
    )

    assert result == (sampling, "pbo_objective_metric_mismatch")


def test_pbo_alignment_accepts_matching_sampling_evidence() -> None:
    sampling = _pbo_sampling(((0.1,),) * 4)
    plan = _plan(tuple(partition.identity for partition in sampling.partitions))

    result = trial_adjustments._aligned_pbo_sampling(
        _objective(pbo_partition_plan=plan),
        (_trial(pbo_sampling=sampling), _trial(pbo_sampling=sampling)),
    )

    assert result == (sampling, None)


def test_pbo_requires_at_least_two_trials() -> None:
    sampling = _pbo_sampling(((0.1,),) * 4)
    plan = _plan(tuple(partition.identity for partition in sampling.partitions))

    evidence = trial_adjustments.pbo_evidence(
        _objective(pbo_partition_plan=plan),
        (_trial(pbo_sampling=sampling),),
    )

    assert evidence.reason == "insufficient_trial_count"
    assert evidence.observed_trial_count == 1


@pytest.mark.parametrize(
    ("partition_count", "expected_reason"),
    [
        (3, "insufficient_partition_count"),
        (5, "partition_count_must_be_even"),
    ],
)
def test_pbo_rejects_invalid_partition_cardinality(
    partition_count: int,
    expected_reason: str,
) -> None:
    sampling = _pbo_sampling(((0.1,),) * partition_count)
    plan = _plan(tuple(partition.identity for partition in sampling.partitions))

    evidence = trial_adjustments.pbo_evidence(
        _objective(pbo_partition_plan=plan),
        (_trial(pbo_sampling=sampling), _trial(pbo_sampling=sampling)),
    )

    assert evidence.reason == expected_reason
    assert evidence.partition_count == partition_count
