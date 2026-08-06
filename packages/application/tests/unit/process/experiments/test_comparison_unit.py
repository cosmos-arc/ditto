"""Unit tests for immutable R3 candidate/fold comparison evidence."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime
from inspect import signature
from itertools import permutations
from typing import cast

import pytest
from ditto_analysis.experiments import (
    R3_COMPARISON_METRIC_IDS,
    R3_DIAGNOSTIC_METRIC_IDS,
    R3_RESEARCH_METRIC_SCHEMA,
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
    ResearchMetricValue,
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
    R3_COMPARISON_ARTIFACT_SCHEMA_ID,
    R3_COMPARISON_ARTIFACT_SCHEMA_VERSION,
    BaselineComparisonIdentity,
    CandidateComparisonProjection,
    CandidateFoldEvidence,
    CapacityEvidence,
    DiagnosticEvidence,
    EvidenceStatus,
    FactorDiagnosticsArtifactEvidence,
    FoldReturnEvidence,
    OOSFoldRegistration,
    PersistedFoldExecutionEvidence,
    ScalarEvidence,
    build_candidate_comparison,
    load_persisted_fold_execution,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
    ExactUniverseIdentity,
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
OOS_FOLDS = (
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


def _baseline_identity(
    folds: tuple[OOSFoldRegistration, ...] = OOS_FOLDS,
) -> BaselineComparisonIdentity:
    plan = default_baseline_registry().plan(
        BaselinePlanRequest(
            baseline_ref=BaselineRef("stock_universe_equal_weight", 1),
            snapshot=ExactResearchSnapshot(
                str(SNAPSHOT_ID),
                str(SNAPSHOT_HASH),
            ),
            universe=ExactUniverseIdentity("a-share-r3", "b" * 64),
            exact_strategy=None,
        )
    )
    return BaselineComparisonIdentity(
        experiment_id=EXPERIMENT_ID,
        candidate_id=CandidateId("candidate-baseline"),
        plan=plan,
        oos_folds=folds,
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
        annualized_return=999.0,
        annualized_volatility=999.0,
        sharpe_ratio=999.0,
        sortino_ratio=999.0,
        max_drawdown=-99.0,
        max_drawdown_duration_days=999,
        calmar_ratio=999.0,
        information_ratio=None,
        tracking_error=None,
        beta=None,
        alpha_annualized=None,
        total_turnover=999.0,
        avg_turnover_per_rebalance=999.0,
        total_fees=999.0,
        net_return_after_cost=999.0,
        cost_drag=999.0,
    )


def _fill(fold: OOSFoldRegistration) -> FillEvent:
    return FillEvent(
        fill_id=f"fill-{fold.fold_ordinal}",
        order_id=f"order-{fold.fold_ordinal}",
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


def _report(
    candidate_id: CandidateId,
    fold: OOSFoldRegistration,
    navs: tuple[float, ...],
    *,
    initial_cash: float = 100.0,
    fills: tuple[FillEvent, ...] | None = None,
) -> BacktestReport:
    dates = tuple(
        (
            fold.test_window.start
            if index == 0
            else fold.test_window.end
            if index == len(navs) - 1
            else fold.test_window.start.replace(day=fold.test_window.start.day + index)
        ).isoformat()
        for index in range(len(navs))
    )
    return BacktestReport(
        run_id=f"run:{candidate_id}:{fold.fold_id}",
        period=(fold.test_window.start.isoformat(), fold.test_window.end.isoformat()),
        initial_cash=initial_cash,
        final_nav=navs[-1],
        trade_stats=(),
        portfolio_stats=(),
        aggregated_trade_stats=_empty_trades(),
        alpha_stats=_alpha(),
        nav_series=tuple(zip(dates, navs, strict=True)),
        trade_log=(),
        fill_log=(_fill(fold),) if fills is None else fills,
    )


def _diagnostics(
    candidate_id: CandidateId,
    fold: OOSFoldRegistration,
    *,
    factor_version: int = 1,
    snapshot_id: str = "snapshot-r3",
) -> FactorDiagnosticsArtifactEvidence:
    source = {
        "coverage": 0.97,
        "market_regime_performance": {"bull": 0.04},
        "liquidity": {"high": 0.8},
        "industry_exposure": {"bank": 0.1},
        "size_exposure": {"large": -0.1},
        "style_exposure": {"value": 0.2},
    }
    projection = project_r3_factor_diagnostics(
        source,
        provenance=R3FactorDiagnosticsProvenance(
            factor_id="momentum_1m",
            factor_version=factor_version,
            evaluation_period=(
                fold.test_window.start.isoformat(),
                fold.test_window.end.isoformat(),
            ),
            dataset_id="factor_evaluation",
            catalog_snapshot_id=snapshot_id,
            universe="a-share-r3",
            cost_bps=20.0,
        ),
    )
    return FactorDiagnosticsArtifactEvidence(
        experiment_id=EXPERIMENT_ID,
        candidate_id=candidate_id,
        fold_id=fold.fold_id,
        snapshot_id=SnapshotId(snapshot_id),
        snapshot_hash=SNAPSHOT_HASH,
        test_window=fold.test_window,
        artifact_ref=f"diagnostic://{candidate_id}/{fold.fold_id}",
        projection=projection,
    )


def _execution_binding(
    candidate_id: CandidateId,
    fold: OOSFoldRegistration,
    *,
    run_id: BacktestRunId | None = None,
    fold_role: FoldRole = FoldRole.WALK_FORWARD,
):
    occurred_at = datetime(2024, 1, 1, tzinfo=UTC)
    key = FoldKey(EXPERIMENT_ID, candidate_id, fold.fold_id)
    fold_spec = FoldPersistenceSpec.create(
        key,
        fold.fold_ordinal,
        fold_role,
        None,
        fold.test_window,
        0,
        0,
    )
    attempt_id = AttemptId(f"attempt:{candidate_id}:{fold.fold_id}")
    persisted_run_id = run_id or BacktestRunId(f"run:{candidate_id}:{fold.fold_id}")
    fold_view = FoldView(
        fold_spec,
        FoldProjection(
            key,
            ExperimentStatus.COMPLETED,
            None,
            occurred_at,
            occurred_at,
            1,
        ),
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
            ExperimentStatus.COMPLETED,
            persisted_run_id,
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


def _evidence(
    candidate: str,
    candidate_ordinal: int,
    fold_ordinal: int,
    navs: tuple[float, ...],
    *,
    report: BacktestReport | None = None,
    diagnostics: FactorDiagnosticsArtifactEvidence | None = None,
    capacity: bool = True,
    fold_override: OOSFoldRegistration | None = None,
) -> CandidateFoldEvidence:
    candidate_id = CandidateId(candidate)
    fold = OOS_FOLDS[fold_ordinal - 1] if fold_override is None else fold_override
    resolved_report = _report(candidate_id, fold, navs) if report is None else report
    execution_binding = _execution_binding(candidate_id, fold)
    report_evidence = BacktestReportEvidence.from_report(resolved_report)
    identity = _artifact_identity(execution_binding)
    report_artifact = LoadedBacktestReportArtifact(
        record=_artifact_record(identity, report_evidence),
        evidence=report_evidence,
    )
    return CandidateFoldEvidence(
        execution_binding=execution_binding,
        candidate_ordinal=candidate_ordinal,
        snapshot_id=SNAPSHOT_ID,
        snapshot_hash=SNAPSHOT_HASH,
        parameter_hash=ContentHash("1" * 64),
        resolved_spec_hash=ContentHash("2" * 64),
        report_artifact=report_artifact,
        factor_diagnostics=(
            _diagnostics(candidate_id, fold) if diagnostics is None else diagnostics
        ),
        capacity=(
            CapacityEvidence(
                experiment_id=EXPERIMENT_ID,
                candidate_id=candidate_id,
                fold_id=fold.fold_id,
                snapshot_id=SNAPSHOT_ID,
                snapshot_hash=SNAPSHOT_HASH,
                parameter_hash=ContentHash("1" * 64),
                resolved_spec_hash=ContentHash("2" * 64),
                test_window=fold.test_window,
                value_cny=1_000_000.0,
                evidence_ref=f"capacity://{candidate_id}/{fold.fold_id}",
                method="participation_rate_stress_v1",
            )
            if capacity
            else None
        ),
    )


def _baseline_rows() -> tuple[CandidateFoldEvidence, ...]:
    return (
        _evidence("candidate-baseline", 1, 1, (101.0, 102.0)),
        _evidence("candidate-baseline", 1, 2, (100.0, 101.0)),
    )


def test_comparison_binds_full_identity_and_analysis_owned_schema() -> None:
    candidate = _evidence("candidate-alpha", 2, 1, (96.0, 92.0))
    comparison = build_candidate_comparison(
        _baseline_identity(),
        (*_baseline_rows(), candidate),
    )

    assert comparison.metric_schema is R3_RESEARCH_METRIC_SCHEMA
    assert tuple(comparison.folds[0].metrics) == R3_COMPARISON_METRIC_IDS
    row = comparison.folds[1]
    assert row.source.attempt_id == candidate.attempt_id
    assert row.source.backtest_report is not None
    assert row.source.result_hash == row.source.backtest_report.content_hash
    assert row.source.artifact_hash == row.source.result_hash
    assert row.metrics[ResearchMetricId.NET_RETURN].value == pytest.approx(-8.0)
    assert row.metrics[ResearchMetricId.NET_RETURN].unit.value == "percent"
    assert row.metrics[ResearchMetricId.TURNOVER].value == pytest.approx(20.0 / 94.0)
    assert row.metrics[ResearchMetricId.COST_DRAG].value == 1.0
    assert row.return_evidence is not None
    assert row.return_evidence.nav_series == (
        ("2024-01-01", 96.0),
        ("2024-01-03", 92.0),
    )
    assert row.return_evidence.daily_returns[0][1] == pytest.approx(-0.04)
    assert row.return_evidence.evidence_refs == (candidate.result_ref,)
    assert row.return_evidence.evidence_hashes == (candidate.result_hash,)
    assert row.metrics[ResearchMetricId.NET_RETURN].evidence_refs == (
        candidate.result_ref,
    )
    assert row.metrics[ResearchMetricId.NET_RETURN].evidence_hashes == (
        candidate.result_hash,
    )


def test_diagnostics_use_fixed_schema_and_retain_artifact_evidence() -> None:
    comparison = build_candidate_comparison(
        _baseline_identity(),
        (*_baseline_rows(), _evidence("candidate-alpha", 2, 1, (100.0, 101.0))),
    )
    row = comparison.folds[1]

    assert tuple(row.factor_diagnostics) == R3_DIAGNOSTIC_METRIC_IDS
    coverage = row.factor_diagnostics[ResearchMetricId.COVERAGE]
    assert coverage.status is EvidenceStatus.EVALUATED
    assert coverage.value == 0.97
    assert coverage.evidence_refs == ("diagnostic://candidate-alpha/wf-1",)
    diagnostics = row.source.factor_diagnostics
    assert diagnostics is not None
    assert coverage.evidence_hashes == (diagnostics.artifact_hash,)
    missing = row.factor_diagnostics[ResearchMetricId.RANK_IC]
    assert missing.status is EvidenceStatus.NOT_EVALUATED
    assert missing.reason == "factor_diagnostic_not_computed"


def test_comparison_rejects_persisted_run_drift() -> None:
    source = _evidence("candidate-alpha", 2, 1, (100.0, 101.0))
    binding = _execution_binding(
        source.candidate_id,
        OOS_FOLDS[0],
        run_id=BacktestRunId("wrong-run"),
    )
    with pytest.raises(AppProcessError) as exc_info:
        replace(source, execution_binding=binding)

    assert exc_info.value.details["reason"] == "report_run_identity_drift"


def test_comparison_rejects_snapshot_drift() -> None:
    source = _evidence("candidate-alpha", 2, 1, (100.0, 101.0))
    evidence = replace(
        source,
        snapshot_id=SnapshotId("wrong-snapshot"),
        report_artifact=None,
        factor_diagnostics=None,
        capacity=None,
    )
    with pytest.raises(AppProcessError) as exc_info:
        build_candidate_comparison(
            _baseline_identity(),
            (*_baseline_rows(), evidence),
        )

    assert exc_info.value.details["reason"] == "snapshot_identity_drift"


def test_comparison_rejects_persisted_fold_window_drift() -> None:
    source = _evidence("candidate-alpha", 2, 1, (100.0, 101.0))
    changed_fold = OOSFoldRegistration(
        source.fold_id,
        source.fold_ordinal,
        DateWindow(date(2024, 1, 1), date(2024, 1, 2)),
    )
    evidence = replace(
        source,
        execution_binding=_execution_binding(source.candidate_id, changed_fold),
        report_artifact=None,
        factor_diagnostics=None,
        capacity=None,
    )
    with pytest.raises(AppProcessError) as exc_info:
        build_candidate_comparison(
            _baseline_identity(),
            (*_baseline_rows(), evidence),
        )

    assert exc_info.value.details["reason"] == "fold_window_drift"


def test_persisted_binding_rejects_holdout_as_walk_forward_evidence() -> None:
    with pytest.raises(AppProcessError) as exc_info:
        _execution_binding(
            CandidateId("candidate-alpha"),
            OOS_FOLDS[0],
            fold_role=FoldRole.HOLDOUT,
        )

    assert exc_info.value.details["reason"] == "invalid_persisted_execution_binding"


def test_candidate_evidence_rejects_report_period_drift() -> None:
    evidence = _evidence("candidate-alpha", 2, 1, (100.0, 101.0))
    artifact = evidence.report_artifact
    assert artifact is not None
    report = replace(
        artifact.evidence,
        period=("2023-12-31", "2024-01-03"),
    )
    drifted = replace(
        artifact,
        evidence=report,
        record=replace(artifact.record, content_hash=report.content_hash),
    )

    with pytest.raises(AppProcessError) as exc_info:
        replace(evidence, report_artifact=drifted)

    assert exc_info.value.details["reason"] == "report_period_drift"


def test_comparison_rejects_diagnostic_source_drift_across_folds() -> None:
    candidate_first = _evidence("candidate-alpha", 2, 1, (100.0, 101.0))
    candidate_second = _evidence(
        "candidate-alpha",
        2,
        2,
        (100.0, 102.0),
        diagnostics=_diagnostics(
            CandidateId("candidate-alpha"), OOS_FOLDS[1], factor_version=2
        ),
    )

    with pytest.raises(AppProcessError) as exc_info:
        build_candidate_comparison(
            _baseline_identity(),
            (*_baseline_rows(), candidate_first, candidate_second),
        )

    assert exc_info.value.details["reason"] == "factor_diagnostic_identity_drift"


def test_diagnostic_outer_hash_binds_candidate_fold_lineage() -> None:
    source = _evidence("candidate-alpha", 2, 1, (100.0, 101.0))
    diagnostics = source.factor_diagnostics
    assert diagnostics is not None
    relabeled = replace(diagnostics, candidate_id=CandidateId("candidate-other"))

    assert relabeled.artifact_hash != diagnostics.artifact_hash
    with pytest.raises(AppProcessError) as exc_info:
        replace(source, factor_diagnostics=relabeled)

    assert exc_info.value.details["reason"] == "factor_diagnostic_identity_drift"


def test_missing_report_capacity_and_diagnostics_are_typed_not_evaluated() -> None:
    source = _evidence("candidate-missing", 2, 1, (100.0, 101.0))
    missing = replace(
        source,
        report_artifact=None,
        factor_diagnostics=None,
        capacity=None,
    )
    comparison = build_candidate_comparison(
        _baseline_identity(),
        (*_baseline_rows(), missing),
    )
    row = comparison.folds[1]

    assert row.metrics[ResearchMetricId.NET_RETURN].reason == "backtest_report_missing"
    assert row.metrics[ResearchMetricId.TURNOVER].reason == ("backtest_report_missing")
    assert row.metrics[ResearchMetricId.CAPACITY].reason == (
        "capacity_evidence_missing"
    )
    assert all(
        item.status is EvidenceStatus.NOT_EVALUATED
        and item.reason == "factor_diagnostics_missing"
        for item in row.factor_diagnostics.values()
    )


def test_insufficient_nav_or_capital_never_falls_back_to_report_aggregates() -> None:
    source = _evidence("candidate-alpha", 2, 1, (100.0, 101.0))
    artifact = source.report_artifact
    assert artifact is not None
    report = replace(artifact.evidence, initial_cash=0.0)
    evidence = replace(
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
    comparison = build_candidate_comparison(
        _baseline_identity(),
        (*_baseline_rows(), evidence),
    )
    row = comparison.folds[1]

    for metric_id in (
        ResearchMetricId.NET_RETURN,
        ResearchMetricId.SHARPE_RATIO,
        ResearchMetricId.MAX_DRAWDOWN,
        ResearchMetricId.TURNOVER,
        ResearchMetricId.COST_DRAG,
    ):
        assert row.metrics[metric_id].status is EvidenceStatus.NOT_EVALUATED
    assert row.metrics[ResearchMetricId.TURNOVER].reason == (
        "insufficient_fill_nav_capital_evidence"
    )


def test_cost_drag_recomputes_fees_and_absolute_buy_sell_slippage() -> None:
    fold = OOS_FOLDS[0]
    candidate_id = CandidateId("candidate-alpha")
    buy = replace(
        _fill(fold),
        fill_id="buy-fill",
        fee=1.0,
        slippage=0.5,
    )
    sell = replace(
        _fill(fold),
        fill_id="sell-fill",
        order_id="sell-order",
        direction=OrderSide.SELL,
        fee=1.0,
        slippage=-0.25,
    )
    report = _report(
        candidate_id,
        fold,
        (100.0, 100.0),
        fills=(buy, sell),
    )
    evidence = _evidence(
        "candidate-alpha",
        2,
        1,
        (100.0, 100.0),
        report=report,
    )
    row = build_candidate_comparison(
        _baseline_identity(),
        (*_baseline_rows(), evidence),
    ).folds[1]

    assert row.metrics[ResearchMetricId.COST_DRAG].value == pytest.approx(3.5)


def test_evaluated_evidence_requires_nonempty_reference_and_content_hash() -> None:
    with pytest.raises(AppProcessError) as scalar_error:
        ScalarEvidence(
            EvidenceStatus.EVALUATED,
            ResearchMetricValue(ResearchMetricId.NET_RETURN, 1.0),
            None,
        )
    with pytest.raises(AppProcessError) as diagnostic_error:
        DiagnosticEvidence(EvidenceStatus.EVALUATED, 0.5, None)

    assert scalar_error.value.details["reason"] == "evaluated_evidence_source_required"
    assert diagnostic_error.value.details["reason"] == (
        "evaluated_evidence_source_required"
    )

    with pytest.raises(AppProcessError) as lineage_error:
        ScalarEvidence(
            EvidenceStatus.EVALUATED,
            ResearchMetricValue(ResearchMetricId.NET_RETURN, 1.0),
            None,
            ("result://one", "result://two"),
            (ContentHash("1" * 64),),
        )
    assert lineage_error.value.details["reason"] == ("evidence_lineage_length_mismatch")


def test_candidate_evidence_rejects_report_content_substitution() -> None:
    evidence = _evidence("candidate-alpha", 2, 1, (100.0, 101.0))
    artifact = evidence.report_artifact
    assert artifact is not None
    substituted = replace(
        artifact.evidence,
        final_nav=109.0,
        nav_series=(("2024-01-01", 100.0), ("2024-01-03", 109.0)),
    )

    with pytest.raises(AppProcessError) as exc_info:
        replace(
            evidence,
            report_artifact=replace(artifact, evidence=substituted),
        )

    assert exc_info.value.details["reason"] == "report_content_hash_drift"


def test_capacity_evidence_binds_value_and_exact_fold_identity() -> None:
    evidence = _evidence("candidate-alpha", 2, 1, (100.0, 101.0))
    capacity = evidence.capacity
    assert capacity is not None

    changed_value = replace(capacity, value_cny=2_000_000.0)
    assert changed_value.content_hash != capacity.content_hash
    object.__setattr__(changed_value, "content_hash", capacity.content_hash)
    with pytest.raises(AppProcessError) as content_error:
        replace(evidence, capacity=changed_value)

    changed_identity = replace(
        capacity,
        candidate_id=CandidateId("candidate-substituted"),
    )
    with pytest.raises(AppProcessError) as identity_error:
        replace(evidence, capacity=changed_identity)

    assert content_error.value.details["reason"] == "capacity_content_hash_drift"
    assert identity_error.value.details["reason"] == "capacity_evidence_identity_drift"


def test_fold_return_evidence_rejects_nav_return_contradiction() -> None:
    with pytest.raises(AppProcessError) as exc_info:
        FoldReturnEvidence(
            100.0,
            (("2024-01-01", 110.0),),
            (("2024-01-01", 0.05),),
            ("result://candidate/fold",),
            (ContentHash("1" * 64),),
        )

    assert exc_info.value.details["reason"] == "invalid_fold_return_evidence"


def test_exactly_two_ordered_nonoverlapping_oos_windows_are_required() -> None:
    baseline = _baseline_identity()
    overlapping = (
        OOS_FOLDS[0],
        replace(
            OOS_FOLDS[1],
            test_window=DateWindow(date(2024, 1, 3), date(2025, 1, 3)),
        ),
    )

    with pytest.raises(AppProcessError) as exc_info:
        replace(baseline, oos_folds=overlapping)

    assert exc_info.value.details["reason"] == "invalid_oos_fold_windows"


def test_two_persisted_walk_forward_ordinals_after_exploration_are_valid() -> None:
    persisted_folds = (
        replace(OOS_FOLDS[0], fold_ordinal=2),
        replace(OOS_FOLDS[1], fold_ordinal=3),
    )
    baseline = _baseline_identity(persisted_folds)
    rows = (
        _evidence(
            "candidate-baseline",
            1,
            1,
            (101.0, 102.0),
            fold_override=persisted_folds[0],
        ),
        _evidence(
            "candidate-baseline",
            1,
            2,
            (100.0, 101.0),
            fold_override=persisted_folds[1],
        ),
    )

    comparison = build_candidate_comparison(
        baseline,
        rows,
    )

    assert tuple(row.fold_ordinal for row in comparison.folds) == (2, 3)


def test_comparison_is_canonical_for_every_input_permutation() -> None:
    rows = (
        *_baseline_rows(),
        _evidence("candidate-alpha", 2, 1, (100.0, 101.0)),
        _evidence("candidate-alpha", 2, 2, (100.0, 102.0)),
    )

    projections = tuple(
        build_candidate_comparison(_baseline_identity(), order)
        for order in permutations(rows)
    )

    assert all(projection == projections[0] for projection in projections)
    assert tuple(
        (row.fold_ordinal, row.candidate_ordinal) for row in projections[0].folds
    ) == ((1, 1), (1, 2), (2, 1), (2, 2))


def test_comparison_has_versioned_authoritative_content_identity() -> None:
    rows = (
        *_baseline_rows(),
        _evidence("candidate-alpha", 2, 1, (100.0, 101.0)),
        _evidence("candidate-alpha", 2, 2, (100.0, 102.0)),
    )
    first = build_candidate_comparison(_baseline_identity(), rows)
    permuted = build_candidate_comparison(_baseline_identity(), reversed(rows))
    missing = replace(
        rows[2],
        report_artifact=None,
        factor_diagnostics=None,
        capacity=None,
    )
    changed = build_candidate_comparison(
        _baseline_identity(),
        (*rows[:2], missing, rows[3]),
    )

    payload = first.canonical_payload()
    assert payload["artifact_schema"] == {
        "id": R3_COMPARISON_ARTIFACT_SCHEMA_ID,
        "version": R3_COMPARISON_ARTIFACT_SCHEMA_VERSION,
    }
    assert payload["metric_schema"] == R3_RESEARCH_METRIC_SCHEMA.canonical_payload()
    assert type(first.content_hash) is ContentHash
    assert first.content_hash == permuted.content_hash
    assert first.content_hash != changed.content_hash
    missing_source = changed.folds[1].source.canonical_payload()
    assert missing_source["artifact_hash"] is None
    assert missing_source["artifact_ref"] is None
    assert missing_source["backtest_report_identity"] is None
    assert missing_source["result_hash"] is None
    assert missing_source["result_ref"] is None
    assert (
        changed.content_hash
        == build_candidate_comparison(
            _baseline_identity(),
            (*rows[:2], missing, rows[3]),
        ).content_hash
    )

    with pytest.raises(AppProcessError) as exc_info:
        CandidateComparisonProjection(first.baseline, first.metric_schema, first.folds)
    assert exc_info.value.details["reason"] == "comparison_factory_required"


def test_candidate_fold_api_accepts_only_one_typed_report_artifact() -> None:
    parameters = signature(CandidateFoldEvidence).parameters

    assert "report_artifact" in parameters
    assert "backtest_report" not in parameters
    assert "result_ref" not in parameters
    assert "result_hash" not in parameters
    assert "artifact_ref" not in parameters
    assert "artifact_hash" not in parameters


@pytest.mark.parametrize(
    ("record_field", "replacement_value"),
    [
        ("experiment_id", ExperimentId("experiment-other")),
        ("candidate_id", CandidateId("candidate-other")),
        ("fold_id", FoldId("fold-other")),
        ("attempt_id", AttemptId("attempt-other")),
        ("reproduction_fingerprint", ContentHash("9" * 64)),
        ("artifact_kind", "other"),
        ("artifact_id", "forged-artifact"),
        ("relative_path", "forged/report.json"),
    ],
)
def test_candidate_evidence_rejects_forged_loaded_record_identity(
    record_field: str,
    replacement_value: object,
) -> None:
    source = _evidence("candidate-alpha", 2, 1, (100.0, 101.0))
    artifact = source.report_artifact
    assert artifact is not None

    with pytest.raises(AppProcessError) as exc_info:
        replace(
            source,
            report_artifact=replace(
                artifact,
                record=replace(
                    artifact.record,
                    **{record_field: replacement_value},
                ),
            ),
        )

    assert exc_info.value.details["reason"] == "report_artifact_identity_drift"


def _rebuild_record_measurements(
    record: ArtifactRecord,
    *,
    schema_hash: ContentHash | None = None,
    row_count: int | None = None,
    byte_size: int | None = None,
) -> ArtifactRecord:
    manifest = ArtifactManifest.from_record(record)
    return ArtifactManifest.create(
        spec=manifest.spec,
        artifact_format=manifest.artifact_format,
        content_hash=manifest.content_hash,
        schema_hash=manifest.schema_hash if schema_hash is None else schema_hash,
        row_count=manifest.row_count if row_count is None else row_count,
        byte_size=manifest.byte_size if byte_size is None else byte_size,
    ).to_record()


def _mutate_manifest(
    record: ArtifactRecord,
    section: str,
    field: str,
    value: object,
) -> ArtifactRecord:
    manifest = deepcopy(dict(record.manifest))
    target = cast("dict[str, object]", manifest[section])
    target[field] = value
    return replace(record, manifest=manifest)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda record: _rebuild_record_measurements(
                record,
                schema_hash=ContentHash("9" * 64),
            ),
            id="self-consistent-schema-hash",
        ),
        pytest.param(
            lambda record: _rebuild_record_measurements(record, row_count=2),
            id="self-consistent-row-count",
        ),
        pytest.param(
            lambda record: _rebuild_record_measurements(
                record,
                byte_size=record.byte_size + 1,
            ),
            id="self-consistent-byte-size",
        ),
        pytest.param(
            lambda record: replace(
                record,
                schema_hash=cast("ContentHash", str(record.schema_hash)),
            ),
            id="non-nominal-schema-hash",
        ),
        pytest.param(
            lambda record: _mutate_manifest(
                record,
                "audit",
                "run_id",
                "forged-run",
            ),
            id="manifest-audit-run",
        ),
        pytest.param(
            lambda record: _mutate_manifest(
                record,
                "audit",
                "attempt_id",
                "forged-attempt",
            ),
            id="manifest-audit-attempt",
        ),
        pytest.param(
            lambda record: _mutate_manifest(
                record,
                "audit",
                "created_at",
                "2024-01-02T00:00:00+00:00",
            ),
            id="manifest-audit-created-at",
        ),
        pytest.param(
            lambda record: replace(
                record,
                manifest={**record.manifest, "format": "parquet"},
            ),
            id="manifest-format",
        ),
    ],
)
def test_comparison_revalidates_complete_artifact_after_construction(
    mutate: Callable[[ArtifactRecord], ArtifactRecord],
) -> None:
    source = _evidence("candidate-alpha", 2, 1, (100.0, 101.0))
    artifact = source.report_artifact
    assert artifact is not None
    object.__setattr__(artifact, "record", mutate(artifact.record))

    with pytest.raises(AppProcessError):
        build_candidate_comparison(
            _baseline_identity(),
            (*_baseline_rows(), source),
        )


def test_comparison_revalidates_persisted_binding_after_construction() -> None:
    source = _evidence("candidate-alpha", 2, 1, (100.0, 101.0))
    object.__setattr__(
        source.execution_binding,
        "content_hash",
        ContentHash("9" * 64),
    )

    with pytest.raises(AppProcessError) as exc_info:
        build_candidate_comparison(
            _baseline_identity(),
            (*_baseline_rows(), source),
        )

    assert exc_info.value.details["reason"] == "persisted_execution_binding_hash_drift"


def test_comparison_allows_multiple_missing_artifacts_without_zero_hashes() -> None:
    missing_rows = tuple(
        replace(row, report_artifact=None, factor_diagnostics=None, capacity=None)
        for row in _baseline_rows()
    )
    candidate = replace(
        _evidence("candidate-alpha", 2, 1, (100.0, 101.0)),
        report_artifact=None,
        factor_diagnostics=None,
        capacity=None,
    )

    comparison = build_candidate_comparison(
        _baseline_identity(),
        (*missing_rows, candidate),
    )

    assert all(
        row.source.result_hash is None
        and row.source.artifact_hash is None
        and row.metrics[ResearchMetricId.NET_RETURN].reason == "backtest_report_missing"
        for row in comparison.folds
    )
