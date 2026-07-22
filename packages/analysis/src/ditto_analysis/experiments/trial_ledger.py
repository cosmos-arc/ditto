"""Immutable logical trial ledger and multiple-testing evidence projection."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import InitVar, dataclass
from typing import cast

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.metric_schema import (
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
)
from ditto_analysis.experiments.models import CandidateId, ContentHash
from ditto_analysis.experiments.persistence import (
    canonical_payload as _canonical_payload,
)
from ditto_analysis.experiments.promotion_models import (
    ConstraintOperator,
    MetricConstraint,
    ObjectiveMetric,
    PriorTrialEvidenceDeclaration,
    PromotionObjective,
)
from ditto_analysis.experiments.promotion_objective import (
    promotion_objective_payload,
    trial_family_payload,
    validate_promotion_objective_graph,
)
from ditto_analysis.experiments.trial_adjustments import (
    deflated_sharpe_evidence,
    pbo_evidence,
)
from ditto_analysis.experiments.trial_family import LogicalTrialIdentity, TrialKind
from ditto_analysis.experiments.trial_outcomes import (
    MetricEvidenceLineage,
    TrialOutcome,
    TrialStatus,
)
from ditto_analysis.experiments.trial_statistics import (
    MAX_PBO_COMBINATIONS,
    DeflatedSharpeEvidence,
    EvidenceStatus,
    PboEstimator,
    PboEvidence,
    PboPartitionIdentity,
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

MetricDirection = ResearchMetricDirection

__all__ = [
    "MAX_PBO_COMBINATIONS",
    "ConstraintOperator",
    "DeflatedSharpeEvidence",
    "EvidenceStatus",
    "MetricConstraint",
    "MetricDirection",
    "MetricEvidenceLineage",
    "ObjectiveMetric",
    "PboEstimator",
    "PboEvidence",
    "PboPartitionIdentity",
    "PboPartitionPlan",
    "PboPartitionReturns",
    "PboSamplingEvidence",
    "PriorTrialEvidenceDeclaration",
    "PromotionObjective",
    "ReturnFrequency",
    "SamplingReturnUnit",
    "SharpeRatioScale",
    "SharpeSamplingEvidence",
    "TrialLedger",
    "TrialOutcome",
    "TrialStatus",
    "build_trial_ledger",
    "partition_observation_date_grid_hash",
    "partition_returns_hash",
    "promotion_objective_content_hash",
    "trial_family_content_hash",
    "trial_ledger_content_hash",
    "trial_outcome_content_hash",
    "trial_outcome_payload",
]

_TRIAL_LEDGER_SCHEMA_ID = "r3-trial-ledger"
_TRIAL_LEDGER_SCHEMA_VERSION = 1
_TRIAL_LEDGER_FACTORY_TOKEN = object()


def _ledger_error(
    message: str,
    reason_code: str,
    **details: object,
) -> ExperimentSpecError:
    return ExperimentSpecError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _freeze_trials(
    objective: PromotionObjective,
    trials: Iterable[TrialOutcome],
) -> tuple[TrialOutcome, ...]:
    raw_trials = tuple(cast("Iterable[object]", trials))
    if any(type(trial) is not TrialOutcome for trial in raw_trials):
        raise _ledger_error(
            "trials must contain exact TrialOutcome values",
            "invalid_trial_sequence",
        )
    typed = cast("tuple[TrialOutcome, ...]", raw_trials)
    identities = tuple(trial.trial for trial in typed)
    if len(set(identities)) != len(identities):
        raise _ledger_error(
            "one logical trial cannot have multiple ledger outcomes",
            "duplicate_logical_trial_outcome",
        )
    declared = objective.trial_family.members
    missing = frozenset(declared).difference(identities)
    unexpected = frozenset(identities).difference(declared)
    if missing or unexpected:
        raise _ledger_error(
            "observed outcomes must equal the exact declared logical trial family",
            "trial_family_mismatch",
            missing_trial_count=len(missing),
            unexpected_trial_count=len(unexpected),
        )
    by_identity = {trial.trial: trial for trial in typed}
    ordered = tuple(by_identity[identity] for identity in declared)
    prior_hashes = {
        item.trial: item.outcome_content_hash for item in objective.prior_trial_evidence
    }
    for trial in ordered:
        expected_hash = prior_hashes.get(trial.trial)
        if (
            expected_hash is not None
            and trial_outcome_content_hash(trial) != expected_hash
            and not (
                trial.status is TrialStatus.FAILED
                and trial.failure_reason == "prior_evidence_unavailable"
            )
        ):
            raise _ledger_error(
                "prior outcome does not match its pre-registered artifact hash",
                "prior_trial_outcome_content_hash_mismatch",
            )
    current_projection_hashes = {
        trial.source_projection_hash
        for trial in ordered
        if trial.trial.kind is TrialKind.CURRENT
    }
    if len(current_projection_hashes) != 1:
        raise _ledger_error(
            "current trial outcomes must come from one comparison projection",
            "trial_projection_hash_mismatch",
        )
    return ordered


def _passes_constraints(
    trial: TrialOutcome,
    constraints: Sequence[MetricConstraint],
) -> bool:
    for constraint in constraints:
        observed = trial.metrics.get(constraint.metric_id)
        if observed is None:
            return False
        threshold = constraint.threshold.value
        if (
            constraint.operator is ConstraintOperator.GREATER_THAN_OR_EQUAL
            and observed.value < threshold
        ):
            return False
        if (
            constraint.operator is ConstraintOperator.LESS_THAN_OR_EQUAL
            and observed.value > threshold
        ):
            return False
    return True


def _metric_rank_key(
    trial: TrialOutcome,
    metric: ObjectiveMetric,
) -> tuple[int, float]:
    observed: ResearchMetricValue | None = trial.metrics.get(metric.metric_id)
    if observed is None:
        return (1, 0.0)
    directed = (
        -observed.value
        if metric.direction is ResearchMetricDirection.MAXIMIZE
        else observed.value
    )
    return (0, directed)


def _rank_trials(
    objective: PromotionObjective,
    trials: tuple[TrialOutcome, ...],
) -> tuple[TrialOutcome, ...]:
    baseline = next(
        (
            trial
            for trial in trials
            if trial.trial.kind is TrialKind.CURRENT
            and trial.candidate_id == objective.baseline_candidate_id
        ),
        None,
    )
    required_metric_ids = {
        objective.primary.metric_id,
        *(item.metric_id for item in objective.hard_constraints),
        *(item.metric_id for item in objective.tie_break_order),
    }
    if (
        baseline is None
        or baseline.status is not TrialStatus.COMPLETED
        or not required_metric_ids.issubset(baseline.metrics)
    ):
        return ()
    eligible = tuple(
        trial
        for trial in trials
        if trial.trial.kind is TrialKind.CURRENT
        and trial.status is TrialStatus.COMPLETED
        and objective.primary.metric_id in trial.metrics
        and _passes_constraints(trial, objective.hard_constraints)
    )
    family_order = {
        member: index for index, member in enumerate(objective.trial_family.members)
    }

    def rank_key(trial: TrialOutcome) -> tuple[object, ...]:
        metrics = (objective.primary, *objective.tie_break_order)
        return (
            *(_metric_rank_key(trial, metric) for metric in metrics),
            family_order[trial.trial],
        )

    return tuple(sorted(eligible, key=rank_key))


@dataclass(frozen=True, slots=True)
class TrialLedger:
    """Deterministic projection of the complete declared logical trial family."""

    objective: PromotionObjective
    trials: tuple[TrialOutcome, ...]
    ranked_trial_ids: tuple[LogicalTrialIdentity, ...]
    deflated_sharpe: DeflatedSharpeEvidence
    pbo: PboEvidence
    _factory_token: InitVar[object | None] = None

    def __post_init__(self, _factory_token: object | None) -> None:
        """Allow construction only through the validating ledger factory."""
        if _factory_token is not _TRIAL_LEDGER_FACTORY_TOKEN:
            raise _ledger_error(
                "trial ledger must be produced by build_trial_ledger",
                "trial_ledger_factory_required",
            )

    @property
    def declared_trial_count(self) -> int:
        """Return prior plus current pre-registered multiplicity."""
        return self.objective.declared_trial_count

    @property
    def observed_trial_count(self) -> int:
        """Count every supplied logical trial, including failures."""
        return len(self.trials)

    @property
    def failed_trial_count(self) -> int:
        """Count failed trials without turning them into valid observations."""
        return sum(trial.status is TrialStatus.FAILED for trial in self.trials)

    @property
    def ranked_candidate_ids(self) -> tuple[CandidateId, ...]:
        """Project ranked current logical trials to candidate identities."""
        return tuple(trial.candidate_id for trial in self.ranked_trial_ids)

    def canonical_payload(self) -> dict[str, object]:
        """Return complete versioned evidence without repr-based projections."""
        return _trial_ledger_payload(self)

    @property
    def content_hash(self) -> ContentHash:
        """Hash the complete ledger with the shared canonical JSON primitive."""
        return trial_ledger_content_hash(self)


def _identity_payload(value: LogicalTrialIdentity) -> dict[str, object]:
    return {
        "origin_experiment_id": str(value.origin_experiment_id),
        "candidate_id": str(value.candidate_id),
        "ordinal": value.ordinal,
        "parameter_hash": str(value.parameter_hash),
        "kind": value.kind.value,
    }


def _metric_payloads(
    values: Mapping[ResearchMetricId, ResearchMetricValue],
    evidence: Mapping[ResearchMetricId, MetricEvidenceLineage],
) -> list[dict[str, object]]:
    return [
        {
            **value.canonical_payload(),
            "evidence_refs": list(evidence[metric_id].evidence_refs),
            "evidence_hashes": [
                str(item) for item in evidence[metric_id].evidence_hashes
            ],
        }
        for metric_id, value in values.items()
    ]


def _sharpe_sampling_payload(
    value: SharpeSamplingEvidence | None,
) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "schema_id": "r3-sharpe-sampling-evidence",
        "schema_version": 1,
        "sharpe_ratio": value.sharpe_ratio.canonical_payload(),
        "scale": value.scale.value,
        "return_unit": value.return_unit.value,
        "return_frequency": value.return_frequency.value,
        "periods_per_year": value.periods_per_year,
        "observation_count": value.observation_count,
        "return_skewness": value.return_skewness,
        "pearson_kurtosis": value.pearson_kurtosis,
        "return_series_hash": str(value.return_series_hash),
    }


def _pbo_sampling_payload(
    value: PboSamplingEvidence | None,
) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "schema_id": "r3-pbo-sampling-evidence",
        "schema_version": 1,
        "score_metric_id": value.score_metric_id.value,
        "direction": value.direction.value,
        "estimator": value.estimator.value,
        "return_unit": value.return_unit.value,
        "return_frequency": value.return_frequency.value,
        "periods_per_year": value.periods_per_year,
        "partitions": [
            {
                "identity": partition.identity.canonical_payload(),
                "returns": list(partition.returns),
                "return_hash": str(partition.return_hash),
            }
            for partition in value.partitions
        ],
    }


def trial_outcome_payload(value: object) -> dict[str, object]:
    """Return the complete versioned payload for one exact trial outcome."""
    if type(value) is not TrialOutcome:
        raise _ledger_error(
            "outcome must be TrialOutcome",
            "invalid_trial_outcome",
        )
    outcome = value
    return {
        "schema_id": "r3-trial-outcome",
        "schema_version": 1,
        "trial": _identity_payload(outcome.trial),
        "status": outcome.status.value,
        "source_projection_hash": str(outcome.source_projection_hash),
        "metrics": _metric_payloads(outcome.metrics, outcome.metric_evidence),
        "holdout_metrics": _metric_payloads(
            outcome.holdout_metrics,
            outcome.holdout_metric_evidence,
        ),
        "sharpe_sampling": _sharpe_sampling_payload(outcome.sharpe_sampling),
        "pbo_sampling": _pbo_sampling_payload(outcome.pbo_sampling),
        "failure_reason": outcome.failure_reason,
    }


def trial_outcome_content_hash(value: object) -> ContentHash:
    """Hash one canonical prior/current outcome artifact."""
    return _canonical_payload(
        trial_outcome_payload(value),
        schema_version=1,
    ).content_hash


def _deflated_sharpe_payload(value: DeflatedSharpeEvidence) -> dict[str, object]:
    return {
        "status": value.status.value,
        "method": value.method,
        "method_prerequisites": list(value.method_prerequisites),
        "reason": value.reason,
        "candidate_id": (
            None if value.candidate_id is None else str(value.candidate_id)
        ),
        "probability": value.probability,
        "observed_sharpe": value.observed_sharpe,
        "expected_max_sharpe": value.expected_max_sharpe,
        "declared_trial_count": value.declared_trial_count,
        "observed_trial_count": value.observed_trial_count,
        "completed_sharpe_trial_count": value.completed_sharpe_trial_count,
        "return_frequency": (
            None if value.return_frequency is None else value.return_frequency.value
        ),
        "periods_per_year": value.periods_per_year,
    }


def _pbo_payload(value: PboEvidence) -> dict[str, object]:
    return {
        "status": value.status.value,
        "method": value.method,
        "method_prerequisites": list(value.method_prerequisites),
        "reason": value.reason,
        "probability": value.probability,
        "declared_trial_count": value.declared_trial_count,
        "observed_trial_count": value.observed_trial_count,
        "partition_count": value.partition_count,
        "combination_budget": value.combination_budget,
        "combination_count": value.combination_count,
        "evaluated_combination_count": value.evaluated_combination_count,
        "score_metric_id": (
            None if value.score_metric_id is None else value.score_metric_id.value
        ),
        "direction": None if value.direction is None else value.direction.value,
        "estimator": None if value.estimator is None else value.estimator.value,
        "tie_method": value.tie_method,
        "overfit_lambda_threshold": value.overfit_lambda_threshold,
    }


def trial_family_content_hash(value: object) -> ContentHash:
    """Hash the complete versioned family declaration canonically."""
    return _canonical_payload(
        trial_family_payload(value),
        schema_version=1,
    ).content_hash


def promotion_objective_content_hash(value: object) -> ContentHash:
    """Hash the complete objective, metric schema, and family declaration."""
    return _canonical_payload(
        promotion_objective_payload(value),
        schema_version=1,
    ).content_hash


def _trial_ledger_payload(value: TrialLedger) -> dict[str, object]:
    return {
        "schema_id": _TRIAL_LEDGER_SCHEMA_ID,
        "schema_version": _TRIAL_LEDGER_SCHEMA_VERSION,
        "trial_family_content_hash": str(
            trial_family_content_hash(value.objective.trial_family)
        ),
        "promotion_objective_content_hash": str(
            promotion_objective_content_hash(value.objective)
        ),
        "objective": promotion_objective_payload(value.objective),
        "trials": [trial_outcome_payload(trial) for trial in value.trials],
        "ranked_trial_ids": [
            _identity_payload(trial) for trial in value.ranked_trial_ids
        ],
        "declared_trial_count": value.declared_trial_count,
        "observed_trial_count": value.observed_trial_count,
        "failed_trial_count": value.failed_trial_count,
        "deflated_sharpe": _deflated_sharpe_payload(value.deflated_sharpe),
        "pbo": _pbo_payload(value.pbo),
    }


def trial_ledger_content_hash(value: object) -> ContentHash:
    """Hash one exact immutable ledger using its embedded artifact version."""
    if type(value) is not TrialLedger:
        raise _ledger_error(
            "ledger must be TrialLedger",
            "invalid_trial_ledger",
        )
    return _canonical_payload(
        _trial_ledger_payload(value),
        schema_version=_TRIAL_LEDGER_SCHEMA_VERSION,
    ).content_hash


def build_trial_ledger(
    objective: PromotionObjective,
    trials: Iterable[TrialOutcome],
    *,
    pbo_combination_budget: int = MAX_PBO_COMBINATIONS,
) -> TrialLedger:
    """Build evidence only for one exact, complete, pre-registered family."""
    if type(objective) is not PromotionObjective:
        raise _ledger_error(
            "objective must be PromotionObjective",
            "invalid_promotion_objective",
        )
    if type(pbo_combination_budget) is not int or pbo_combination_budget <= 0:
        raise _ledger_error(
            "PBO combination budget must be a positive integer",
            "invalid_pbo_combination_budget",
        )
    validated_objective = validate_promotion_objective_graph(objective)
    frozen_trials = _freeze_trials(validated_objective, trials)
    ranked_trials = _rank_trials(validated_objective, frozen_trials)
    return TrialLedger(
        objective=validated_objective,
        trials=frozen_trials,
        ranked_trial_ids=tuple(trial.trial for trial in ranked_trials),
        deflated_sharpe=deflated_sharpe_evidence(
            validated_objective,
            frozen_trials,
            ranked_trials,
        ),
        pbo=pbo_evidence(
            validated_objective,
            frozen_trials,
            combination_budget=pbo_combination_budget,
        ),
        _factory_token=_TRIAL_LEDGER_FACTORY_TOKEN,
    )
