"""Unit tests for deterministic unified-equity walk-forward evidence."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, date, datetime
from itertools import permutations
from statistics import stdev
from typing import cast

import pytest
from ditto_analysis.experiments import (
    ArtifactRecord,
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    BacktestRunId,
    CandidateId,
    ContentHash,
    DateWindow,
    ExperimentId,
    ExperimentReaderProtocol,
    ExperimentStatus,
    FoldId,
    FoldKey,
    FoldPersistenceSpec,
    FoldProjection,
    FoldRole,
    FoldView,
    ResearchMetricId,
    SnapshotId,
    canonical_payload,
)
from ditto_analysis.experiments.artifact_manifest import (
    ArtifactFormat,
    ArtifactManifest,
    ArtifactPublicationSpec,
)
from ditto_analysis.research.artifact_measurement import measure_json_bytes
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._persisted_execution_evidence import (
    PersistedFoldExecutionEvidence,
)
from ditto_application.processes.experiments._report_evidence import (
    BACKTEST_REPORT_ARTIFACT_KIND,
    BacktestReportArtifactIdentity,
    BacktestReportEvidence,
    LoadedBacktestReportArtifact,
)
from ditto_application.processes.experiments.baseline_registry import (
    BaselinePlanRequest,
    BaselineRef,
    default_baseline_registry,
)
from ditto_application.processes.experiments.comparison import (
    BaselineComparisonIdentity,
    CandidateFoldEvidence,
    CapacityEvidence,
    EvidenceStatus,
    FactorDiagnosticsArtifactEvidence,
    OOSFoldRegistration,
    build_candidate_comparison,
    load_persisted_fold_execution,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
    ExactUniverseIdentity,
)
from ditto_application.processes.experiments.walk_forward import (
    R3_WALK_FORWARD_ARTIFACT_SCHEMA_ID,
    R3_WALK_FORWARD_ARTIFACT_SCHEMA_VERSION,
    CandidateWalkForwardStatus,
    StitchedReturnEvidence,
    WalkForwardAggregation,
    aggregate_walk_forward,
)
from ditto_backtest.statistics import (
    AggregatedTradeStatistics,
    AlphaStatistics,
    BacktestReport,
)
from ditto_features.evaluation.report import (
    R3FactorDiagnosticsProvenance,
    project_r3_factor_diagnostics,
)
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting import FillEvent

EXPERIMENT_ID = ExperimentId("experiment-r3")
SNAPSHOT_ID = SnapshotId("snapshot-r3")
SNAPSHOT_HASH = ContentHash("a" * 64)
FOLDS = (
    OOSFoldRegistration(
        FoldId("wf-1"),
        1,
        DateWindow(date(2024, 1, 1), date(2024, 1, 3)),
    ),
    OOSFoldRegistration(
        FoldId("wf-2"),
        2,
        DateWindow(date(2025, 1, 1), date(2025, 1, 3)),
    ),
)


def _baseline_identity() -> BaselineComparisonIdentity:
    plan = default_baseline_registry().plan(
        BaselinePlanRequest(
            BaselineRef("stock_universe_equal_weight", 1),
            ExactResearchSnapshot(str(SNAPSHOT_ID), str(SNAPSHOT_HASH)),
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
        999.0,
        999.0,
        999.0,
        999.0,
        -99.0,
        999,
        999.0,
        None,
        None,
        None,
        None,
        999.0,
        999.0,
        999.0,
        999.0,
        999.0,
    )


def _report(
    candidate_id: CandidateId,
    fold: OOSFoldRegistration,
    navs: tuple[float, float],
) -> BacktestReport:
    fill = FillEvent(
        fill_id=f"fill:{candidate_id}:{fold.fold_id}",
        order_id=f"order:{candidate_id}:{fold.fold_id}",
        instrument_id=InstrumentId(1),
        direction=OrderSide.BUY,
        filled_quantity=2,
        fill_price=10.0,
        fee=1.0,
        slippage=0.0,
        event_time=datetime.combine(
            fold.test_window.start,
            datetime.min.time(),
            tzinfo=UTC,
        ),
        cumulative_quantity=2,
        leaves_quantity=0,
    )
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
        fill_log=(fill,),
    )


def _diagnostics(
    candidate_id: CandidateId,
    fold: OOSFoldRegistration,
) -> FactorDiagnosticsArtifactEvidence:
    source = {
        "coverage": 0.95,
        "rank_ic": 0.03 * fold.fold_ordinal,
        "market_regime_performance": {"bull": 0.1 * fold.fold_ordinal},
    }
    projection = project_r3_factor_diagnostics(
        source,
        provenance=R3FactorDiagnosticsProvenance(
            factor_id="momentum_1m",
            factor_version=1,
            evaluation_period=(
                fold.test_window.start.isoformat(),
                fold.test_window.end.isoformat(),
            ),
            dataset_id="factor_evaluation",
            catalog_snapshot_id=str(SNAPSHOT_ID),
            universe="a-share-r3",
            cost_bps=20.0,
        ),
    )
    return FactorDiagnosticsArtifactEvidence(
        experiment_id=EXPERIMENT_ID,
        candidate_id=candidate_id,
        fold_id=fold.fold_id,
        snapshot_id=SNAPSHOT_ID,
        snapshot_hash=SNAPSHOT_HASH,
        test_window=fold.test_window,
        artifact_ref=f"diagnostic://{candidate_id}/{fold.fold_id}",
        projection=projection,
    )


def _execution_binding(
    candidate_id: CandidateId,
    fold: OOSFoldRegistration,
    *,
    status: ExperimentStatus = ExperimentStatus.COMPLETED,
):
    occurred_at = datetime(2024, 1, 1, tzinfo=UTC)
    key = FoldKey(EXPERIMENT_ID, candidate_id, fold.fold_id)
    fold_spec = FoldPersistenceSpec.create(
        key,
        fold.fold_ordinal,
        FoldRole.WALK_FORWARD,
        None,
        fold.test_window,
        0,
        0,
    )
    attempt_id = AttemptId(f"attempt:{candidate_id}:{fold.fold_id}")
    run_id = BacktestRunId(f"run:{candidate_id}:{fold.fold_id}")
    fold_view = FoldView(
        fold_spec,
        FoldProjection(key, status, None, occurred_at, occurred_at, 1),
    )
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
            status,
            run_id,
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
        cast("ExperimentReaderProtocol", _Reader()), key, attempt_id
    )


def _loaded_report(
    binding: PersistedFoldExecutionEvidence,
    report: BacktestReport,
) -> LoadedBacktestReportArtifact:
    evidence = BacktestReportEvidence.from_report(report)
    identity = _artifact_identity(binding)
    return LoadedBacktestReportArtifact(
        record=_artifact_record(identity, evidence),
        evidence=evidence,
    )


def _artifact_identity(
    binding: PersistedFoldExecutionEvidence,
) -> BacktestReportArtifactIdentity:
    return BacktestReportArtifactIdentity(
        experiment_id=binding.experiment_id,
        candidate_id=binding.candidate_id,
        fold_id=binding.fold_id,
        attempt_id=binding.attempt_id,
        attempt_created_at=binding.attempt_view.spec.created_at,
        run_id=binding.run_id,
        test_window=binding.test_window,
        reproduction_fingerprint=binding.reproduction_fingerprint,
    )


def _artifact_record(
    identity: BacktestReportArtifactIdentity,
    evidence: BacktestReportEvidence,
) -> ArtifactRecord:
    measurement = measure_json_bytes(
        canonical_payload(evidence.canonical_payload()).json_bytes
    )
    return ArtifactManifest.create(
        spec=ArtifactPublicationSpec(
            artifact_id=identity.artifact_id,
            experiment_id=identity.experiment_id,
            candidate_id=identity.candidate_id,
            fold_id=identity.fold_id,
            attempt_id=identity.attempt_id,
            artifact_kind=BACKTEST_REPORT_ARTIFACT_KIND,
            relative_path=identity.relative_path,
            reproduction_fingerprint=identity.reproduction_fingerprint,
            audit={
                "attempt_id": str(identity.attempt_id),
                "created_at": identity.attempt_created_at.isoformat(),
                "run_id": str(identity.run_id),
            },
            created_at=identity.attempt_created_at,
        ),
        artifact_format=ArtifactFormat.JSON,
        content_hash=measurement.content_hash,
        schema_hash=measurement.schema_hash,
        row_count=measurement.row_count,
        byte_size=measurement.byte_size,
    ).to_record()


def _with_report(
    source: CandidateFoldEvidence,
    report: BacktestReportEvidence,
) -> CandidateFoldEvidence:
    artifact = source.report_artifact
    assert artifact is not None
    return replace(
        source,
        report_artifact=replace(
            artifact,
            evidence=report,
            record=_artifact_record(
                _artifact_identity(source.execution_binding),
                report,
            ),
        ),
    )


def _evidence(
    candidate: str,
    candidate_ordinal: int,
    fold_ordinal: int,
    navs: tuple[float, float],
    *,
    capacity: float | None = 1_000_000.0,
) -> CandidateFoldEvidence:
    candidate_id = CandidateId(candidate)
    fold = FOLDS[fold_ordinal - 1]
    report = _report(candidate_id, fold, navs)
    execution_binding = _execution_binding(candidate_id, fold)
    return CandidateFoldEvidence(
        execution_binding=execution_binding,
        candidate_ordinal=candidate_ordinal,
        snapshot_id=SNAPSHOT_ID,
        snapshot_hash=SNAPSHOT_HASH,
        parameter_hash=ContentHash("1" * 64),
        resolved_spec_hash=ContentHash("2" * 64),
        report_artifact=_loaded_report(execution_binding, report),
        factor_diagnostics=_diagnostics(candidate_id, fold),
        capacity=(
            None
            if capacity is None
            else CapacityEvidence(
                experiment_id=EXPERIMENT_ID,
                candidate_id=candidate_id,
                fold_id=fold.fold_id,
                snapshot_id=SNAPSHOT_ID,
                snapshot_hash=SNAPSHOT_HASH,
                parameter_hash=ContentHash("1" * 64),
                resolved_spec_hash=ContentHash("2" * 64),
                test_window=fold.test_window,
                value_cny=capacity,
                evidence_ref=f"capacity://{candidate_id}/{fold.fold_id}",
                method="participation_rate_stress_v1",
            )
        ),
    )


def _rows() -> tuple[CandidateFoldEvidence, ...]:
    return (
        _evidence("candidate-baseline", 1, 1, (102.0, 102.0), capacity=2_000_000.0),
        _evidence("candidate-baseline", 1, 2, (104.0, 104.0), capacity=1_800_000.0),
        _evidence("candidate-alpha", 2, 1, (120.0, 110.0), capacity=1_000_000.0),
        _evidence("candidate-alpha", 2, 2, (100.0, 95.0), capacity=800_000.0),
    )


def test_metrics_are_recomputed_from_one_stitched_equity_curve() -> None:
    result = aggregate_walk_forward(
        build_candidate_comparison(_baseline_identity(), reversed(_rows()))
    )
    candidate = result.candidates[1]
    daily_returns = (0.2, 110.0 / 120.0 - 1.0, 0.0, -0.05)
    expected_sharpe = (
        sum(daily_returns) / len(daily_returns) / stdev(daily_returns) * math.sqrt(252)
    )
    expected_drawdown = (95.0 * 1.1 / 120.0 - 1.0) * 100.0
    expected_annualized = (1.045 ** (252 / 4) - 1.0) * 100.0

    assert candidate.status is CandidateWalkForwardStatus.COMPLETED
    assert candidate.metrics[ResearchMetricId.NET_RETURN].value == pytest.approx(4.5)
    assert candidate.metrics[ResearchMetricId.SHARPE_RATIO].value == pytest.approx(
        expected_sharpe
    )
    assert candidate.metrics[ResearchMetricId.MAX_DRAWDOWN].value == pytest.approx(
        expected_drawdown
    )
    assert candidate.metrics[ResearchMetricId.MAX_DRAWDOWN].value < min(
        cast("float", fold.metrics[ResearchMetricId.MAX_DRAWDOWN].value)
        for fold in candidate.folds
    )
    assert candidate.metrics[ResearchMetricId.CALMAR_RATIO].value == pytest.approx(
        expected_annualized / abs(expected_drawdown)
    )
    assert candidate.metrics[ResearchMetricId.SHARPE_RATIO].value != 999.0
    assert candidate.stitched_returns is not None
    assert tuple(item[2] for item in candidate.stitched_returns.daily_returns) == (
        pytest.approx(daily_returns)
    )


def test_execution_metrics_use_recomputed_scaling_and_capacity_is_explicit() -> None:
    result = aggregate_walk_forward(
        build_candidate_comparison(_baseline_identity(), _rows())
    )
    candidate = result.candidates[1]

    expected_turnover = (0.2 + 0.22) / ((1.2 + 1.1 + 1.1 + 1.045) / 4.0)
    assert candidate.metrics[ResearchMetricId.TURNOVER].value == pytest.approx(
        expected_turnover
    )
    assert candidate.metrics[ResearchMetricId.COST_DRAG].value == pytest.approx(2.1)
    assert candidate.metrics[ResearchMetricId.CAPACITY].value == 800_000.0


def test_execution_metrics_reweight_unequal_fold_capital_on_stitched_equity() -> None:
    first = _evidence("candidate-alpha", 2, 1, (110.0, 110.0))
    second_source = _evidence("candidate-alpha", 2, 2, (120.0, 120.0))
    second_report = replace(
        second_source.backtest_report,
        initial_cash=1_000.0,
        final_nav=1_200.0,
        nav_series=(
            (FOLDS[1].test_window.start.isoformat(), 1_200.0),
            (FOLDS[1].test_window.end.isoformat(), 1_200.0),
        ),
    )
    second = _with_report(second_source, second_report)
    rows = (*_rows()[:2], first, second)
    candidate = aggregate_walk_forward(
        build_candidate_comparison(_baseline_identity(), rows)
    ).candidates[1]

    normalized_notional = 20.0 / 100.0 + 20.0 / 1_000.0 * 1.1
    average_stitched_nav = (1.1 + 1.1 + 1.32 + 1.32) / 4.0
    assert candidate.metrics[ResearchMetricId.TURNOVER].value == pytest.approx(
        normalized_notional / average_stitched_nav
    )
    assert candidate.metrics[ResearchMetricId.COST_DRAG].value == pytest.approx(1.11)


def test_fold_stability_includes_absolute_and_relative_baseline_direction() -> None:
    rows = (
        _evidence("candidate-baseline", 1, 1, (102.0, 102.0)),
        _evidence("candidate-baseline", 1, 2, (104.0, 104.0)),
        _evidence("candidate-alpha", 2, 1, (103.0, 103.0)),
        _evidence("candidate-alpha", 2, 2, (102.0, 102.0)),
    )
    candidate = aggregate_walk_forward(
        build_candidate_comparison(_baseline_identity(), rows)
    ).candidates[1]

    assert candidate.fold_stability.direction_consistent is True
    assert candidate.fold_stability.positive_fold_count == 2
    assert candidate.relative_baseline_stability.direction_consistent is False
    assert candidate.relative_baseline_stability.positive_fold_count == 1
    assert candidate.relative_baseline_stability.negative_fold_count == 1
    baseline_net = (1.02 * 1.04 - 1.0) * 100.0
    candidate_net = (1.03 * 1.02 - 1.0) * 100.0
    assert candidate.metrics[ResearchMetricId.RELATIVE_NET_RETURN].value == (
        pytest.approx(candidate_net - baseline_net)
    )


def test_diagnostic_aggregation_retains_each_fold_artifact_reference_and_hash() -> None:
    candidate = aggregate_walk_forward(
        build_candidate_comparison(_baseline_identity(), _rows())
    ).candidates[1]
    coverage = candidate.factor_diagnostics[ResearchMetricId.COVERAGE]

    assert coverage.status is EvidenceStatus.EVALUATED
    assert coverage.fold_values == (
        (FoldId("wf-1"), 0.95),
        (FoldId("wf-2"), 0.95),
    )
    assert coverage.evidence_refs == (
        "diagnostic://candidate-alpha/wf-1",
        "diagnostic://candidate-alpha/wf-2",
    )
    expected_hashes: list[ContentHash] = []
    for fold in candidate.folds:
        diagnostics = fold.source.factor_diagnostics
        assert diagnostics is not None
        expected_hashes.append(diagnostics.artifact_hash)
    assert coverage.evidence_hashes == tuple(expected_hashes)


def test_missing_capacity_and_diagnostic_are_honestly_not_evaluated() -> None:
    rows = list(_rows())
    rows[3] = replace(
        rows[3],
        capacity=None,
        factor_diagnostics=None,
    )
    candidate = aggregate_walk_forward(
        build_candidate_comparison(_baseline_identity(), rows)
    ).candidates[1]

    assert candidate.metrics[ResearchMetricId.NET_RETURN].status is (
        EvidenceStatus.EVALUATED
    )
    assert candidate.metrics[ResearchMetricId.CAPACITY].reason == (
        "capacity_evidence_missing"
    )
    coverage = candidate.factor_diagnostics[ResearchMetricId.COVERAGE]
    assert coverage.status is EvidenceStatus.NOT_EVALUATED
    assert coverage.reason == "fold_diagnostic_not_evaluated"
    assert coverage.fold_values == ((FoldId("wf-1"), 0.95),)


def test_completed_fold_without_primary_return_evidence_is_not_evaluated() -> None:
    rows = list(_rows())
    rows[3] = replace(rows[3], report_artifact=None)

    candidate = aggregate_walk_forward(
        build_candidate_comparison(_baseline_identity(), rows)
    ).candidates[1]

    assert candidate.status is CandidateWalkForwardStatus.NOT_EVALUATED
    assert all(
        item.reason == "incomplete_walk_forward_folds"
        for item in candidate.metrics.values()
    )


def test_missing_baseline_primary_evidence_blocks_every_candidate() -> None:
    rows = list(_rows())
    rows[1] = replace(rows[1], report_artifact=None)

    result = aggregate_walk_forward(
        build_candidate_comparison(_baseline_identity(), rows)
    )

    assert all(
        candidate.status is CandidateWalkForwardStatus.NOT_EVALUATED
        for candidate in result.candidates
    )
    assert all(
        metric.reason == "incomplete_walk_forward_folds"
        for candidate in result.candidates
        for metric in candidate.metrics.values()
    )


def test_candidate_return_grid_must_exactly_match_baseline() -> None:
    rows = list(_rows())
    baseline = rows[0]
    assert baseline.backtest_report is not None
    report = replace(
        baseline.backtest_report,
        nav_series=(
            (FOLDS[0].test_window.start.isoformat(), 102.0),
            (date(2024, 1, 2).isoformat(), 102.0),
            (FOLDS[0].test_window.end.isoformat(), 102.0),
        ),
    )
    rows[0] = _with_report(baseline, report)

    with pytest.raises(AppProcessError) as exc_info:
        aggregate_walk_forward(build_candidate_comparison(_baseline_identity(), rows))

    assert exc_info.value.details["reason"] == "candidate_return_grid_drift"


def test_failed_and_incomplete_candidates_remain_visible() -> None:
    failed_source = _evidence("candidate-failed", 3, 1, (100.0, 100.0))
    failed = replace(
        failed_source,
        execution_binding=_execution_binding(
            failed_source.candidate_id,
            FOLDS[0],
            status=ExperimentStatus.FAILED,
        ),
        failure_reason="candidate_numeric_failure",
        report_artifact=None,
        factor_diagnostics=None,
        capacity=None,
    )
    rows = (*_rows(), failed, _evidence("candidate-incomplete", 4, 1, (101.0, 101.0)))
    result = aggregate_walk_forward(
        build_candidate_comparison(_baseline_identity(), rows)
    )

    failed_result = result.candidates[2]
    incomplete = result.candidates[3]
    assert failed_result.status is CandidateWalkForwardStatus.FAILED
    assert all(
        item.reason == "candidate_failed" for item in failed_result.metrics.values()
    )
    assert incomplete.status is CandidateWalkForwardStatus.NOT_EVALUATED
    assert all(
        item.reason == "incomplete_walk_forward_folds"
        for item in incomplete.metrics.values()
    )


def test_every_input_permutation_produces_the_same_frozen_projection() -> None:
    projections = tuple(
        aggregate_walk_forward(build_candidate_comparison(_baseline_identity(), order))
        for order in permutations(_rows())
    )

    assert all(item == projections[0] for item in projections)
    assert tuple(item.candidate_id for item in projections[0].candidates) == (
        CandidateId("candidate-baseline"),
        CandidateId("candidate-alpha"),
    )


def test_walk_forward_candidate_content_hash_matches_canonical_payload() -> None:
    candidate = aggregate_walk_forward(
        build_candidate_comparison(_baseline_identity(), _rows())
    ).candidates[1]

    assert type(candidate.content_hash) is ContentHash
    assert (
        candidate.content_hash
        == canonical_payload(candidate.canonical_payload()).content_hash
    )


def test_walk_forward_candidate_content_hash_is_deterministic() -> None:
    rows = _rows()
    first = aggregate_walk_forward(
        build_candidate_comparison(_baseline_identity(), rows)
    ).candidates[1]
    permuted = aggregate_walk_forward(
        build_candidate_comparison(_baseline_identity(), reversed(rows))
    ).candidates[1]

    assert first.content_hash == permuted.content_hash


def test_walk_forward_candidate_content_hash_detects_evidence_drift() -> None:
    rows = _rows()
    original = aggregate_walk_forward(
        build_candidate_comparison(_baseline_identity(), rows)
    ).candidates[1]
    missing = replace(
        rows[2],
        report_artifact=None,
        factor_diagnostics=None,
        capacity=None,
    )
    changed = aggregate_walk_forward(
        build_candidate_comparison(
            _baseline_identity(),
            (*rows[:2], missing, rows[3]),
        )
    ).candidates[1]

    assert original.content_hash != changed.content_hash


def test_walk_forward_has_versioned_authoritative_content_identity() -> None:
    rows = _rows()
    first = aggregate_walk_forward(
        build_candidate_comparison(_baseline_identity(), rows)
    )
    permuted = aggregate_walk_forward(
        build_candidate_comparison(_baseline_identity(), reversed(rows))
    )
    missing = replace(
        rows[2],
        report_artifact=None,
        factor_diagnostics=None,
        capacity=None,
    )
    changed = aggregate_walk_forward(
        build_candidate_comparison(
            _baseline_identity(),
            (*rows[:2], missing, rows[3]),
        )
    )

    payload = first.canonical_payload()
    assert payload["artifact_schema"] == {
        "id": R3_WALK_FORWARD_ARTIFACT_SCHEMA_ID,
        "version": R3_WALK_FORWARD_ARTIFACT_SCHEMA_VERSION,
    }
    assert type(first.content_hash) is ContentHash
    assert first.content_hash == permuted.content_hash
    assert first.content_hash != changed.content_hash

    with pytest.raises(AppProcessError) as exc_info:
        WalkForwardAggregation(first.baseline, first.metric_schema, first.candidates)
    assert exc_info.value.details["reason"] == "walk_forward_factory_required"


def test_stitched_return_evidence_rejects_equity_recurrence_drift() -> None:
    with pytest.raises(AppProcessError) as exc_info:
        StitchedReturnEvidence(
            ((FoldId("wf-1"), "2024-01-01", 0.10),),
            ((FoldId("wf-1"), "2024-01-01", 1.05),),
            ("result://candidate/fold",),
            (ContentHash("1" * 64),),
        )

    assert exc_info.value.details["reason"] == ("stitched_return_equity_identity_drift")
