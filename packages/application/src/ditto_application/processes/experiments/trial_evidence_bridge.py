"""Fail-closed bridge from walk-forward evidence to logical trial outcomes."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import InitVar, dataclass
from datetime import date
from statistics import fmean
from typing import NoReturn, cast

from ditto_analysis.errors import AnalysisError
from ditto_analysis.experiments import (
    R3_RESEARCH_METRIC_SCHEMA,
    CandidateExecutionBinding,
    CandidateId,
    ContentHash,
    ExperimentId,
    ExperimentLaunchSpec,
    ResearchMetricId,
    ResearchMetricValue,
    canonical_payload,
    decode_launch_spec,
    encode_launch_spec,
)
from ditto_analysis.experiments.promotion_models import PromotionObjective
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialKind,
)
from ditto_analysis.experiments.trial_ledger import (
    TrialLedger,
    trial_outcome_content_hash,
)
from ditto_analysis.experiments.trial_outcomes import (
    MetricEvidenceLineage,
    TrialOutcome,
    TrialStatus,
)
from ditto_analysis.experiments.trial_statistics import (
    PboPartitionPlan,
    PboPartitionReturns,
    PboSamplingEvidence,
    ReturnFrequency,
    SamplingReturnUnit,
    SharpeRatioScale,
    SharpeSamplingEvidence,
    partition_observation_date_grid_hash,
    partition_returns_hash,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.comparison import EvidenceStatus
from ditto_application.processes.experiments.walk_forward import (
    CandidateWalkForwardStatus,
    StitchedReturnEvidence,
    WalkForwardAggregation,
    WalkForwardCandidate,
)

__all__ = [
    "VerifiedPreHoldoutSelectionEvidence",
    "project_walk_forward_trial_outcomes",
    "verify_pre_holdout_selection_evidence",
]

_TRADING_DAYS_PER_YEAR = 252
_MIN_SHARPE_OBSERVATIONS = 2
_VERIFIED_SELECTION_FACTORY_TOKEN = object()


def _bridge_error(reason: str, **details: object) -> NoReturn:
    raise AppProcessError(
        "walk-forward trial evidence bridge is invalid",
        details={"code": "SPEC_INVALID", "reason": reason, **details},
    )


def _selection_evidence_error(reason: str, **details: object) -> NoReturn:
    raise AppProcessError(
        "pre-holdout selection evidence is invalid",
        details={"code": "SPEC_INVALID", "reason": reason, **details},
    )


@dataclass(frozen=True, slots=True)
class VerifiedPreHoldoutSelectionEvidence:
    """Factory-sealed proof that selection used untouched pre-holdout evidence."""

    experiment_id: ExperimentId
    candidate_id: CandidateId
    content_hash: ContentHash
    _factory_token: InitVar[object | None] = None

    def __post_init__(self, _factory_token: object | None) -> None:
        """Prevent callers from minting verified selection evidence."""
        if (
            _factory_token is not _VERIFIED_SELECTION_FACTORY_TOKEN
            or type(self.experiment_id) is not ExperimentId
            or type(self.candidate_id) is not CandidateId
            or type(self.content_hash) is not ContentHash
        ):
            _selection_evidence_error("selection_evidence_factory_required")


def verify_pre_holdout_selection_evidence(
    ledger: object,
    *,
    experiment_id: ExperimentId,
    candidate_id: CandidateId,
    expected_content_hash: ContentHash,
) -> VerifiedPreHoldoutSelectionEvidence:
    """Verify one ranked current candidate before any holdout evidence exists."""
    if (
        type(ledger) is not TrialLedger
        or type(experiment_id) is not ExperimentId
        or type(candidate_id) is not CandidateId
        or type(expected_content_hash) is not ContentHash
    ):
        _selection_evidence_error("invalid_selection_evidence_contract")
    typed_ledger = ledger
    try:
        observed_content_hash = typed_ledger.content_hash
    except AnalysisError:
        _selection_evidence_error("invalid_selection_evidence_ledger")
    if observed_content_hash != expected_content_hash:
        _selection_evidence_error(
            "selection_evidence_hash_mismatch",
            expected_content_hash=str(expected_content_hash),
            observed_content_hash=str(observed_content_hash),
        )

    current_trials = tuple(
        trial for trial in typed_ledger.trials if trial.trial.kind is TrialKind.CURRENT
    )
    if not current_trials or any(
        trial.trial.origin_experiment_id != experiment_id for trial in current_trials
    ):
        _selection_evidence_error("selection_evidence_experiment_mismatch")
    if any(
        trial.holdout_metrics or trial.holdout_metric_evidence
        for trial in current_trials
    ):
        _selection_evidence_error("selection_evidence_holdout_already_consumed")

    selected = tuple(
        trial for trial in current_trials if trial.candidate_id == candidate_id
    )
    if (
        len(selected) != 1
        or selected[0].status is not TrialStatus.COMPLETED
        or selected[0].trial not in typed_ledger.ranked_trial_ids
    ):
        _selection_evidence_error("selection_evidence_candidate_not_ranked")
    return VerifiedPreHoldoutSelectionEvidence(
        experiment_id,
        candidate_id,
        observed_content_hash,
        _factory_token=_VERIFIED_SELECTION_FACTORY_TOKEN,
    )


def _validate_candidate_lineage(
    candidate: WalkForwardCandidate,
    experiment_id: ExperimentId,
    expected_folds: tuple[tuple[object, int], ...],
    execution_binding: CandidateExecutionBinding,
) -> None:
    if not candidate.folds:
        _bridge_error("walk_forward_candidate_lineage_missing")
    observed = tuple((fold.fold_id, fold.fold_ordinal) for fold in candidate.folds)
    if len(set(observed)) != len(observed) or any(
        fold.source.experiment_id != experiment_id
        or fold.candidate_id != candidate.candidate_id
        or fold.candidate_ordinal != candidate.candidate_ordinal
        or fold.source.parameter_hash != execution_binding.parameter_hash
        or fold.source.resolved_spec_hash != execution_binding.resolved_spec_hash
        for fold in candidate.folds
    ):
        _bridge_error("walk_forward_candidate_lineage_drift")
    if candidate.status is CandidateWalkForwardStatus.COMPLETED:
        if observed != expected_folds:
            _bridge_error("walk_forward_candidate_lineage_drift")
    elif any(item not in expected_folds for item in observed):
        _bridge_error("walk_forward_candidate_lineage_drift")


def _metric_projection(
    candidate: WalkForwardCandidate,
) -> tuple[
    dict[ResearchMetricId, ResearchMetricValue],
    dict[ResearchMetricId, MetricEvidenceLineage],
]:
    metrics: dict[ResearchMetricId, ResearchMetricValue] = {}
    lineage: dict[ResearchMetricId, MetricEvidenceLineage] = {}
    for metric_id, evidence in candidate.metrics.items():
        if evidence.status is EvidenceStatus.NOT_EVALUATED:
            continue
        value = evidence.metric_value
        if value is None or value.metric_id is not metric_id:
            _bridge_error("walk_forward_metric_identity_drift")
        metrics[metric_id] = value
        lineage[metric_id] = MetricEvidenceLineage(
            evidence.evidence_refs,
            evidence.evidence_hashes,
        )
    return metrics, lineage


def _return_series_hash(
    trial: LogicalTrialIdentity,
    evidence: StitchedReturnEvidence,
) -> ContentHash:
    payload = {
        "schema_id": "r3-walk-forward-return-sampling",
        "schema_version": 1,
        "trial": {
            "origin_experiment_id": str(trial.origin_experiment_id),
            "candidate_id": str(trial.candidate_id),
            "ordinal": trial.ordinal,
            "parameter_hash": str(trial.parameter_hash),
            "kind": trial.kind.value,
        },
        "return_unit": SamplingReturnUnit.PER_PERIOD_DECIMAL.value,
        "return_frequency": ReturnFrequency.DAILY.value,
        "periods_per_year": _TRADING_DAYS_PER_YEAR,
        "daily_returns": [
            {
                "fold_id": str(fold_id),
                "trade_date": trade_date,
                "value": value,
            }
            for fold_id, trade_date, value in evidence.daily_returns
        ],
        "evidence_refs": list(evidence.evidence_refs),
        "evidence_hashes": [str(item) for item in evidence.evidence_hashes],
    }
    return canonical_payload(payload, schema_version=1).content_hash


def _sharpe_sampling(
    trial: LogicalTrialIdentity,
    candidate: WalkForwardCandidate,
    metrics: Mapping[ResearchMetricId, ResearchMetricValue],
) -> SharpeSamplingEvidence | None:
    sharpe = metrics.get(ResearchMetricId.SHARPE_RATIO)
    if sharpe is None:
        return None
    evidence = candidate.stitched_returns
    if evidence is None:
        _bridge_error("walk_forward_sharpe_sampling_missing")
    returns = tuple(item[2] for item in evidence.daily_returns)
    if len(returns) < _MIN_SHARPE_OBSERVATIONS or any(
        not math.isfinite(value) or value <= -1.0 for value in returns
    ):
        _bridge_error("walk_forward_sharpe_sampling_invalid")
    mean_return = fmean(returns)
    centered = tuple(value - mean_return for value in returns)
    second_moment = fmean(value**2 for value in centered)
    if second_moment <= 0.0:
        _bridge_error("walk_forward_sharpe_sampling_invalid")
    skewness = fmean(value**3 for value in centered) / second_moment**1.5
    pearson_kurtosis = fmean(value**4 for value in centered) / second_moment**2
    return SharpeSamplingEvidence(
        sharpe_ratio=sharpe,
        scale=SharpeRatioScale.ANNUALIZED,
        return_unit=SamplingReturnUnit.PER_PERIOD_DECIMAL,
        return_frequency=ReturnFrequency.DAILY,
        periods_per_year=_TRADING_DAYS_PER_YEAR,
        observation_count=len(returns),
        return_skewness=skewness,
        pearson_kurtosis=max(1.0, pearson_kurtosis),
        return_series_hash=_return_series_hash(trial, evidence),
    )


def _failure_reason(candidate: WalkForwardCandidate) -> str:
    if candidate.status is CandidateWalkForwardStatus.NOT_EVALUATED:
        return "incomplete_walk_forward_folds"
    reasons = tuple(
        dict.fromkeys(
            fold.failure_reason
            for fold in candidate.folds
            if fold.failure_reason is not None
        )
    )
    return reasons[0] if len(reasons) == 1 else "candidate_failed"


def _current_outcome(
    trial: LogicalTrialIdentity,
    candidate: WalkForwardCandidate,
    pbo_partition_plan: PboPartitionPlan | None,
    source_projection_hash: ContentHash,
) -> TrialOutcome:
    if candidate.status is not CandidateWalkForwardStatus.COMPLETED:
        return TrialOutcome(
            trial=trial,
            status=TrialStatus.FAILED,
            metrics={},
            holdout_metrics={},
            source_projection_hash=source_projection_hash,
            failure_reason=_failure_reason(candidate),
        )
    metrics, lineage = _metric_projection(candidate)
    pbo_sampling = _derive_pbo_sampling(candidate, pbo_partition_plan)
    return TrialOutcome(
        trial=trial,
        status=TrialStatus.COMPLETED,
        metrics=metrics,
        holdout_metrics={},
        source_projection_hash=source_projection_hash,
        metric_evidence=lineage,
        sharpe_sampling=_sharpe_sampling(trial, candidate, metrics),
        pbo_sampling=pbo_sampling,
    )


def _derive_pbo_sampling(
    candidate: WalkForwardCandidate,
    plan: PboPartitionPlan | None,
) -> PboSamplingEvidence | None:
    if plan is None:
        return None
    stitched = candidate.stitched_returns
    if stitched is None:
        _bridge_error("pbo_stitched_return_evidence_missing")
    rows = stitched.daily_returns
    offset = 0
    partitions: list[PboPartitionReturns] = []
    for identity in plan.partitions:
        stop = offset + identity.observation_count
        segment = rows[offset:stop]
        observation_dates = tuple(date.fromisoformat(item[1]) for item in segment)
        if (
            len(segment) != identity.observation_count
            or len({item[0] for item in segment}) != 1
            or identity.window_start != date.fromisoformat(segment[0][1])
            or identity.window_end != date.fromisoformat(segment[-1][1])
            or identity.observation_date_grid_hash
            != partition_observation_date_grid_hash(observation_dates)
        ):
            _bridge_error("pbo_partition_plan_stitched_return_mismatch")
        returns = tuple(item[2] for item in segment)
        partitions.append(
            PboPartitionReturns(
                identity,
                returns,
                partition_returns_hash(identity, returns),
            )
        )
        offset = stop
    if offset != len(rows):
        _bridge_error("pbo_partition_plan_stitched_return_mismatch")
    return PboSamplingEvidence(
        plan.score_metric_id,
        plan.direction,
        plan.estimator,
        plan.return_unit,
        plan.return_frequency,
        plan.periods_per_year,
        tuple(partitions),
    )


def _prior_outcomes(
    objective: PromotionObjective,
    values: Iterable[TrialOutcome],
    source_projection_hash: ContentHash,
) -> dict[LogicalTrialIdentity, TrialOutcome]:
    raw = tuple(cast("Iterable[object]", values))
    if any(type(item) is not TrialOutcome for item in raw):
        _bridge_error("invalid_prior_trial_outcomes")
    outcomes = cast("tuple[TrialOutcome, ...]", raw)
    expected = objective.trial_family.prior_members
    by_trial = {item.trial: item for item in outcomes}
    if (
        len(by_trial) != len(outcomes)
        or any(trial not in expected for trial in by_trial)
        or any(item.trial.kind is not TrialKind.PRIOR for item in outcomes)
    ):
        _bridge_error("prior_trial_family_mismatch")
    declarations = {
        item.trial: item.outcome_content_hash for item in objective.prior_trial_evidence
    }
    if not declarations and outcomes:
        _bridge_error("prior_trial_evidence_not_preregistered")
    if any(
        trial_outcome_content_hash(outcome) != declarations[trial]
        for trial, outcome in by_trial.items()
    ):
        _bridge_error("prior_trial_outcome_content_hash_mismatch")
    return {
        trial: by_trial.get(trial)
        or TrialOutcome(
            trial=trial,
            status=TrialStatus.FAILED,
            metrics={},
            holdout_metrics={},
            source_projection_hash=source_projection_hash,
            failure_reason=(
                "prior_evidence_unavailable"
                if trial in declarations
                else "prior_evidence_not_preregistered"
            ),
        )
        for trial in expected
    }


def project_walk_forward_trial_outcomes(
    launch_spec: ExperimentLaunchSpec,
    aggregation: WalkForwardAggregation,
    *,
    prior_outcomes: Iterable[TrialOutcome] = (),
) -> tuple[TrialOutcome, ...]:
    """Project an exact walk-forward family without dropping failed trials."""
    if type(launch_spec) is not ExperimentLaunchSpec:
        _bridge_error("invalid_experiment_launch_spec")
    try:
        encoded_launch = encode_launch_spec(launch_spec)
        validated_launch = decode_launch_spec(
            encoded_launch.json_bytes,
            encoded_launch.content_hash,
        )
    except AnalysisError:
        _bridge_error("invalid_experiment_launch_spec")
    objective = validated_launch.promotion_objective
    if type(aggregation) is not WalkForwardAggregation:
        _bridge_error("invalid_walk_forward_aggregation")
    if aggregation.metric_schema is not R3_RESEARCH_METRIC_SCHEMA:
        _bridge_error("walk_forward_metric_schema_drift")
    experiment_id = aggregation.baseline.experiment_id
    if (
        type(experiment_id) is not ExperimentId
        or experiment_id != validated_launch.experiment_id
    ):
        _bridge_error("walk_forward_experiment_identity_drift")
    current = objective.trial_family.current_members
    if objective.baseline_candidate_id != aggregation.baseline.candidate_id or any(
        item.origin_experiment_id != experiment_id for item in current
    ):
        _bridge_error("walk_forward_trial_family_mismatch")
    candidates = tuple(aggregation.candidates)
    candidate_keys = tuple(
        (item.candidate_id, item.candidate_ordinal) for item in candidates
    )
    current_keys = tuple((item.candidate_id, item.ordinal) for item in current)
    launch_keys = tuple(
        (item.candidate_id, item.ordinal) for item in validated_launch.candidates
    )
    if (
        len(set(candidate_keys)) != len(candidate_keys)
        or set(candidate_keys) != set(current_keys)
        or candidate_keys != launch_keys
    ):
        _bridge_error("walk_forward_trial_family_mismatch")
    expected_folds = tuple(
        (fold.fold_id, fold.fold_ordinal) for fold in aggregation.baseline.oos_folds
    )
    by_key = {
        (candidate.candidate_id, candidate.candidate_ordinal): candidate
        for candidate in candidates
    }
    bindings_by_key = {
        (binding.candidate_id, binding.ordinal): binding
        for binding in validated_launch.execution_bindings
    }
    for candidate in candidates:
        _validate_candidate_lineage(
            candidate,
            experiment_id,
            expected_folds,
            bindings_by_key[(candidate.candidate_id, candidate.candidate_ordinal)],
        )
    prior_by_trial = _prior_outcomes(
        objective,
        prior_outcomes,
        aggregation.content_hash,
    )
    current_by_trial = {
        trial: _current_outcome(
            trial,
            by_key[(trial.candidate_id, trial.ordinal)],
            objective.pbo_partition_plan,
            aggregation.content_hash,
        )
        for trial in current
    }
    return tuple(
        prior_by_trial[trial]
        if trial.kind is TrialKind.PRIOR
        else current_by_trial[trial]
        for trial in objective.trial_family.members
    )
