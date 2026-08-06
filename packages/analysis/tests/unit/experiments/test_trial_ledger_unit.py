"""Unit tests for immutable, typed multiple-testing evidence."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from itertools import permutations
from math import sqrt
from statistics import fmean, stdev
from typing import cast

import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.metric_schema import (
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
)
from ditto_analysis.experiments.models import CandidateId, ContentHash, ExperimentId
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialFamilyDeclaration,
    TrialKind,
)
from ditto_analysis.experiments.trial_ledger import (
    ConstraintOperator,
    EvidenceStatus,
    MetricConstraint,
    MetricEvidenceLineage,
    ObjectiveMetric,
    PboEstimator,
    PboPartitionIdentity,
    PboPartitionPlan,
    PboPartitionReturns,
    PboSamplingEvidence,
    PriorTrialEvidenceDeclaration,
    PromotionObjective,
    ReturnFrequency,
    SamplingReturnUnit,
    SharpeRatioScale,
    SharpeSamplingEvidence,
    TrialLedger,
    TrialOutcome,
    TrialStatus,
    build_trial_ledger,
    partition_observation_date_grid_hash,
    partition_returns_hash,
    promotion_objective_content_hash,
    trial_family_content_hash,
    trial_ledger_content_hash,
    trial_outcome_content_hash,
)


def _identity(
    ordinal: int,
    *,
    origin: str = "experiment-current",
    candidate: str | None = None,
    kind: TrialKind = TrialKind.CURRENT,
    hash_character: str | None = None,
) -> LogicalTrialIdentity:
    return LogicalTrialIdentity(
        origin_experiment_id=ExperimentId(origin),
        candidate_id=CandidateId(candidate or f"candidate-{ordinal}"),
        ordinal=ordinal,
        parameter_hash=ContentHash((hash_character or f"{ordinal:x}") * 64),
        kind=kind,
    )


def _family(count: int, *, prior_count: int = 0) -> TrialFamilyDeclaration:
    prior = tuple(
        _identity(
            ordinal,
            origin="experiment-prior",
            candidate=f"prior-{ordinal}",
            kind=TrialKind.PRIOR,
            hash_character=chr(96 + ordinal),
        )
        for ordinal in range(1, prior_count + 1)
    )
    current = tuple(_identity(ordinal) for ordinal in range(1, count - prior_count + 1))
    return TrialFamilyDeclaration("stock-selection-r3-v1", (*current, *prior))


def _objective(
    family: TrialFamilyDeclaration,
    *,
    primary: ResearchMetricId = ResearchMetricId.NET_RETURN,
    hard_constraints: tuple[MetricConstraint, ...] = (),
    tie_break_order: tuple[ObjectiveMetric, ...] = (),
    pbo_partition_plan: PboPartitionPlan | None = None,
    prior_trial_evidence: tuple[PriorTrialEvidenceDeclaration, ...] = (),
) -> PromotionObjective:
    baseline = family.current_members[0]
    direction = cast(
        "ResearchMetricDirection",
        {
            ResearchMetricId.NET_RETURN: ResearchMetricDirection.MAXIMIZE,
            ResearchMetricId.SHARPE_RATIO: ResearchMetricDirection.MAXIMIZE,
        }[primary],
    )
    return PromotionObjective(
        primary=ObjectiveMetric(primary, direction),
        hard_constraints=hard_constraints,
        tie_break_order=tie_break_order,
        baseline_candidate_id=baseline.candidate_id,
        economic_rationale="Capture durable cross-sectional returns after costs.",
        trial_family=family,
        pbo_partition_plan=pbo_partition_plan,
        prior_trial_evidence=prior_trial_evidence,
    )


def _metrics(
    net_return: float,
    *,
    sharpe: float = 1.0,
    max_drawdown: float | None = None,
    turnover: float | None = None,
) -> dict[ResearchMetricId, ResearchMetricValue]:
    values = {
        ResearchMetricId.NET_RETURN: ResearchMetricValue(
            ResearchMetricId.NET_RETURN,
            net_return,
        ),
        ResearchMetricId.SHARPE_RATIO: ResearchMetricValue(
            ResearchMetricId.SHARPE_RATIO,
            sharpe,
        ),
    }
    if max_drawdown is not None:
        values[ResearchMetricId.MAX_DRAWDOWN] = ResearchMetricValue(
            ResearchMetricId.MAX_DRAWDOWN,
            max_drawdown,
        )
    if turnover is not None:
        values[ResearchMetricId.TURNOVER] = ResearchMetricValue(
            ResearchMetricId.TURNOVER,
            turnover,
        )
    return values


def _metric_evidence(
    metrics: dict[ResearchMetricId, ResearchMetricValue],
) -> dict[ResearchMetricId, MetricEvidenceLineage]:
    return {
        metric_id: MetricEvidenceLineage(
            (f"artifact://{metric_id.value}",),
            (ContentHash("d" * 64),),
        )
        for metric_id in metrics
    }


def _sharpe(
    value: float,
    *,
    scale: SharpeRatioScale = SharpeRatioScale.ANNUALIZED,
    frequency: ReturnFrequency = ReturnFrequency.DAILY,
    periods_per_year: int = 252,
) -> SharpeSamplingEvidence:
    return SharpeSamplingEvidence(
        sharpe_ratio=ResearchMetricValue(ResearchMetricId.SHARPE_RATIO, value),
        scale=scale,
        return_unit=SamplingReturnUnit.PER_PERIOD_DECIMAL,
        return_frequency=frequency,
        periods_per_year=periods_per_year,
        observation_count=252,
        return_skewness=0.0,
        pearson_kurtosis=3.0,
        return_series_hash=ContentHash("a" * 64),
    )


def _outcome(
    trial: LogicalTrialIdentity,
    *,
    net_return: float = 10.0,
    sharpe: float = 1.0,
    metrics: dict[ResearchMetricId, ResearchMetricValue] | None = None,
    sampling: SharpeSamplingEvidence | None = None,
    pbo_sampling: PboSamplingEvidence | None = None,
    holdout_metrics: dict[ResearchMetricId, ResearchMetricValue] | None = None,
) -> TrialOutcome:
    resolved_sharpe = sharpe if sampling is None else sampling.annualized_sharpe.value
    resolved_metrics = (
        _metrics(net_return, sharpe=resolved_sharpe) if metrics is None else metrics
    )
    if pbo_sampling is not None and metrics is None:
        aggregate = pbo_sampling.aggregate_metric_value
        resolved_metrics = {
            **resolved_metrics,
            aggregate.metric_id: aggregate,
        }
    return TrialOutcome(
        trial=trial,
        status=TrialStatus.COMPLETED,
        source_projection_hash=ContentHash("c" * 64),
        metrics=resolved_metrics,
        holdout_metrics=({} if holdout_metrics is None else holdout_metrics),
        metric_evidence=_metric_evidence(resolved_metrics),
        holdout_metric_evidence=_metric_evidence(
            {} if holdout_metrics is None else holdout_metrics
        ),
        sharpe_sampling=(
            _sharpe(sharpe) if sampling is None and metrics is None else sampling
        ),
        pbo_sampling=pbo_sampling,
    )


def _partition_identity(ordinal: int) -> PboPartitionIdentity:
    day = date(2026, 1, 1) + timedelta(days=ordinal - 1)
    return PboPartitionIdentity(
        partition_id=f"partition-{ordinal}",
        ordinal=ordinal,
        window_start=day,
        window_end=day,
        observation_count=1,
        observation_date_grid_hash=partition_observation_date_grid_hash((day,)),
    )


def _pbo_sampling(
    partition_returns: tuple[float, ...],
    *,
    identities: tuple[PboPartitionIdentity, ...] | None = None,
) -> PboSamplingEvidence:
    resolved = identities or tuple(
        _partition_identity(index) for index in range(1, len(partition_returns) + 1)
    )
    partitions = tuple(
        PboPartitionReturns(
            identity=identity,
            returns=(value,),
            return_hash=partition_returns_hash(identity, (value,)),
        )
        for identity, value in zip(resolved, partition_returns, strict=True)
    )
    return PboSamplingEvidence(
        score_metric_id=ResearchMetricId.NET_RETURN,
        direction=ResearchMetricDirection.MAXIMIZE,
        estimator=PboEstimator.COMPOUND_RETURN,
        return_unit=SamplingReturnUnit.PER_PERIOD_DECIMAL,
        return_frequency=ReturnFrequency.DAILY,
        periods_per_year=252,
        partitions=partitions,
    )


def _pbo_plan(
    identities: tuple[PboPartitionIdentity, ...] | None = None,
) -> PboPartitionPlan:
    return PboPartitionPlan(
        score_metric_id=ResearchMetricId.NET_RETURN,
        direction=ResearchMetricDirection.MAXIMIZE,
        estimator=PboEstimator.COMPOUND_RETURN,
        return_unit=SamplingReturnUnit.PER_PERIOD_DECIMAL,
        return_frequency=ReturnFrequency.DAILY,
        periods_per_year=252,
        partitions=(
            identities or tuple(_partition_identity(index) for index in range(1, 5))
        ),
    )


def test_objective_uses_typed_metric_values_and_schema_direction() -> None:
    family = _family(2)
    constraint = MetricConstraint(
        threshold=ResearchMetricValue(ResearchMetricId.MAX_DRAWDOWN, -20.0),
        operator=ConstraintOperator.GREATER_THAN_OR_EQUAL,
    )

    objective = _objective(family, hard_constraints=(constraint,))

    assert objective.primary.metric_id is ResearchMetricId.NET_RETURN
    assert objective.hard_constraints[0].threshold.unit.value == "percent"
    with pytest.raises(ExperimentSpecError) as exc_info:
        ObjectiveMetric(
            ResearchMetricId.NET_RETURN,
            ResearchMetricDirection.MINIMIZE,
        )
    assert exc_info.value.details["reason_code"] == "metric_direction_mismatch"


def test_trial_metrics_freeze_in_schema_order_and_reject_key_substitution() -> None:
    trial = _identity(1)
    outcome = _outcome(
        trial,
        metrics={
            ResearchMetricId.TURNOVER: ResearchMetricValue(
                ResearchMetricId.TURNOVER,
                0.2,
            ),
            ResearchMetricId.NET_RETURN: ResearchMetricValue(
                ResearchMetricId.NET_RETURN,
                10.0,
            ),
        },
    )

    assert tuple(outcome.metrics) == (
        ResearchMetricId.NET_RETURN,
        ResearchMetricId.TURNOVER,
    )
    with pytest.raises(TypeError):
        cast("dict[ResearchMetricId, ResearchMetricValue]", outcome.metrics)[
            ResearchMetricId.SHARPE_RATIO
        ] = ResearchMetricValue(ResearchMetricId.SHARPE_RATIO, 1.0)
    with pytest.raises(ExperimentSpecError) as exc_info:
        _outcome(
            trial,
            metrics={
                ResearchMetricId.NET_RETURN: ResearchMetricValue(
                    ResearchMetricId.SHARPE_RATIO,
                    1.0,
                )
            },
        )
    assert exc_info.value.details["reason_code"] == "metric_identity_mismatch"


def test_metric_evidence_lineage_requires_positional_ref_hash_pairs() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        MetricEvidenceLineage(
            ("artifact://first", "artifact://second"),
            (ContentHash("a" * 64),),
        )

    assert exc_info.value.details["reason_code"] == ("invalid_metric_evidence_lineage")


def test_failed_trial_cannot_carry_valid_metrics_or_sampling_evidence() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        TrialOutcome(
            trial=_identity(1),
            status=TrialStatus.FAILED,
            source_projection_hash=ContentHash("c" * 64),
            metrics=_metrics(999.0),
            holdout_metrics={},
            sharpe_sampling=_sharpe(99.0),
            failure_reason="candidate_failed",
        )

    assert exc_info.value.details["reason_code"] == "failed_trial_carries_evidence"


@pytest.mark.parametrize("include_metric", [True, False])
def test_sharpe_sampling_must_match_the_governance_metric(
    include_metric: bool,
) -> None:
    metrics = (
        {
            ResearchMetricId.SHARPE_RATIO: ResearchMetricValue(
                ResearchMetricId.SHARPE_RATIO,
                2.0,
            )
        }
        if include_metric
        else {}
    )

    with pytest.raises(ExperimentSpecError) as exc_info:
        _outcome(_identity(1), metrics=metrics, sampling=_sharpe(1.0))

    assert exc_info.value.details["reason_code"] == "sharpe_sampling_metric_mismatch"


@pytest.mark.parametrize(
    ("sampling", "expected"),
    [
        (_sharpe(1.25, scale=SharpeRatioScale.ANNUALIZED), 1.25),
        (_sharpe(0.1, scale=SharpeRatioScale.PER_PERIOD), 0.1 * sqrt(252)),
    ],
)
def test_sharpe_sampling_binds_both_scales_to_annualized_governance(
    sampling: SharpeSamplingEvidence,
    expected: float,
) -> None:
    outcome = _outcome(_identity(1), sampling=sampling)

    assert outcome.metrics[ResearchMetricId.SHARPE_RATIO].value == pytest.approx(
        expected
    )


def test_ledger_rejects_incomplete_or_substituted_logical_trial_family() -> None:
    family = _family(2)
    objective = _objective(family)
    first, second = family.current_members
    substituted = LogicalTrialIdentity(
        second.origin_experiment_id,
        second.candidate_id,
        second.ordinal,
        ContentHash("f" * 64),
        second.kind,
    )

    with pytest.raises(ExperimentSpecError) as incomplete:
        build_trial_ledger(objective, (_outcome(first),))
    with pytest.raises(ExperimentSpecError) as replacement:
        build_trial_ledger(
            objective,
            (_outcome(first), _outcome(substituted)),
        )

    assert incomplete.value.details["reason_code"] == "trial_family_mismatch"
    assert replacement.value.details["reason_code"] == "trial_family_mismatch"
    assert replacement.value.details["missing_trial_count"] == 1
    assert replacement.value.details["unexpected_trial_count"] == 1


def test_holdout_evidence_remains_on_the_same_logical_trial() -> None:
    family = _family(2, prior_count=1)
    objective = _objective(family)
    outcomes = tuple(
        _outcome(
            trial,
            holdout_metrics={
                ResearchMetricId.NET_RETURN: ResearchMetricValue(
                    ResearchMetricId.NET_RETURN,
                    5.0,
                )
            },
        )
        for trial in family.members
    )

    ledger = build_trial_ledger(objective, outcomes)

    assert ledger.declared_trial_count == 2
    assert ledger.observed_trial_count == 2
    assert all(outcome.holdout_metrics for outcome in ledger.trials)


def test_adjustments_do_not_consume_unregistered_prior_trial_evidence() -> None:
    family = _family(2, prior_count=1)
    objective = _objective(family)
    outcomes = tuple(
        _outcome(trial, net_return=float(trial.ordinal), sharpe=0.5 + trial.ordinal)
        for trial in family.members
    )

    ledger = build_trial_ledger(objective, outcomes)

    assert ledger.deflated_sharpe.status is EvidenceStatus.NOT_EVALUATED
    assert ledger.deflated_sharpe.reason == ("prior_trial_evidence_not_preregistered")
    assert ledger.pbo.status is EvidenceStatus.NOT_EVALUATED
    assert ledger.pbo.reason == "prior_trial_evidence_not_preregistered"


def test_ledger_rejects_prior_outcome_that_drifted_from_preregistered_hash() -> None:
    family = _family(2, prior_count=1)
    prior = family.prior_members[0]
    registered = _outcome(prior, net_return=3.0)
    objective = _objective(
        family,
        prior_trial_evidence=(
            PriorTrialEvidenceDeclaration(
                prior,
                trial_outcome_content_hash(registered),
            ),
        ),
    )

    with pytest.raises(ExperimentSpecError) as exc_info:
        build_trial_ledger(
            objective,
            (
                _outcome(family.current_members[0]),
                _outcome(prior, net_return=99.0),
            ),
        )

    assert exc_info.value.details["reason_code"] == (
        "prior_trial_outcome_content_hash_mismatch"
    )


def test_failed_trial_counts_but_is_never_ranked() -> None:
    family = _family(3)
    objective = _objective(family)
    first, second, third = family.current_members
    failed = TrialOutcome(
        trial=third,
        status=TrialStatus.FAILED,
        source_projection_hash=ContentHash("c" * 64),
        metrics={},
        holdout_metrics={},
        failure_reason="candidate_failed",
    )

    ledger = build_trial_ledger(
        objective,
        (_outcome(first, net_return=10.0), _outcome(second, net_return=20.0), failed),
    )

    assert ledger.failed_trial_count == 1
    assert ledger.ranked_trial_ids == (second, first)
    assert third not in ledger.ranked_trial_ids


def test_ledger_fail_closes_ranking_when_baseline_primary_evidence_is_missing() -> None:
    family = _family(2)
    objective = _objective(family)
    baseline, alpha = family.current_members
    baseline_metrics = {
        ResearchMetricId.SHARPE_RATIO: ResearchMetricValue(
            ResearchMetricId.SHARPE_RATIO,
            1.0,
        )
    }

    ledger = build_trial_ledger(
        objective,
        (
            _outcome(baseline, metrics=baseline_metrics),
            _outcome(alpha, net_return=20.0),
        ),
    )

    assert ledger.ranked_trial_ids == ()
    assert ledger.deflated_sharpe.status is EvidenceStatus.NOT_EVALUATED
    assert ledger.deflated_sharpe.reason == "no_eligible_current_trial"


def test_ledger_rejects_mixed_current_projection_artifacts() -> None:
    family = _family(2)
    objective = _objective(family)
    first, second = family.current_members

    with pytest.raises(ExperimentSpecError) as exc_info:
        build_trial_ledger(
            objective,
            (
                _outcome(first),
                replace(
                    _outcome(second),
                    source_projection_hash=ContentHash("f" * 64),
                ),
            ),
        )

    assert exc_info.value.details["reason_code"] == ("trial_projection_hash_mismatch")


def test_ledger_projection_is_deterministic_for_input_permutations() -> None:
    family = _family(3)
    objective = _objective(family)
    outcomes = tuple(
        _outcome(trial, net_return=float(trial.ordinal)) for trial in family.members
    )

    ledgers = tuple(
        build_trial_ledger(objective, permutation)
        for permutation in permutations(outcomes)
    )

    assert all(ledger == ledgers[0] for ledger in ledgers)


def test_trial_ledger_rejects_direct_or_forged_aggregate_construction() -> None:
    family = _family(2)
    objective = _objective(family)
    ledger = build_trial_ledger(
        objective,
        tuple(_outcome(trial) for trial in family.members),
    )

    with pytest.raises(ExperimentSpecError) as direct:
        TrialLedger(
            ledger.objective,
            ledger.trials,
            ledger.ranked_trial_ids,
            ledger.deflated_sharpe,
            ledger.pbo,
        )
    with pytest.raises(ExperimentSpecError) as forged:
        replace(
            ledger,
            pbo=replace(ledger.pbo, probability=0.999),
        )

    assert direct.value.details["reason_code"] == "trial_ledger_factory_required"
    assert forged.value.details["reason_code"] == "trial_ledger_factory_required"


def test_ledger_has_versioned_complete_canonical_payload_and_content_hash() -> None:
    family = _family(2)
    objective = _objective(family, pbo_partition_plan=_pbo_plan())
    first, second = family.current_members
    outcomes = (
        _outcome(
            first,
            pbo_sampling=_pbo_sampling((0.1, 0.1, -0.1, -0.1)),
            holdout_metrics={
                ResearchMetricId.NET_RETURN: ResearchMetricValue(
                    ResearchMetricId.NET_RETURN,
                    2.5,
                )
            },
        ),
        _outcome(
            second,
            pbo_sampling=_pbo_sampling((-0.1, -0.1, 0.1, 0.1)),
        ),
    )

    ledger = build_trial_ledger(objective, reversed(outcomes))
    payload = ledger.canonical_payload()

    assert payload["schema_id"] == "r3-trial-ledger"
    assert payload["schema_version"] == 1
    assert payload["trial_family_content_hash"] == str(
        trial_family_content_hash(family)
    )
    assert payload["promotion_objective_content_hash"] == str(
        promotion_objective_content_hash(objective)
    )
    trials = payload["trials"]
    assert isinstance(trials, list)
    first_payload = trials[0]
    assert isinstance(first_payload, dict)
    assert first_payload["holdout_metrics"] == [
        {
            "metric_id": "net_return",
            "unit": "percent",
            "value": 2.5,
            "evidence_refs": ["artifact://net_return"],
            "evidence_hashes": ["d" * 64],
        }
    ]
    assert first_payload["sharpe_sampling"] is not None
    pbo_sampling = first_payload["pbo_sampling"]
    assert isinstance(pbo_sampling, dict)
    partitions = pbo_sampling["partitions"]
    assert isinstance(partitions, list)
    assert partitions[0]["returns"] == [0.1]
    assert partitions[0]["return_hash"]
    assert payload["deflated_sharpe"] == {
        "status": ledger.deflated_sharpe.status.value,
        "method": ledger.deflated_sharpe.method,
        "method_prerequisites": list(ledger.deflated_sharpe.method_prerequisites),
        "reason": ledger.deflated_sharpe.reason,
        "candidate_id": str(ledger.deflated_sharpe.candidate_id),
        "probability": ledger.deflated_sharpe.probability,
        "observed_sharpe": ledger.deflated_sharpe.observed_sharpe,
        "expected_max_sharpe": ledger.deflated_sharpe.expected_max_sharpe,
        "declared_trial_count": 2,
        "observed_trial_count": 2,
        "completed_sharpe_trial_count": 2,
        "return_frequency": "daily",
        "periods_per_year": 252,
    }
    assert payload["pbo"] == {
        "status": "evaluated",
        "method": ledger.pbo.method,
        "method_prerequisites": list(ledger.pbo.method_prerequisites),
        "reason": ledger.pbo.reason,
        "probability": pytest.approx(1 / 3),
        "declared_trial_count": 2,
        "observed_trial_count": 2,
        "partition_count": 4,
        "combination_budget": 100_000,
        "combination_count": 6,
        "evaluated_combination_count": 6,
        "score_metric_id": "net_return",
        "direction": "maximize",
        "estimator": "compound_return",
        "tie_method": "midrank_average_in_sample_ties",
        "overfit_lambda_threshold": 0.0,
    }
    assert ledger.content_hash == trial_ledger_content_hash(ledger)
    assert (
        ledger.content_hash
        == build_trial_ledger(
            objective,
            outcomes,
        ).content_hash
    )


def test_ledger_content_hash_changes_with_raw_sampling_evidence() -> None:
    family = _family(2)
    objective = _objective(family, pbo_partition_plan=_pbo_plan())
    first, second = family.current_members
    original = build_trial_ledger(
        objective,
        (
            _outcome(first, pbo_sampling=_pbo_sampling((0.1, 0.1, -0.1, -0.1))),
            _outcome(second, pbo_sampling=_pbo_sampling((-0.1, -0.1, 0.1, 0.1))),
        ),
    )
    changed = build_trial_ledger(
        objective,
        (
            _outcome(first, pbo_sampling=_pbo_sampling((0.2, 0.0, -0.1, -0.1))),
            _outcome(second, pbo_sampling=_pbo_sampling((-0.1, -0.1, 0.1, 0.1))),
        ),
    )

    assert original.content_hash != changed.content_hash


def test_deflated_sharpe_converts_annualized_evidence_to_per_period_units() -> None:
    family = _family(3)
    objective = _objective(family)
    outcomes = tuple(
        _outcome(
            trial,
            net_return=float(4 - trial.ordinal),
            sharpe=value,
            sampling=_sharpe(value),
        )
        for trial, value in zip(family.members, (1.2, 0.8, 0.4), strict=True)
    )

    evidence = build_trial_ledger(objective, outcomes).deflated_sharpe

    assert evidence.status is EvidenceStatus.EVALUATED
    assert evidence.observed_sharpe == pytest.approx(1.2 / sqrt(252))
    assert evidence.return_frequency is ReturnFrequency.DAILY
    assert evidence.periods_per_year == 252
    assert evidence.completed_sharpe_trial_count == 3
    assert evidence.probability is not None


def test_deflated_sharpe_never_uses_a_completed_survivor_subset() -> None:
    family = _family(3)
    objective = _objective(family)
    first, second, third = family.current_members
    failed = TrialOutcome(
        trial=third,
        status=TrialStatus.FAILED,
        source_projection_hash=ContentHash("c" * 64),
        metrics={},
        holdout_metrics={},
        failure_reason="candidate_failed",
    )

    failed_evidence = build_trial_ledger(
        objective,
        (_outcome(first, sampling=_sharpe(1.2)), _outcome(second), failed),
    ).deflated_sharpe
    missing_evidence = build_trial_ledger(
        objective,
        (
            _outcome(first, sampling=_sharpe(1.2)),
            TrialOutcome(
                trial=second,
                status=TrialStatus.COMPLETED,
                source_projection_hash=ContentHash("c" * 64),
                metrics=_metrics(10.0),
                holdout_metrics={},
                metric_evidence=_metric_evidence(_metrics(10.0)),
                sharpe_sampling=None,
            ),
            _outcome(third, sampling=_sharpe(0.4)),
        ),
    ).deflated_sharpe

    assert failed_evidence.status is EvidenceStatus.NOT_EVALUATED
    assert failed_evidence.reason == "failed_trial_in_family"
    assert missing_evidence.status is EvidenceStatus.NOT_EVALUATED
    assert missing_evidence.reason == "incomplete_sharpe_sampling_family"


def test_sharpe_sampling_frequency_and_periods_per_year_are_consistent() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _sharpe(
            1.0,
            frequency=ReturnFrequency.MONTHLY,
            periods_per_year=252,
        )

    assert exc_info.value.details["reason_code"] == "invalid_periods_per_year"


def test_sampling_evidence_rejects_percent_metric_units_as_raw_returns() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        SharpeSamplingEvidence(
            sharpe_ratio=ResearchMetricValue(ResearchMetricId.SHARPE_RATIO, 1.0),
            scale=SharpeRatioScale.ANNUALIZED,
            return_unit=cast("SamplingReturnUnit", "percent"),
            return_frequency=ReturnFrequency.DAILY,
            periods_per_year=252,
            observation_count=252,
            return_skewness=0.0,
            pearson_kurtosis=3.0,
            return_series_hash=ContentHash("a" * 64),
        )

    assert exc_info.value.details["reason_code"] == "invalid_sampling_return_unit"


def test_pbo_recomputes_combined_returns_with_a_known_answer() -> None:
    family = _family(2)
    objective = _objective(family, pbo_partition_plan=_pbo_plan())
    first, second = family.current_members
    outcomes = (
        _outcome(first, pbo_sampling=_pbo_sampling((0.1, 0.1, -0.1, -0.1))),
        _outcome(second, pbo_sampling=_pbo_sampling((-0.1, -0.1, 0.1, 0.1))),
    )

    evidence = build_trial_ledger(objective, outcomes).pbo

    assert evidence.status is EvidenceStatus.EVALUATED
    assert evidence.probability == pytest.approx(1 / 3)
    assert evidence.partition_count == 4
    assert evidence.combination_count == 6
    assert evidence.tie_method == "midrank_average_in_sample_ties"


def test_pbo_midrank_ties_have_zero_lambda_and_are_not_overfit() -> None:
    family = _family(2)
    objective = _objective(family, pbo_partition_plan=_pbo_plan())
    identical = _pbo_sampling((0.01, 0.01, 0.01, 0.01))
    outcomes = tuple(
        _outcome(trial, pbo_sampling=identical) for trial in family.current_members
    )

    evidence = build_trial_ledger(objective, outcomes).pbo

    assert evidence.status is EvidenceStatus.EVALUATED
    assert evidence.probability == 0.0
    assert evidence.overfit_lambda_threshold == 0.0


def test_pbo_refuses_unaligned_partition_identity() -> None:
    family = _family(2)
    first, second = family.current_members
    aligned = tuple(_partition_identity(index) for index in range(1, 5))
    objective = _objective(family, pbo_partition_plan=_pbo_plan(aligned))
    shifted = (
        *aligned[:3],
        PboPartitionIdentity(
            "partition-4",
            4,
            date(2026, 1, 8),
            date(2026, 1, 8),
            1,
            partition_observation_date_grid_hash((date(2026, 1, 8),)),
        ),
    )

    evidence = build_trial_ledger(
        objective,
        (
            _outcome(first, pbo_sampling=_pbo_sampling((0.1,) * 4, identities=aligned)),
            _outcome(
                second,
                pbo_sampling=_pbo_sampling((0.2,) * 4, identities=shifted),
            ),
        ),
    ).pbo

    assert evidence.status is EvidenceStatus.NOT_EVALUATED
    assert evidence.reason == "pbo_partition_plan_mismatch"


def test_pbo_is_not_evaluated_without_a_preregistered_partition_plan() -> None:
    family = _family(2)
    objective = _objective(family)
    outcomes = tuple(
        _outcome(
            trial,
            pbo_sampling=_pbo_sampling((0.1, 0.1, -0.1, -0.1)),
        )
        for trial in family.current_members
    )

    evidence = build_trial_ledger(objective, outcomes).pbo

    assert evidence.status is EvidenceStatus.NOT_EVALUATED
    assert evidence.reason == "pbo_partition_plan_not_preregistered"


def test_pbo_partition_returns_require_the_exact_canonical_hash() -> None:
    identity = _partition_identity(1)

    with pytest.raises(ExperimentSpecError) as exc_info:
        PboPartitionReturns(identity, (0.1,), ContentHash("f" * 64))

    assert exc_info.value.details["reason_code"] == "partition_return_hash_mismatch"


def test_pbo_observation_date_grid_hash_binds_interior_trading_dates() -> None:
    first_grid = (
        date(2026, 1, 1),
        date(2026, 1, 2),
        date(2026, 1, 4),
    )
    substituted_grid = (
        date(2026, 1, 1),
        date(2026, 1, 3),
        date(2026, 1, 4),
    )

    assert partition_observation_date_grid_hash(
        first_grid
    ) != partition_observation_date_grid_hash(substituted_grid)


def test_pbo_partitions_require_equal_observation_counts() -> None:
    first = _partition_identity(1)
    second = PboPartitionIdentity(
        "partition-2",
        2,
        date(2026, 1, 2),
        date(2026, 1, 3),
        2,
        partition_observation_date_grid_hash((date(2026, 1, 2), date(2026, 1, 3))),
    )
    partitions = (
        PboPartitionReturns(first, (0.1,), partition_returns_hash(first, (0.1,))),
        PboPartitionReturns(
            second,
            (0.1, 0.2),
            partition_returns_hash(second, (0.1, 0.2)),
        ),
    )

    with pytest.raises(ExperimentSpecError) as exc_info:
        PboSamplingEvidence(
            ResearchMetricId.NET_RETURN,
            ResearchMetricDirection.MAXIMIZE,
            PboEstimator.COMPOUND_RETURN,
            SamplingReturnUnit.PER_PERIOD_DECIMAL,
            ReturnFrequency.DAILY,
            252,
            partitions,
        )

    assert (
        exc_info.value.details["reason_code"]
        == "unequal_pbo_partition_observation_count"
    )


def test_pbo_aggregate_metric_must_match_recomputed_raw_returns() -> None:
    sampling = _pbo_sampling((0.01, 0.01, 0.01, 0.01))

    with pytest.raises(ExperimentSpecError) as exc_info:
        _outcome(
            _identity(1),
            metrics=_metrics(99.0),
            pbo_sampling=sampling,
        )

    assert exc_info.value.details["reason_code"] == "pbo_sampling_metric_mismatch"


def test_pbo_sharpe_aggregate_uses_the_annualized_governance_scale() -> None:
    returns = (0.01, 0.02, 0.0, 0.01)
    partitions = tuple(
        PboPartitionReturns(
            identity,
            (value,),
            partition_returns_hash(identity, (value,)),
        )
        for identity, value in zip(
            tuple(_partition_identity(index) for index in range(1, 5)),
            returns,
            strict=True,
        )
    )
    sampling = PboSamplingEvidence(
        ResearchMetricId.SHARPE_RATIO,
        ResearchMetricDirection.MAXIMIZE,
        PboEstimator.SHARPE_RATIO,
        SamplingReturnUnit.PER_PERIOD_DECIMAL,
        ReturnFrequency.DAILY,
        252,
        partitions,
    )

    aggregate = sampling.aggregate_metric_value

    assert aggregate.value == pytest.approx(fmean(returns) / stdev(returns) * sqrt(252))
    TrialOutcome(
        trial=_identity(1),
        status=TrialStatus.COMPLETED,
        source_projection_hash=ContentHash("c" * 64),
        metrics={ResearchMetricId.SHARPE_RATIO: aggregate},
        holdout_metrics={},
        metric_evidence=_metric_evidence({ResearchMetricId.SHARPE_RATIO: aggregate}),
        pbo_sampling=sampling,
    )


def test_pbo_combination_budget_is_checked_without_materializing_splits() -> None:
    family = _family(2)
    returns = tuple(0.001 if index % 2 else -0.001 for index in range(20))
    identities = tuple(_partition_identity(index) for index in range(1, 21))
    objective = _objective(family, pbo_partition_plan=_pbo_plan(identities))
    outcomes = tuple(
        _outcome(trial, pbo_sampling=_pbo_sampling(returns))
        for trial in family.current_members
    )

    evidence = build_trial_ledger(objective, outcomes).pbo

    assert evidence.status is EvidenceStatus.NOT_EVALUATED
    assert evidence.reason == "pbo_combination_budget_exceeded"
    assert evidence.combination_count == 184_756
    assert evidence.evaluated_combination_count == 0
