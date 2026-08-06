"""Fail-closed Deflated Sharpe and CSCV PBO calculations."""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import combinations
from statistics import NormalDist, fmean, stdev, variance
from typing import cast

from ditto_analysis.experiments.metric_schema import ResearchMetricDirection
from ditto_analysis.experiments.models import CandidateId
from ditto_analysis.experiments.promotion_models import PromotionObjective
from ditto_analysis.experiments.trial_outcomes import TrialOutcome, TrialStatus
from ditto_analysis.experiments.trial_statistics import (
    MAX_PBO_COMBINATIONS,
    DeflatedSharpeEvidence,
    EvidenceStatus,
    PboEstimator,
    PboEvidence,
    PboSamplingEvidence,
    ReturnFrequency,
    SharpeSamplingEvidence,
)

__all__ = ["deflated_sharpe_evidence", "pbo_evidence"]

_EULER_MASCHERONI = 0.5772156649015329
_DSR_METHOD = "bailey_lopez_de_prado_deflated_sharpe"
_PBO_METHOD = "combinatorially_symmetric_cross_validation_pbo"
_PREREQUISITES_SATISFIED = "method_prerequisites_satisfied"
_MIN_STATISTICAL_TRIALS = 2
_MIN_SHARPE_RETURNS = 2
_MIN_PBO_PARTITIONS = 4
_TIE_METHOD = "midrank_average_in_sample_ties"
_OVERFIT_LAMBDA_THRESHOLD = 0.0
_DSR_PREREQUISITES = (
    "exact_declared_trial_family_observed",
    "all_declared_trials_completed",
    "all_declared_trials_have_hashed_sharpe_sampling_evidence",
    "aligned_sampling_frequency_and_scale",
    "annualized_sharpe_converted_to_per_period",
    "positive_sharpe_dispersion",
    "positive_sharpe_sampling_variance",
)
_PBO_PREREQUISITES = (
    "exact_declared_trial_family_observed",
    "all_declared_trials_completed_with_hashed_partition_returns",
    "aligned_partition_identity_and_sampling_schema",
    "non_overlapping_equal_count_partitions",
    "combined_performance_recomputed_from_raw_returns",
    "streamed_combinations_within_budget",
    "midrank_ties_and_strict_negative_lambda",
)


def _deflated_not_evaluated(
    objective: PromotionObjective,
    trials: tuple[TrialOutcome, ...],
    reason: str,
    *,
    candidate_id: CandidateId | None = None,
    completed_count: int = 0,
    frequency: ReturnFrequency | None = None,
    periods_per_year: int | None = None,
) -> DeflatedSharpeEvidence:
    return DeflatedSharpeEvidence(
        status=EvidenceStatus.NOT_EVALUATED,
        method=_DSR_METHOD,
        method_prerequisites=_DSR_PREREQUISITES,
        reason=reason,
        candidate_id=candidate_id,
        probability=None,
        observed_sharpe=None,
        expected_max_sharpe=None,
        declared_trial_count=objective.declared_trial_count,
        observed_trial_count=len(trials),
        completed_sharpe_trial_count=completed_count,
        return_frequency=frequency,
        periods_per_year=periods_per_year,
    )


def _deflated_prerequisite_failure(  # noqa: PLR0911 - fail-closed reasons
    objective: PromotionObjective,
    trials: tuple[TrialOutcome, ...],
    ranked_trials: tuple[TrialOutcome, ...],
) -> DeflatedSharpeEvidence | None:
    completed_count = sum(
        trial.status is TrialStatus.COMPLETED and trial.sharpe_sampling is not None
        for trial in trials
    )
    if objective.trial_family.prior_members and not objective.prior_trial_evidence:
        return _deflated_not_evaluated(
            objective,
            trials,
            "prior_trial_evidence_not_preregistered",
            completed_count=completed_count,
        )
    if any(trial.status is TrialStatus.FAILED for trial in trials):
        return _deflated_not_evaluated(
            objective,
            trials,
            "failed_trial_in_family",
            completed_count=completed_count,
        )
    if not ranked_trials:
        return _deflated_not_evaluated(
            objective,
            trials,
            "no_eligible_current_trial",
            completed_count=completed_count,
        )
    if any(trial.sharpe_sampling is None for trial in trials):
        return _deflated_not_evaluated(
            objective,
            trials,
            "incomplete_sharpe_sampling_family",
            candidate_id=ranked_trials[0].candidate_id,
            completed_count=completed_count,
        )
    if len(trials) < _MIN_STATISTICAL_TRIALS:
        return _deflated_not_evaluated(
            objective,
            trials,
            "insufficient_trial_count",
            candidate_id=ranked_trials[0].candidate_id,
            completed_count=completed_count,
        )
    samplings = tuple(
        cast("SharpeSamplingEvidence", trial.sharpe_sampling) for trial in trials
    )
    first_sampling = samplings[0]
    if any(
        sampling.return_frequency is not first_sampling.return_frequency
        or sampling.periods_per_year != first_sampling.periods_per_year
        for sampling in samplings
    ):
        return _deflated_not_evaluated(
            objective,
            trials,
            "unaligned_sharpe_sampling_frequency",
            candidate_id=ranked_trials[0].candidate_id,
            completed_count=completed_count,
        )
    return None


def deflated_sharpe_evidence(
    objective: PromotionObjective,
    trials: tuple[TrialOutcome, ...],
    ranked_trials: tuple[TrialOutcome, ...],
) -> DeflatedSharpeEvidence:
    """Calculate DSR only from complete, aligned, per-period family evidence."""
    prerequisite_failure = _deflated_prerequisite_failure(
        objective,
        trials,
        ranked_trials,
    )
    if prerequisite_failure is not None:
        return prerequisite_failure
    completed_count = len(trials)
    samplings = tuple(
        cast("SharpeSamplingEvidence", trial.sharpe_sampling) for trial in trials
    )
    first_sampling = samplings[0]
    selected = ranked_trials[0]
    selected_sampling = cast("SharpeSamplingEvidence", selected.sharpe_sampling)
    per_period_sharpes = tuple(sampling.per_period_sharpe for sampling in samplings)
    sharpe_dispersion = variance(per_period_sharpes)
    if sharpe_dispersion <= 0.0:
        return _deflated_not_evaluated(
            objective,
            trials,
            "non_positive_sharpe_dispersion",
            candidate_id=selected.candidate_id,
            completed_count=completed_count,
            frequency=first_sampling.return_frequency,
            periods_per_year=first_sampling.periods_per_year,
        )
    trial_count = objective.declared_trial_count
    normal = NormalDist()
    expected_max = math.sqrt(sharpe_dispersion) * (
        (1.0 - _EULER_MASCHERONI) * normal.inv_cdf(1.0 - (1.0 / trial_count))
        + _EULER_MASCHERONI * normal.inv_cdf(1.0 - (1.0 / (trial_count * math.e)))
    )
    observed_sharpe = selected_sampling.per_period_sharpe
    sampling_variance = (
        1.0
        - selected_sampling.return_skewness * observed_sharpe
        + ((selected_sampling.pearson_kurtosis - 1.0) / 4.0) * observed_sharpe**2
    )
    if sampling_variance <= 0.0:
        return _deflated_not_evaluated(
            objective,
            trials,
            "non_positive_sharpe_sampling_variance",
            candidate_id=selected.candidate_id,
            completed_count=completed_count,
            frequency=first_sampling.return_frequency,
            periods_per_year=first_sampling.periods_per_year,
        )
    statistic = (
        (observed_sharpe - expected_max)
        * math.sqrt(selected_sampling.observation_count - 1)
        / math.sqrt(sampling_variance)
    )
    return DeflatedSharpeEvidence(
        status=EvidenceStatus.EVALUATED,
        method=_DSR_METHOD,
        method_prerequisites=_DSR_PREREQUISITES,
        reason=_PREREQUISITES_SATISFIED,
        candidate_id=selected.candidate_id,
        probability=normal.cdf(statistic),
        observed_sharpe=observed_sharpe,
        expected_max_sharpe=expected_max,
        declared_trial_count=trial_count,
        observed_trial_count=len(trials),
        completed_sharpe_trial_count=completed_count,
        return_frequency=first_sampling.return_frequency,
        periods_per_year=first_sampling.periods_per_year,
    )


def _pbo_not_evaluated(
    objective: PromotionObjective,
    trials: tuple[TrialOutcome, ...],
    reason: str,
    *,
    sampling: PboSamplingEvidence | None = None,
    partition_count: int | None = None,
    combination_budget: int = MAX_PBO_COMBINATIONS,
    combination_count: int = 0,
) -> PboEvidence:
    return PboEvidence(
        status=EvidenceStatus.NOT_EVALUATED,
        method=_PBO_METHOD,
        method_prerequisites=_PBO_PREREQUISITES,
        reason=reason,
        probability=None,
        declared_trial_count=objective.declared_trial_count,
        observed_trial_count=len(trials),
        partition_count=partition_count,
        combination_budget=combination_budget,
        combination_count=combination_count,
        evaluated_combination_count=0,
        score_metric_id=None if sampling is None else sampling.score_metric_id,
        direction=None if sampling is None else sampling.direction,
        estimator=None if sampling is None else sampling.estimator,
        tie_method=_TIE_METHOD,
        overfit_lambda_threshold=_OVERFIT_LAMBDA_THRESHOLD,
    )


def _combined_performance(
    sampling: PboSamplingEvidence,
    indices: Sequence[int],
) -> float:
    returns = tuple(
        value for index in indices for value in sampling.partitions[index].returns
    )
    if sampling.estimator is PboEstimator.COMPOUND_RETURN:
        return math.prod(1.0 + value for value in returns) - 1.0
    mean_return = fmean(returns)
    if len(returns) < _MIN_SHARPE_RETURNS:
        return 0.0
    volatility = stdev(returns)
    if volatility == 0.0:
        if mean_return == 0.0:
            return 0.0
        return math.copysign(math.inf, mean_return)
    return mean_return / volatility


def _equal_score(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-15)


def _in_sample_winners(
    samplings: tuple[PboSamplingEvidence, ...],
    indices: Sequence[int],
    direction: ResearchMetricDirection,
) -> tuple[int, ...]:
    scores = tuple(_combined_performance(item, indices) for item in samplings)
    best = max(scores) if direction is ResearchMetricDirection.MAXIMIZE else min(scores)
    return tuple(
        index for index, score in enumerate(scores) if _equal_score(score, best)
    )


def _midrank_worst_first(
    score: float,
    scores: tuple[float, ...],
    direction: ResearchMetricDirection,
) -> float:
    tied = sum(_equal_score(item, score) for item in scores)
    if direction is ResearchMetricDirection.MAXIMIZE:
        strictly_worse = sum(
            item < score and not _equal_score(item, score) for item in scores
        )
    else:
        strictly_worse = sum(
            item > score and not _equal_score(item, score) for item in scores
        )
    return strictly_worse + 1.0 + ((tied - 1.0) / 2.0)


def _split_lambda(
    samplings: tuple[PboSamplingEvidence, ...],
    in_sample: Sequence[int],
    out_of_sample: Sequence[int],
) -> float:
    direction = samplings[0].direction
    winners = _in_sample_winners(samplings, in_sample, direction)
    out_scores = tuple(_combined_performance(item, out_of_sample) for item in samplings)
    trial_count = len(samplings)
    lambdas: list[float] = []
    for winner in winners:
        rank = _midrank_worst_first(out_scores[winner], out_scores, direction)
        lambdas.append(math.log(rank / (trial_count + 1.0 - rank)))
    return fmean(lambdas)


def _aligned_pbo_sampling(  # noqa: PLR0911 - explicit alignment reasons
    objective: PromotionObjective,
    trials: tuple[TrialOutcome, ...],
) -> tuple[PboSamplingEvidence | None, str | None]:
    if any(trial.status is TrialStatus.FAILED for trial in trials):
        return None, "failed_trial_in_family"
    if any(trial.pbo_sampling is None for trial in trials):
        return None, "incomplete_trial_partition_evidence"
    samplings = tuple(
        trial.pbo_sampling for trial in trials if trial.pbo_sampling is not None
    )
    first = samplings[0]
    plan = objective.pbo_partition_plan
    if plan is None:
        return first, "pbo_partition_plan_not_preregistered"
    plan_schema = (
        plan.score_metric_id,
        plan.direction,
        plan.estimator,
        plan.return_unit,
        plan.return_frequency,
        plan.periods_per_year,
    )
    if any(
        (
            item.score_metric_id,
            item.direction,
            item.estimator,
            item.return_unit,
            item.return_frequency,
            item.periods_per_year,
        )
        != plan_schema
        or tuple(partition.identity for partition in item.partitions) != plan.partitions
        for item in samplings
    ):
        return first, "pbo_partition_plan_mismatch"
    if any(
        (
            item.score_metric_id,
            item.direction,
            item.estimator,
            item.return_unit,
            item.return_frequency,
            item.periods_per_year,
        )
        != (
            first.score_metric_id,
            first.direction,
            first.estimator,
            first.return_unit,
            first.return_frequency,
            first.periods_per_year,
        )
        for item in samplings
    ):
        return first, "unaligned_pbo_sampling_schema"
    if first.score_metric_id is not objective.primary.metric_id:
        return first, "pbo_objective_metric_mismatch"
    identities = tuple(partition.identity for partition in first.partitions)
    if any(
        tuple(partition.identity for partition in item.partitions) != identities
        for item in samplings[1:]
    ):
        return first, "unaligned_pbo_partition_identity"
    return first, None


def pbo_evidence(  # noqa: PLR0911 - explicit fail-closed reasons
    objective: PromotionObjective,
    trials: tuple[TrialOutcome, ...],
    *,
    combination_budget: int = MAX_PBO_COMBINATIONS,
) -> PboEvidence:
    """Calculate PBO from streamed CSCV combinations and recomputed returns."""
    if objective.trial_family.prior_members and not objective.prior_trial_evidence:
        return _pbo_not_evaluated(
            objective,
            trials,
            "prior_trial_evidence_not_preregistered",
            combination_budget=combination_budget,
        )
    if objective.pbo_partition_plan is None:
        return _pbo_not_evaluated(
            objective,
            trials,
            "pbo_partition_plan_not_preregistered",
            combination_budget=combination_budget,
        )
    if len(trials) < _MIN_STATISTICAL_TRIALS:
        return _pbo_not_evaluated(
            objective,
            trials,
            "insufficient_trial_count",
            combination_budget=combination_budget,
        )
    first, alignment_failure = _aligned_pbo_sampling(objective, trials)
    if alignment_failure is not None or first is None:
        return _pbo_not_evaluated(
            objective,
            trials,
            alignment_failure or "incomplete_trial_partition_evidence",
            sampling=first,
            combination_budget=combination_budget,
        )
    partition_count = len(first.partitions)
    partition_failure = (
        "insufficient_partition_count"
        if partition_count < _MIN_PBO_PARTITIONS
        else "partition_count_must_be_even"
        if partition_count % 2
        else None
    )
    if partition_failure is not None:
        return _pbo_not_evaluated(
            objective,
            trials,
            partition_failure,
            sampling=first,
            partition_count=partition_count,
            combination_budget=combination_budget,
        )
    combination_count = math.comb(partition_count, partition_count // 2)
    if combination_count > combination_budget:
        return _pbo_not_evaluated(
            objective,
            trials,
            "pbo_combination_budget_exceeded",
            sampling=first,
            partition_count=partition_count,
            combination_budget=combination_budget,
            combination_count=combination_count,
        )
    samplings = tuple(
        trial.pbo_sampling for trial in trials if trial.pbo_sampling is not None
    )
    all_indices = tuple(range(partition_count))
    overfit_count = 0
    evaluated_count = 0
    for in_sample in combinations(all_indices, partition_count // 2):
        selected = frozenset(in_sample)
        out_of_sample = tuple(index for index in all_indices if index not in selected)
        split_lambda = _split_lambda(samplings, in_sample, out_of_sample)
        overfit_count += split_lambda < _OVERFIT_LAMBDA_THRESHOLD
        evaluated_count += 1
    return PboEvidence(
        status=EvidenceStatus.EVALUATED,
        method=_PBO_METHOD,
        method_prerequisites=_PBO_PREREQUISITES,
        reason=_PREREQUISITES_SATISFIED,
        probability=overfit_count / evaluated_count,
        declared_trial_count=objective.declared_trial_count,
        observed_trial_count=len(trials),
        partition_count=partition_count,
        combination_budget=combination_budget,
        combination_count=combination_count,
        evaluated_combination_count=evaluated_count,
        score_metric_id=first.score_metric_id,
        direction=first.direction,
        estimator=first.estimator,
        tie_method=_TIE_METHOD,
        overfit_lambda_threshold=_OVERFIT_LAMBDA_THRESHOLD,
    )
