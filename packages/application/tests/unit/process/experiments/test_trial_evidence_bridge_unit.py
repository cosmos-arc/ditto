"""Unit tests for the walk-forward to logical-trial evidence boundary."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import cast

import pytest
from ditto_analysis.experiments import (
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    BacktestRunId,
    CandidateExecutionBinding,
    CandidateId,
    CandidateSpec,
    ContentHash,
    DateWindow,
    ExperimentBudget,
    ExperimentDesiredState,
    ExperimentFailurePolicy,
    ExperimentId,
    ExperimentLaunchSpec,
    ExperimentReaderProtocol,
    ExperimentStatus,
    FoldId,
    FoldKey,
    FoldPersistenceSpec,
    FoldProjection,
    FoldProtocolSpec,
    FoldRole,
    FoldView,
    ResearchMetricDirection,
    ResearchMetricId,
    SnapshotId,
    StrategyVersion,
)
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialFamilyDeclaration,
    TrialKind,
)
from ditto_analysis.experiments.trial_ledger import (
    ObjectiveMetric,
    PboEstimator,
    PboPartitionIdentity,
    PboPartitionPlan,
    PriorTrialEvidenceDeclaration,
    PromotionObjective,
    ReturnFrequency,
    SamplingReturnUnit,
    TrialOutcome,
    TrialStatus,
    build_trial_ledger,
    partition_observation_date_grid_hash,
    trial_outcome_content_hash,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.baseline_registry import (
    BaselinePlanRequest,
    BaselineRef,
    default_baseline_registry,
)
from ditto_application.processes.experiments.comparison import (
    BaselineComparisonIdentity,
    CandidateFoldEvidence,
    OOSFoldRegistration,
    backtest_report_content_hash,
    build_candidate_comparison,
    load_persisted_fold_execution,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
    ExactUniverseIdentity,
)
from ditto_application.processes.experiments.trial_evidence_bridge import (
    project_walk_forward_trial_outcomes,
    verify_pre_holdout_selection_evidence,
)
from ditto_application.processes.experiments.walk_forward import (
    WalkForwardAggregation,
    aggregate_walk_forward,
)
from ditto_backtest.statistics import (
    AggregatedTradeStatistics,
    AlphaStatistics,
    BacktestReport,
)

EXPERIMENT_ID = ExperimentId("experiment-r3")
SNAPSHOT_ID = SnapshotId("snapshot-r3")
FOLDS = (
    OOSFoldRegistration(
        FoldId("wf-1"),
        1,
        DateWindow(date(2024, 1, 1), date(2024, 1, 2)),
    ),
    OOSFoldRegistration(
        FoldId("wf-2"),
        2,
        DateWindow(date(2025, 1, 1), date(2025, 1, 2)),
    ),
)


def _baseline_identity() -> BaselineComparisonIdentity:
    plan = default_baseline_registry().plan(
        BaselinePlanRequest(
            BaselineRef("stock_universe_equal_weight", 1),
            ExactResearchSnapshot(str(SNAPSHOT_ID), "a" * 64),
            ExactUniverseIdentity("a-share-r3", "b" * 64),
        )
    )
    return BaselineComparisonIdentity(
        EXPERIMENT_ID,
        CandidateId("candidate-baseline"),
        plan,
        FOLDS,
    )


def _empty_trades() -> AggregatedTradeStatistics:
    return AggregatedTradeStatistics(
        0,
        0,
        0,
        0,
        0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0,
        0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
    )


def _alpha() -> AlphaStatistics:
    return AlphaStatistics(
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0,
        0.0,
        None,
        None,
        None,
        None,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
    )


def _report(
    candidate_id: CandidateId,
    fold: OOSFoldRegistration,
    navs: tuple[float, float],
) -> BacktestReport:
    return BacktestReport(
        run_id=f"run:{candidate_id}:{fold.fold_id}",
        period=(fold.test_window.start.isoformat(), fold.test_window.end.isoformat()),
        initial_cash=100.0,
        final_nav=navs[-1],
        trade_stats=(),
        portfolio_stats=(),
        aggregated_trade_stats=_empty_trades(),
        alpha_stats=_alpha(),
        nav_series=(
            (fold.test_window.start.isoformat(), navs[0]),
            (fold.test_window.end.isoformat(), navs[1]),
        ),
        trade_log=(),
        fill_log=(),
    )


def _execution_binding(
    candidate_id: CandidateId,
    fold: OOSFoldRegistration,
):
    occurred_at = datetime(2024, 1, 1, tzinfo=UTC)
    key = FoldKey(EXPERIMENT_ID, candidate_id, fold.fold_id)
    fold_view = FoldView(
        FoldPersistenceSpec.create(
            key,
            fold.fold_ordinal,
            FoldRole.WALK_FORWARD,
            None,
            fold.test_window,
            0,
            0,
        ),
        FoldProjection(
            key,
            ExperimentStatus.COMPLETED,
            None,
            occurred_at,
            occurred_at,
            1,
        ),
    )
    attempt_id = AttemptId(f"attempt:{candidate_id}:{fold.fold_id}")
    attempt_view = AttemptView(
        AttemptPersistenceSpec(
            attempt_id,
            key,
            1,
            None,
            None,
            ContentHash("c" * 64),
            occurred_at,
        ),
        AttemptProjection(
            attempt_id,
            ExperimentStatus.COMPLETED,
            BacktestRunId(f"run:{candidate_id}:{fold.fold_id}"),
            None,
            None,
            occurred_at,
            occurred_at,
            1,
        ),
    )

    class _Reader:
        def get_fold(self, lookup: FoldKey) -> FoldView | None:
            return fold_view if lookup == key else None

        def get_attempt(self, lookup: AttemptId) -> AttemptView | None:
            return attempt_view if lookup == attempt_id else None

    return load_persisted_fold_execution(
        cast("ExperimentReaderProtocol", _Reader()),
        key,
        attempt_id,
    )


def _fold(
    candidate: str,
    ordinal: int,
    fold_ordinal: int,
    navs: tuple[float, float],
    parameter_hash_override: ContentHash | None = None,
) -> CandidateFoldEvidence:
    candidate_id = CandidateId(candidate)
    fold = FOLDS[fold_ordinal - 1]
    report = _report(candidate_id, fold, navs)
    artifact_ref = f"artifact://{candidate}/{fold.fold_id}"
    return CandidateFoldEvidence(
        execution_binding=_execution_binding(candidate_id, fold),
        candidate_ordinal=ordinal,
        snapshot_id=SNAPSHOT_ID,
        snapshot_hash=ContentHash("a" * 64),
        parameter_hash=(
            CandidateSpec(
                candidate_id,
                ordinal,
                ordinal == 1,
                {"lookback": 0 if ordinal == 1 else 20},
            ).parameter_hash
            if parameter_hash_override is None
            else parameter_hash_override
        ),
        resolved_spec_hash=ContentHash(f"{ordinal + 256:064x}"),
        result_ref=f"result://{candidate}/{fold.fold_id}",
        result_hash=backtest_report_content_hash(report),
        artifact_ref=artifact_ref,
        artifact_hash=ContentHash(hashlib.sha256(artifact_ref.encode()).hexdigest()),
        backtest_report=report,
    )


def _candidates(
    *,
    alpha_candidate: str = "candidate-alpha",
) -> tuple[CandidateSpec, CandidateSpec]:
    return (
        CandidateSpec(
            CandidateId("candidate-baseline"),
            1,
            True,
            {"lookback": 0},
        ),
        CandidateSpec(
            CandidateId(alpha_candidate),
            2,
            False,
            {"lookback": 20},
        ),
    )


def _execution_bindings(
    candidates: tuple[CandidateSpec, ...],
) -> tuple[CandidateExecutionBinding, ...]:
    return tuple(
        CandidateExecutionBinding(
            candidate.candidate_id,
            candidate.ordinal,
            candidate.parameter_hash,
            ContentHash(f"{candidate.ordinal + 256:064x}"),
        )
        for candidate in candidates
    )


def _objective(
    candidates: tuple[CandidateSpec, ...],
    *,
    pbo_partition_plan: PboPartitionPlan | None = None,
    prior_members: tuple[LogicalTrialIdentity, ...] = (),
    prior_trial_evidence: tuple[PriorTrialEvidenceDeclaration, ...] = (),
) -> PromotionObjective:
    family = TrialFamilyDeclaration(
        "family-r3",
        tuple(
            LogicalTrialIdentity(
                EXPERIMENT_ID,
                candidate.candidate_id,
                candidate.ordinal,
                candidate.parameter_hash,
                TrialKind.CURRENT,
            )
            for candidate in candidates
        ),
    )
    family = TrialFamilyDeclaration(
        "family-r3",
        (*prior_members, *family.current_members),
    )
    return PromotionObjective(
        ObjectiveMetric(
            ResearchMetricId.NET_RETURN,
            ResearchMetricDirection.MAXIMIZE,
        ),
        (),
        (),
        CandidateId("candidate-baseline"),
        "Prefer the strongest durable return after costs.",
        family,
        pbo_partition_plan,
        prior_trial_evidence,
    )


def _launch(
    *,
    alpha_candidate: str = "candidate-alpha",
    pbo_partition_plan: PboPartitionPlan | None = None,
    prior_members: tuple[LogicalTrialIdentity, ...] = (),
    prior_trial_evidence: tuple[PriorTrialEvidenceDeclaration, ...] = (),
) -> ExperimentLaunchSpec:
    candidates = _candidates(alpha_candidate=alpha_candidate)
    return ExperimentLaunchSpec(
        experiment_id=EXPERIMENT_ID,
        strategy_version=StrategyVersion("stock-selection@3"),
        strategy_spec_hash=ContentHash("8" * 64),
        snapshot_id=SNAPSHOT_ID,
        candidates=candidates,
        execution_bindings=_execution_bindings(candidates),
        promotion_objective=_objective(
            candidates,
            pbo_partition_plan=pbo_partition_plan,
            prior_members=prior_members,
            prior_trial_evidence=prior_trial_evidence,
        ),
        fold_protocol=FoldProtocolSpec(
            "r3-walk-forward",
            1,
            ContentHash("7" * 64),
        ),
        seed=17,
        worker_count=2,
        failure_policy=ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES,
        budget=ExperimentBudget(128, 1_000),
        desired_state=ExperimentDesiredState.RUN,
        created_at=datetime(2026, 7, 22, tzinfo=UTC),
    )


def _aggregation_with_typed_metrics(
    *,
    alpha_fold_count: int = 2,
    alpha_parameter_hash: ContentHash | None = None,
) -> WalkForwardAggregation:
    rows = (
        _fold("candidate-baseline", 1, 1, (100.0, 100.0)),
        _fold("candidate-baseline", 1, 2, (100.0, 100.0)),
        *(
            _fold(
                "candidate-alpha",
                2,
                fold_ordinal,
                (101.0, 103.02) if fold_ordinal == 1 else (99.0, 99.0),
                alpha_parameter_hash,
            )
            for fold_ordinal in range(1, alpha_fold_count + 1)
        ),
    )
    return aggregate_walk_forward(
        build_candidate_comparison(_baseline_identity(), rows)
    )


def test_bridge_preserves_typed_metrics_lineage_and_derives_sharpe_sampling() -> None:
    aggregation = _aggregation_with_typed_metrics()
    outcomes = project_walk_forward_trial_outcomes(
        _launch(),
        aggregation,
    )

    baseline, alpha = outcomes
    assert baseline.status is TrialStatus.COMPLETED
    assert alpha.status is TrialStatus.COMPLETED
    assert alpha.source_projection_hash == aggregation.content_hash
    assert ResearchMetricId.NET_RETURN in alpha.metrics
    assert ResearchMetricId.SHARPE_RATIO in alpha.metrics
    assert ResearchMetricId.CAPACITY not in alpha.metrics
    lineage = alpha.metric_evidence[ResearchMetricId.SHARPE_RATIO]
    assert lineage.evidence_refs == (
        "result://candidate-alpha/wf-1",
        "result://candidate-alpha/wf-2",
    )
    expected_hashes = tuple(
        fold.source.result_hash for fold in aggregation.candidates[1].folds
    )
    assert lineage.evidence_hashes == expected_hashes
    assert alpha.sharpe_sampling is not None
    assert alpha.sharpe_sampling.observation_count == 4
    assert alpha.sharpe_sampling.return_frequency.value == "daily"
    assert alpha.sharpe_sampling.periods_per_year == 252
    assert alpha.sharpe_sampling.return_series_hash != ContentHash("e" * 64)


def test_bridge_maps_incomplete_candidate_to_failed_without_survivor_metrics() -> None:
    outcomes = project_walk_forward_trial_outcomes(
        _launch(),
        _aggregation_with_typed_metrics(alpha_fold_count=1),
    )

    assert outcomes[1].status is TrialStatus.FAILED
    assert outcomes[1].failure_reason == "incomplete_walk_forward_folds"
    assert not outcomes[1].metrics
    assert not outcomes[1].metric_evidence
    assert outcomes[1].sharpe_sampling is None


def test_bridge_rejects_candidate_substitution_against_declared_family() -> None:
    with pytest.raises(AppProcessError) as exc_info:
        project_walk_forward_trial_outcomes(
            _launch(alpha_candidate="candidate-substituted"),
            _aggregation_with_typed_metrics(),
        )

    assert exc_info.value.details["reason"] == "walk_forward_trial_family_mismatch"


def test_bridge_rejects_fold_evidence_from_substituted_candidate_parameters() -> None:
    with pytest.raises(AppProcessError) as exc_info:
        project_walk_forward_trial_outcomes(
            _launch(),
            _aggregation_with_typed_metrics(alpha_parameter_hash=ContentHash("f" * 64)),
        )

    assert exc_info.value.details["reason"] == "walk_forward_candidate_lineage_drift"


def test_bridge_marks_unregistered_prior_evidence_failed_without_consuming_it() -> None:
    prior = LogicalTrialIdentity(
        ExperimentId("experiment-prior"),
        CandidateId("candidate-prior"),
        1,
        ContentHash("6" * 64),
        TrialKind.PRIOR,
    )
    aggregation = _aggregation_with_typed_metrics()

    outcomes = project_walk_forward_trial_outcomes(
        _launch(prior_members=(prior,)),
        aggregation,
    )

    prior_outcome = next(item for item in outcomes if item.trial == prior)
    assert prior_outcome.status is TrialStatus.FAILED
    assert prior_outcome.failure_reason == "prior_evidence_not_preregistered"

    fabricated = TrialOutcome(
        trial=prior,
        status=TrialStatus.FAILED,
        metrics={},
        holdout_metrics={},
        source_projection_hash=ContentHash("5" * 64),
        failure_reason="caller_authored",
    )
    with pytest.raises(AppProcessError) as exc_info:
        project_walk_forward_trial_outcomes(
            _launch(prior_members=(prior,)),
            aggregation,
            prior_outcomes=(fabricated,),
        )
    assert exc_info.value.details["reason"] == (
        "prior_trial_evidence_not_preregistered"
    )


def test_bridge_rejects_prior_outcome_not_matching_preregistered_hash() -> None:
    prior = LogicalTrialIdentity(
        ExperimentId("experiment-prior"),
        CandidateId("candidate-prior"),
        1,
        ContentHash("6" * 64),
        TrialKind.PRIOR,
    )
    registered = TrialOutcome(
        trial=prior,
        status=TrialStatus.FAILED,
        metrics={},
        holdout_metrics={},
        source_projection_hash=ContentHash("5" * 64),
        failure_reason="registered_failure",
    )
    declaration = PriorTrialEvidenceDeclaration(
        prior,
        trial_outcome_content_hash(registered),
    )
    substituted = TrialOutcome(
        trial=prior,
        status=TrialStatus.FAILED,
        metrics={},
        holdout_metrics={},
        source_projection_hash=ContentHash("5" * 64),
        failure_reason="substituted_failure",
    )

    with pytest.raises(AppProcessError) as exc_info:
        project_walk_forward_trial_outcomes(
            _launch(
                prior_members=(prior,),
                prior_trial_evidence=(declaration,),
            ),
            _aggregation_with_typed_metrics(),
            prior_outcomes=(substituted,),
        )

    assert exc_info.value.details["reason"] == (
        "prior_trial_outcome_content_hash_mismatch"
    )


def _pbo_plan(
    aggregation: WalkForwardAggregation,
    *,
    first_window_start: date | None = None,
) -> PboPartitionPlan:
    candidate = aggregation.candidates[1]
    assert candidate.stitched_returns is not None
    rows = candidate.stitched_returns.daily_returns
    return PboPartitionPlan(
        ResearchMetricId.NET_RETURN,
        ResearchMetricDirection.MAXIMIZE,
        PboEstimator.COMPOUND_RETURN,
        SamplingReturnUnit.PER_PERIOD_DECIMAL,
        ReturnFrequency.DAILY,
        252,
        tuple(
            PboPartitionIdentity(
                f"partition-{ordinal}",
                ordinal,
                (
                    first_window_start
                    if ordinal == 1 and first_window_start is not None
                    else date.fromisoformat(row[1])
                ),
                date.fromisoformat(row[1]),
                1,
                partition_observation_date_grid_hash((date.fromisoformat(row[1]),)),
            )
            for ordinal, row in enumerate(rows, start=1)
        ),
    )


def test_bridge_derives_sampling_only_from_the_preregistered_pbo_plan() -> None:
    aggregation = _aggregation_with_typed_metrics()
    outcomes = project_walk_forward_trial_outcomes(
        _launch(pbo_partition_plan=_pbo_plan(aggregation)),
        aggregation,
    )

    assert all(outcome.pbo_sampling is not None for outcome in outcomes)
    sampling = outcomes[1].pbo_sampling
    assert sampling is not None
    assert (
        tuple(partition.identity for partition in sampling.partitions)
        == _pbo_plan(aggregation).partitions
    )


def test_bridge_rejects_plan_that_does_not_fit_stitched_returns() -> None:
    aggregation = _aggregation_with_typed_metrics()
    launch = _launch(
        pbo_partition_plan=_pbo_plan(
            aggregation,
            first_window_start=date(2023, 12, 31),
        )
    )

    with pytest.raises(AppProcessError) as exc_info:
        project_walk_forward_trial_outcomes(launch, aggregation)

    assert exc_info.value.details["reason"] == (
        "pbo_partition_plan_stitched_return_mismatch"
    )


def test_bridge_emits_no_current_pbo_sampling_without_a_preregistered_plan() -> None:
    aggregation = _aggregation_with_typed_metrics()
    outcomes = project_walk_forward_trial_outcomes(_launch(), aggregation)

    assert all(outcome.pbo_sampling is None for outcome in outcomes)


def test_pre_holdout_selection_verifier_accepts_ranked_completed_current_trial() -> (
    None
):
    launch = _launch()
    outcomes = project_walk_forward_trial_outcomes(
        launch,
        _aggregation_with_typed_metrics(),
    )
    ledger = build_trial_ledger(launch.promotion_objective, outcomes)
    selected = ledger.ranked_candidate_ids[0]

    verified = verify_pre_holdout_selection_evidence(
        ledger,
        launch_spec=launch,
        experiment_id=EXPERIMENT_ID,
        candidate_id=selected,
        expected_content_hash=ledger.content_hash,
    )

    assert verified.experiment_id == EXPERIMENT_ID
    assert verified.candidate_id == selected
    assert verified.content_hash == ledger.content_hash


def test_pre_holdout_selection_verifier_rejects_drift() -> None:
    launch = _launch()
    outcomes = project_walk_forward_trial_outcomes(
        launch,
        _aggregation_with_typed_metrics(),
    )
    ledger = build_trial_ledger(launch.promotion_objective, outcomes)
    selected = ledger.ranked_candidate_ids[0]

    with pytest.raises(AppProcessError, match="selection evidence"):
        verify_pre_holdout_selection_evidence(
            ledger,
            launch_spec=launch,
            experiment_id=EXPERIMENT_ID,
            candidate_id=selected,
            expected_content_hash=ContentHash("0" * 64),
        )
    with pytest.raises(AppProcessError, match="selection evidence"):
        verify_pre_holdout_selection_evidence(
            ledger,
            launch_spec=launch,
            experiment_id=ExperimentId("experiment-substituted"),
            candidate_id=selected,
            expected_content_hash=ledger.content_hash,
        )
    with pytest.raises(AppProcessError, match="selection evidence"):
        verify_pre_holdout_selection_evidence(
            ledger,
            launch_spec=launch,
            experiment_id=EXPERIMENT_ID,
            candidate_id=CandidateId("candidate-unranked"),
            expected_content_hash=ledger.content_hash,
        )

    alpha = outcomes[1]
    metric_id = ResearchMetricId.NET_RETURN
    contaminated = replace(
        alpha,
        holdout_metrics={metric_id: alpha.metrics[metric_id]},
        holdout_metric_evidence={metric_id: alpha.metric_evidence[metric_id]},
    )
    contaminated_ledger = build_trial_ledger(
        launch.promotion_objective,
        (outcomes[0], contaminated),
    )
    with pytest.raises(AppProcessError, match="selection evidence"):
        verify_pre_holdout_selection_evidence(
            contaminated_ledger,
            launch_spec=launch,
            experiment_id=EXPERIMENT_ID,
            candidate_id=selected,
            expected_content_hash=contaminated_ledger.content_hash,
        )
